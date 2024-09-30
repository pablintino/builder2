import dataclasses
import logging
import typing

import builder2.command_line
from builder2.exceptions import BuilderException
from builder2.models.installation_models import (
    PackageInstallationModel,
    PipPackageInstallationModel,
    AptPackageInstallationModel,
)
from builder2.models.metadata_models import (
    PipPackageInstallationConfiguration,
    AptPackageInstallationConfiguration,
    BasePackageInstallationConfiguration,
)
from builder2.python_manager import PythonManager


class PackageManager:
    def __init__(self, python_manager: PythonManager):
        self._python_manager = python_manager
        self._logger = logging.getLogger(self.__class__.__name__)
        self._apt_update_ran = False
        self.__installed_packages = {}
        self.__uninstalled_packages = {}

    def install_pip_package(
        self, package: PipPackageInstallationConfiguration
    ) -> PipPackageInstallationModel:
        installation_model = self._python_manager.install_pip_package(package)
        self.__run_post_commands(package.post_installation)
        return installation_model

    def __run_post_commands(self, commands):
        for command in commands or []:
            command_list = command.split(" ")
            builder2.command_line.run_process(command_list)

    def __update_apt_sources(self):
        self._logger.info("Running package cache update")
        if not self._apt_update_ran:
            builder2.command_line.run_process(["apt-get", "update"])
            self._apt_update_ran = True

    def __install_apt_package(
        self, package: AptPackageInstallationConfiguration
    ) -> PackageInstallationModel:
        self.__update_apt_sources()

        package_to_install = [
            f"{package.name}={package.version}" if package.version else package.name
        ]
        builder2.command_line.run_process(
            ["apt-get", "install", "-y"] + package_to_install
        )

        self.__run_post_commands(package.post_installation)
        return AptPackageInstallationModel(
            package.name, package.version, configuration=package
        )

    def __cleanup_apt_orphans(self):
        if any(
            isinstance(package, AptPackageInstallationConfiguration)
            and package.build_transient
            for package in self.__uninstalled_packages.values()
        ):
            builder2.command_line.run_process(["apt-get", "autoremove", "-y"])

    def __uninstall_apt_package(self, package: AptPackageInstallationConfiguration):
        package_to_uninstall = [
            f"{package.name}={package.version}" if package.version else package.name
        ]
        builder2.command_line.run_process(
            ["apt-get", "remove", "-y", "--purge"] + package_to_uninstall
        )

        package_key = self.__build_package_key(package)
        del self.__installed_packages[package_key]
        self.__uninstalled_packages[package_key] = package

    @classmethod
    def __build_package_key(cls, package: BasePackageInstallationConfiguration):
        return type(package), package.name, package.version

    def install_packages(self, packages):
        for package in packages:
            key = self.__build_package_key(package)
            # Check if transient and skip as is already installed packages
            if key in self.__installed_packages:
                # If the package was transient but is installed another time as
                # non-transient make it transient
                if (
                    self.__installed_packages[key].configuration.build_transient
                    and not package.build_transient
                ):
                    self.__installed_packages[key].configuration = dataclasses.replace(
                        self.__installed_packages[key].configuration,
                        build_transient=False,
                    )

                continue

            if isinstance(package, PipPackageInstallationConfiguration):
                package_install = self.install_pip_package(package)
            elif isinstance(package, AptPackageInstallationConfiguration):
                package_install = self.__install_apt_package(package)
            else:
                raise BuilderException(
                    f"unsupported package type {type(package).__name__}"
                )
            self.__installed_packages[key] = package_install

    def cleanup(self):
        transients = [
            package
            for package in self.__installed_packages.values()
            if package.configuration.build_transient
        ]
        for package in transients:
            if package.configuration.build_transient:
                if isinstance(
                    package.configuration, PipPackageInstallationConfiguration
                ):
                    self._python_manager.pip_uninstall(package.configuration)
                elif isinstance(
                    package.configuration, AptPackageInstallationConfiguration
                ):
                    self.__uninstall_apt_package(package.configuration)

        self.__cleanup_apt_orphans()

    def get_installed_packages(self) -> typing.List[PackageInstallationModel]:
        packages = []
        for package in self.__installed_packages.values():
            if isinstance(package, PipPackageInstallationConfiguration):
                # Discard Pip packages as we ask the python_manager for them directly
                continue
            packages.append(package)
        packages.extend(self._python_manager.pip_list())
        return packages
