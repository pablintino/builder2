import dataclasses
import json
import logging
import os
import shutil
import sys
import tempfile
import typing

from builder2.command_line import CommandRunner
from builder2.models.installation_models import (
    PackageInstallationModel,
    PipPackageInstallationModel,
)
from builder2.models.metadata_models import (
    PipPackageInstallationConfiguration,
    AptPackageInstallationConfiguration,
    BasePackageInstallationConfiguration,
)


class PackageManager:
    def __init__(self, command_runner: CommandRunner):
        self._command_runner = command_runner
        self._logger = logging.getLogger()
        self._apt_update_ran = False
        self.installed_packages = {}
        self.__uninstalled_packages = {}

    def install_pip_package(
        self, package: PipPackageInstallationConfiguration
    ) -> PipPackageInstallationModel:
        report = self.__run_pip_install_package(package)
        self.__run_post_commands(package.post_installation)
        pip_version, pip_hash = self.__extract_version_hash_from_report(
            package.name, report
        )
        return PipPackageInstallationModel(
            package.name,
            pip_version,
            configuration=package,
            report=report,
            pip_hash=pip_hash,
        )

    def install_pip_requirements(
        self, requirements_file: str = None, requirements_content: str = None
    ) -> typing.List[PipPackageInstallationModel]:
        report = self.__install_pip_requirements(
            requirements_file=requirements_file,
            requirements_content=requirements_content,
        )
        return self.__build_installation_models_from_report(report)

    def __install_pip_requirements(
        self, requirements_file: str = None, requirements_content: str = None
    ) -> typing.Dict[str, typing.Any]:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_reqs_path = os.path.join(tmp_dir, "requirements.txt")
            if requirements_file:
                shutil.copy2(requirements_file, temp_reqs_path)
            elif requirements_content:
                with open(temp_reqs_path, "w") as f:
                    f.write(requirements_content)
            temp_file = os.path.join(tmp_dir, "report.json")
            command = [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                temp_reqs_path,
                "--report",
                temp_file,
                "--force",
            ]
            self._command_runner.run_process(command, cwd=tmp_dir)
            with open(temp_file, "r") as f:
                return json.load(f)

    @classmethod
    def __extract_version_hash_from_report(
        cls, name: str, pip_install_report: typing.Dict[str, typing.Any]
    ) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        tool_element = next(
            (
                elem
                for elem in pip_install_report.get("install", [])
                if cls.__extract_name_from_pip_report_element(elem) == name
            ),
            None,
        )
        if not tool_element:
            return None, None

        hash_str = cls.__extract_hash_from_pip_report_element(tool_element)
        version = cls.__extract_version_from_pip_report_element(tool_element)
        return version, hash_str

    @staticmethod
    def __extract_version_from_pip_report_element(tool_element):
        version = tool_element.get("metadata", {}).get("version", None)
        return version

    @staticmethod
    def __extract_name_from_pip_report_element(tool_element):
        version = tool_element.get("metadata", {}).get("name", None)
        return version

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
        models = []
        for install_elem in pip_install_report.get("install", []):
            name = cls.__extract_name_from_pip_report_element(install_elem)
            version = cls.__extract_version_from_pip_report_element(install_elem)
            package_hash = cls.__extract_hash_from_pip_report_element(install_elem)
            models.append(
                PipPackageInstallationModel(
                    name,
                    version,
                    pip_hash=package_hash,
                    configuration=PipPackageInstallationConfiguration(
                        name=name, version=version
                    ),
                )
            )
        return models

    def __run_post_commands(self, commands):
        for command in commands or []:
            command_list = command.split(" ")
            self._command_runner.run_process(command_list)

    def __run_pip_install_package(
        self, package: PipPackageInstallationConfiguration
    ) -> typing.Dict[str, typing.Any]:
        command = [sys.executable, "-m", "pip", "install"]
        if package.index:
            command.extend(["--index-url", package.index])
        if package.version:
            command.append(f"{package.name}=={package.version}")
        else:
            command.append(f"{package.name}")
        if package.force:
            command.append("--force")

        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_file = os.path.join(tmp_dir, "report.json")
            command.extend(["--report", temp_file])
            self._command_runner.run_process(command)
            with open(temp_file, "r") as f:
                return json.load(f)

    def __run_pip_uninstall_package(self, package: PipPackageInstallationConfiguration):
        package_command_arg = package.name
        if package.version:
            package_command_arg = f"{package_command_arg}=={package.version}"
        command = [sys.executable, "-m", "pip", "uninstall", "-y", package_command_arg]
        self._command_runner.run_process(command)

        package_key = self.__build_package_key(package)
        del self.installed_packages[package_key]
        self.__uninstalled_packages[package_key] = package

    def __update_apt_sources(self):
        self._logger.info("Running package cache update")
        if not self._apt_update_ran:
            self._command_runner.run_process(["apt-get", "update"])
            self._apt_update_ran = True

    def __install_apt_package(
        self, package: AptPackageInstallationConfiguration
    ) -> PackageInstallationModel:
        self.__update_apt_sources()

        package_to_install = [
            f"{package.name}={package.version}" if package.version else package.name
        ]
        self._command_runner.run_process(
            ["apt-get", "install", "-y"] + package_to_install
        )

        self.__run_post_commands(package.post_installation)
        return PackageInstallationModel(
            package.name, package.version, configuration=package
        )

    def __cleanup_apt_orphans(self):
        if any(
            isinstance(package, AptPackageInstallationConfiguration)
            and package.build_transient
            for package in self.__uninstalled_packages.values()
        ):
            self._command_runner.run_process(["apt-get", "autoremove", "-y"])

    def __uninstall_apt_package(self, package: AptPackageInstallationConfiguration):
        package_to_uninstall = [
            f"{package.name}={package.version}" if package.version else package.name
        ]
        self._command_runner.run_process(
            ["apt-get", "remove", "-y", "--purge"] + package_to_uninstall
        )

        package_key = self.__build_package_key(package)
        del self.installed_packages[package_key]
        self.__uninstalled_packages[package_key] = package

    @classmethod
    def __build_package_key(cls, package: BasePackageInstallationConfiguration):
        return type(package), package.name, package.version

    def install_packages(self, packages):
        for package in packages:

            key = self.__build_package_key(package)
            # Check if transient and skip as is already installed packages
            if key in self.installed_packages:
                # If the package was transient but is installed another time as
                # non-transient make it transient
                if (
                    self.installed_packages[key].configuration.build_transient
                    and not package.build_transient
                ):
                    self.installed_packages[key].configuration = dataclasses.replace(
                        self.installed_packages[key].configuration,
                        build_transient=False,
                    )

                continue

            if isinstance(package, PipPackageInstallationConfiguration):
                package_install = self.install_pip_package(package)
            elif isinstance(package, AptPackageInstallationConfiguration):
                package_install = self.__install_apt_package(package)
            self.installed_packages[key] = package_install

    def clean_transient(self):
        transients = [
            package
            for package in self.installed_packages.values()
            if package.configuration.build_transient
        ]
        for package in transients:
            if package.configuration.build_transient:
                if isinstance(
                    package.configuration, PipPackageInstallationConfiguration
                ):
                    self.__run_pip_uninstall_package(package.configuration)
                elif isinstance(
                    package.configuration, AptPackageInstallationConfiguration
                ):
                    self.__uninstall_apt_package(package.configuration)

        self.__cleanup_apt_orphans()
