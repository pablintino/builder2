import dataclasses
import json
import pathlib
import re
import tarfile
import typing

import yaml

import builder2.file_manager
import builder2.cryptographic_provider
from builder2.exceptions import BuilderException
from builder2.models.installation_models import PipPackageInstallationModel
from builder2.python_manager import PythonManager


@dataclasses.dataclass
class AnsibleCollectionInstallReport:
    name: str
    version: str
    requirements: typing.List[str]
    package_hash: str
    collection_path: pathlib.Path = None
    pip_reports: typing.List[PipPackageInstallationModel] = None


@dataclasses.dataclass
class AnsibleCollectionInstallMainReport:
    main_collection: AnsibleCollectionInstallReport
    dependencies: typing.List[AnsibleCollectionInstallReport]


class AnsibleCollectionInstaller:
    __DEFAULT_REQUIREMENTS_REGEX = "requirements\.txt$"
    __SYSTEM_COLLECTIONS_PATH = "/usr/share/ansible/collections"

    def __init__(
        self,
        base_path: pathlib.Path,
        python_manager: PythonManager,
    ):
        self.__base_path = base_path
        self.__python_manager = python_manager

    def install(
        self,
        url: str = None,
        name: str = None,
        install_requirements: bool = False,
        system_wide: bool = False,
        requirements_patterns: typing.List[str] = None,
    ) -> AnsibleCollectionInstallMainReport:
        self.__python_manager.run_module(
            "ansible.cli.galaxy",
            "collection",
            "download",
            url or name,
            cwd=str(self.__base_path),
        )

        downloaded_base_dir = self.__base_path.joinpath("collections")
        collection_data, dependencies = self.__parse_collection_download_content(
            downloaded_base_dir, requirements_patterns
        )
        path_opts = (
            ["--collections-path", self.__SYSTEM_COLLECTIONS_PATH]
            if system_wide
            else []
        )
        self.__python_manager.run_module(
            "ansible.cli.galaxy",
            "collection",
            "install",
            "--force",
            "-r",
            "requirements.yml",
            *path_opts,
            cwd=str(downloaded_base_dir),
        )
        # Compute the path after installation
        collection_data = dataclasses.replace(
            collection_data, collection_path=self.__get_collection_path(name)
        )
        if install_requirements:
            return self.__install_requirements_and_update(collection_data, dependencies)

        return AnsibleCollectionInstallMainReport(collection_data, dependencies)

    def __install_requirements_and_update(
        self, collection_data, dependencies
    ) -> AnsibleCollectionInstallMainReport:
        main_collection_report = None
        dependencies_reports = []
        for collection in [collection_data] + dependencies:
            if not collection.requirements:
                continue
            pip_reports = []
            for requirement in collection.requirements:
                pip_reports.extend(
                    self.__python_manager.install_pip_requirements(
                        requirements_content=requirement
                    )
                )
            if collection == collection_data:
                main_collection_report = dataclasses.replace(
                    collection, pip_reports=pip_reports
                )
            else:
                dependencies_reports.append(
                    dataclasses.replace(collection, pip_reports=pip_reports)
                )
        return AnsibleCollectionInstallMainReport(
            main_collection_report or collection_data,
            dependencies_reports or dependencies,
        )

    def __parse_collection_download_content(
        self, base_dir: pathlib.Path, patterns: typing.List[str] = None
    ) -> typing.Tuple[
        AnsibleCollectionInstallReport, typing.List[AnsibleCollectionInstallReport]
    ]:
        requirements_file = base_dir.joinpath("requirements.yml")
        content = builder2.file_manager.read_yaml_file(requirements_file)
        if not content or "collections" not in content:
            raise BuilderException(
                f"requirements.yml file in {requirements_file} does not contain 'collections' element"
            )
        target_collection_data = None
        dependencies = []
        collections_list = content["collections"]
        for coll_idx in range(0, len(collections_list)):
            collection_data = collections_list[coll_idx]
            tar_name = collection_data.get("name", None)
            if not tar_name:
                raise BuilderException(
                    f"collection with index {coll_idx} in {requirements_file} does not contain a 'name' element"
                )
            tar_path = base_dir.joinpath(tar_name)
            if (not tar_path.exists()) or (tar_path.is_dir()):
                raise BuilderException(
                    f"tar file {tar_name} in {requirements_file} point to a non-existing tar file"
                )
            report = self.__parse_collection_tar(tar_path, patterns)
            # Assume the first report is the one that represents the collection,
            # the rest are its dependencies
            if not target_collection_data:
                target_collection_data = report
            elif report:
                dependencies.append(report)
        return target_collection_data, dependencies

    def __parse_collection_tar(
        self, tar_path: pathlib.Path, patterns: typing.List[str] = None
    ) -> AnsibleCollectionInstallReport:
        requirements = []
        name = None
        version = None
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if not name:
                    name, version = self.__fetch_collection_metadata_from_tar_member(
                        tar, member
                    )
                    if name:
                        continue

                reqs = self.__fetch_collection_requirements_from_tar_member(
                    tar, member, regexes=patterns
                )
                if reqs:
                    requirements.append(reqs)
        tar_hash = builder2.cryptographic_provider.compute_file_sha1(tar_path)
        return AnsibleCollectionInstallReport(
            name, version, requirements, tar_hash, pip_reports=[]
        )

    @staticmethod
    def __get_tar_member_string_content(
        tar_file: tarfile.TarFile, tar_member: tarfile.TarInfo
    ) -> typing.Optional[str]:
        f = tar_file.extractfile(tar_member)
        if f is not None:
            content = f.read()
            if isinstance(content, bytes):
                content = content.decode("utf-8")
            # Some requirement files are empty
            if content:
                return content
        return None

    def __fetch_collection_metadata_from_tar_member(
        self,
        tar_file: tarfile.TarFile,
        tar_member: tarfile.TarInfo,
    ) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        is_manifest = tar_member.name == "MANIFEST.json"
        is_galaxy = tar_member.name == "GALAXY.yml"
        if not is_galaxy and not is_manifest:
            return None, None

        content = self.__get_tar_member_string_content(tar_file, tar_member)
        if not content:
            return None, None

        if is_galaxy:
            return self.__fetch_collection_metadata_from_galaxy_file(content)

        if is_manifest:
            return self.__fetch_collection_metadata_from_manifest_file(content)

        return None, None

    @staticmethod
    def __fetch_collection_metadata_from_galaxy_file(
        manifest_content: str,
    ) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        yaml_content = yaml.safe_load(manifest_content)
        if not yaml_content:
            return None, None
        name = yaml_content.get("name", None)
        namespace = yaml_content.get("namespace", None)
        version = yaml_content.get("version", None)
        if version is None or name is None or namespace is None:
            return None, None
        return f"{namespace}.{name}", version

    @staticmethod
    def __fetch_collection_metadata_from_manifest_file(
        manifest_content: str,
    ) -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
        json_content = json.loads(manifest_content)
        if not json_content or "collection_info" not in json_content:
            return None, None
        collection_info = json_content["collection_info"]
        name = collection_info.get("name", None)
        namespace = collection_info.get("namespace", None)
        version = collection_info.get("version", None)
        if version is None or name is None or namespace is None:
            return None, None
        return f"{namespace}.{name}", version

    def __fetch_collection_requirements_from_tar_member(
        self,
        tar_file: tarfile.TarFile,
        tar_member: tarfile.TarInfo,
        regexes: typing.List[str] = None,
    ) -> typing.Optional[str]:
        if not any(
            (
                re.match(reg, tar_member.name) is not None
                for reg in regexes or [self.__DEFAULT_REQUIREMENTS_REGEX]
            )
        ):
            return None

        return self.__get_tar_member_string_content(tar_file, tar_member)

    def __get_collection_path(
        self, collection_name: str
    ) -> typing.Optional[pathlib.Path]:
        config_params = json.loads(
            self.__python_manager.run_module_check_output(
                "ansible.cli.config",
                "dump",
                "--format",
                "json",
            )
        )
        collection_paths = next(
            (
                param["value"]
                for param in config_params
                if (param.get("name", None) == "COLLECTIONS_PATHS") and "value" in param
            ),
            [],
        )

        name_split = collection_name.split(".")
        name = name_split[1] if len(name_split) > 1 else ""
        namespace = name_split[0]
        for candidate_path in collection_paths:
            # By ansible docs, the collections path is always suffixed by "ansible_collections"
            # if the deepest tree element is not named "ansible_collections".
            base_path = pathlib.Path(candidate_path)
            if base_path.name != "ansible_collections":
                base_path = base_path.joinpath("ansible_collections")

            computed_path = base_path.joinpath(
                namespace,
                name,
            )
            if computed_path.resolve().is_dir():
                return computed_path
        return None
