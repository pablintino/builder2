import configparser
import itertools
import json
import logging
import os
import pathlib
import shutil
import sys
import tempfile
import typing
from os import PathLike

from builder2 import command_line
from builder2 import file_manager
from builder2.exceptions import BuilderException
from builder2.models.installation_models import PipPackageInstallationModel
from builder2.models.metadata_models import PipPackageInstallationConfiguration


class PythonManager:
    def __init__(
            self,
            command_runner: command_line.CommandRunner,
            file_manager: file_manager.FileManager,
            target_path: typing.Union[str, PathLike[str]],
    ):
        self.__command_runner = command_runner
        self.__file_manager = file_manager
        self.__venv_path = pathlib.Path(target_path).resolve().joinpath(".venv")
        self.__logger = logging.getLogger()
        self.__venvs: typing.Dict[str, "PythonManager"] = {}

    def __get_binary(self):
        binary = self.__venv_path.joinpath("bin", "python3")
        if binary.exists():
            return binary

        self.__venv_path.mkdir(parents=True, exist_ok=True)
        self.__logger.debug(
            "Creating venv in %s",
        )
        self.__command_runner.run_process(
            [sys.executable, "-m", "venv", str(self.__venv_path)]
        )
        return binary

    def get_create_env(
            self,
            target_path: pathlib.Path,
            env_key: str,
            depends_on: str = None,
            create_venv: bool = False,
    ) -> "PythonManager":
        if env_key in self.__venvs:
            return self.__venvs[env_key]

        if depends_on and depends_on in self.__venvs:
            target_env = self.__venvs[depends_on]
            self.__venvs[env_key] = target_env
            return target_env
        elif depends_on:
            raise BuilderException(f"venv {depends_on} does not exist")

        if not create_venv:
            self.__venvs[env_key] = self
            return self

        env = PythonManager(
            self.__command_runner, self.__file_manager, target_path=target_path
        )
        self.__venvs[env_key] = env
        return env

    def run_module(self, module: str, *args, cwd: str = None):
        self.__command_runner.run_process(
            [str(self.__get_binary()), "-m", module] + list(args),
            cwd=cwd,
        )

    def run_module_check_output(self, module: str, *args, cwd: str = None) -> str:
        return self.__command_runner.check_output(
            [str(self.__get_binary()), "-m", module] + list(args),
            cwd=cwd,
        )

    def install_pip_package(
            self, pip_package: PipPackageInstallationConfiguration
    ) -> PipPackageInstallationModel:
        command = ["install"]
        if pip_package.index:
            command.extend(["--index-url", pip_package.index])
        if pip_package.version:
            command.append(f"{pip_package.name}=={pip_package.version}")
        else:
            command.append(f"{pip_package.name}")
        if pip_package.force:
            command.append("--force")

        # Cannot use the new --report option because it doesn't point
        # to the installation location
        self.run_module("pip", *command)
        element_report = self.__get_pip_report_element_for_package(
            pip_package.name, self.__pip_inspect(), version=pip_package.version
        )
        if not element_report:
            raise BuilderException(
                f"unable to get pip report for freshly installed package {pip_package.name}"
            )
        return self.__build_pip_installation_model_from_report_element(
            element_report, configuration=pip_package
        )

    def install_pip_requirements(
            self,
            requirements_file: str = None,
            requirements_content: str = None,
    ) -> typing.List[PipPackageInstallationModel]:
        report = self.__install_pip_requirements(
            requirements_file=requirements_file,
            requirements_content=requirements_content,
        )
        return self.__build_installation_models_from_report(report)

    @staticmethod
    def fetch_entry_points(
            package_path: pathlib.Path,
    ) -> typing.Optional[typing.Dict[str, str]]:
        if not package_path.exists():
            return None

        entry_points_info_path = package_path.joinpath("entry_points.txt")
        if not entry_points_info_path.exists():
            return None
        config = configparser.ConfigParser()
        if not config.read(entry_points_info_path):
            # todo log: error reading the file
            return None
        try:
            entry_points = config.options("console_scripts") or []
        except configparser.NoSectionError:
            # todo log
            return None

        # How this works:
        # 1. The parent of entry_points_install_dir points to either site-packages or dist-packages
        # 2. site/dist-packages parent is a dir named python<version>
        # 3. python<version> lives in the lib/ directory
        # 4. lib/ parent is where lib/, include/, bin/ live. No matter
        #    if it's a venv of the system python
        entry_points_install_dir = package_path.parent.parent.parent.parent.joinpath(
            "bin"
        )
        if not entry_points_install_dir.is_dir():
            # todo log: error computing the bin dir
            return None

        result = {}
        for entry_point in entry_points:
            path = entry_points_install_dir.joinpath(entry_point)
            if path.exists():
                result[entry_point] = str(path)
        return result

    def fetch_package_location(
            self, name: str, version: str = None
    ) -> typing.Optional[pathlib.Path]:
        model = self.get_pip_model_by_package(name, version=version)
        if not model:
            return None
        location = pathlib.Path(model.location)
        return location if location.is_dir() else None

    def get_pip_model_by_package(
            self,
            name: str,
            version: str = None
    ) -> typing.Optional[PipPackageInstallationModel]:
        element_report = self.__get_pip_report_element_for_package(
            name, self.__pip_inspect(), version=version
        )
        if not element_report:
            return None
        return self.__build_pip_installation_model_from_report_element(element_report)

    def pip_uninstall(self, package: PipPackageInstallationConfiguration):
        package_command_arg = package.name if not package.version else f"{package.name}=={package.version}"
        self.run_module("pip", "uninstall", "-y", package_command_arg)

    def pip_list(self) -> typing.List[PipPackageInstallationModel]:
        envs_packages = [env.pip_list() for env in self.__venvs.values()]
        packages = set(itertools.chain(*envs_packages))
        packages.update(
            (
                self.__build_pip_installation_model_from_report_element(element)
                for element in self.__pip_inspect(local=True).get("installed", [])
            )
        )
        return sorted(packages, key=lambda x: x.name)


    def __pip_inspect(self, local: bool = False) -> typing.Dict[str, typing.Any]:
        opts = ["--local"] if local else []
        return json.loads(self.run_module_check_output("pip", "inspect", *opts))

    def __install_pip_requirements(
            self,
            requirements_file: str = None,
            requirements_content: str = None,
    ) -> typing.Dict[str, typing.Any]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reqs_path = os.path.join(tmp_dir, "requirements.txt")
            if requirements_file:
                shutil.copy2(requirements_file, temp_reqs_path)
            elif requirements_content:
                self.__file_manager.write_text_file(
                    temp_reqs_path, requirements_content
                )
            self.run_module("pip", "install", "-r", temp_reqs_path, "--force", cwd=tmp_dir)
            return self.__pip_inspect()

    @classmethod
    def __get_pip_report_element_for_package(
            cls,
            name: str,
            pip_install_report: typing.Dict[str, typing.Any],
            version: str = None
    ) -> typing.Optional[typing.Dict[str, typing.Any]]:
        return next(
            (
                elem
                for elem in pip_install_report.get("installed", [])
                if (
                           cls.__extract_name_from_pip_report_element(elem) == name
                   )
                   and (
                           not version
                           or version
                           == cls.__extract_version_from_pip_report_element(elem)
                   )
            ),
            None,
        )

    @staticmethod
    def __extract_version_from_pip_report_element(tool_element):
        version = tool_element.get("metadata", {}).get("version", None)
        if not version:
            raise BuilderException("cannot fetch version from pip report")
        return version

    @staticmethod
    def __extract_name_from_pip_report_element(tool_element) -> str:
        name = tool_element.get("metadata", {}).get("name", None)
        if not name:
            raise BuilderException("cannot fetch name from pip report")
        return name

    @staticmethod
    def __extract_location_from_pip_report_element(
            tool_element,
    ) -> pathlib.Path:
        if "metadata_location" not in tool_element:
            # todo context
            print(tool_element)
            raise BuilderException("cannot fetch package location from pip report")
        return pathlib.Path(tool_element["metadata_location"])

    @staticmethod
    def __extract_hash_from_pip_report_element(tool_element):
        hash_str = (
            tool_element.get("download_info", {})
            .get("archive_info", {})
            .get("hash", None)
        )
        if hash_str and "=" in hash_str:
            hash_str = hash_str.split("=", 1)[1]
        return hash_str

    @classmethod
    def __build_installation_models_from_report(
            cls, pip_install_report: typing.Dict[str, typing.Any]
    ) -> typing.List[PipPackageInstallationModel]:
        return [
            cls.__build_pip_installation_model_from_report_element(install_elem)
            for install_elem in pip_install_report.get("install", [])
        ]

    @classmethod
    def __build_pip_installation_model_from_report_element(
            cls,
            install_elem: typing.Dict[str, typing.Any],
            configuration: PipPackageInstallationConfiguration = None,
    ):
        name = cls.__extract_name_from_pip_report_element(install_elem)
        version = cls.__extract_version_from_pip_report_element(install_elem)
        package_hash = cls.__extract_hash_from_pip_report_element(install_elem)
        location = cls.__extract_location_from_pip_report_element(install_elem)
        return PipPackageInstallationModel(
            name,
            version,
            pip_hash=package_hash,
            configuration=configuration,
            location=str(location),
        )
