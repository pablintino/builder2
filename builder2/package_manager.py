import dataclasses
import logging
import sys

from builder2.command_line import CommandRunner
from builder2.models.installation_models import PackageInstallationModel
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

    def __install_pip_package(
        self, package: PipPackageInstallationConfiguration
    ) -> PackageInstallationModel:
        self.__run_pip_install_package(package)
        self.__run_post_commands(package.post_installation)
        return PackageInstallationModel(
            package.name, package.version, configuration=package
        )

    def __run_post_commands(self, commands):
        for command in commands or []:
            command_list = command.split(" ")
            self._command_runner.run_process(command_list)

    def __run_pip_install_package(self, package: PipPackageInstallationConfiguration):
        command = [sys.executable, "-m", "pip", "install"]
        if package.index:
            command.extend(["--index-url", package.index])
        if package.version:
            command.append(f"{package.name}=={package.version}")
        else:
            command.append(f"{package.name}")

        self._command_runner.run_process(command)

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
                package_install = self.__install_pip_package(package)
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
