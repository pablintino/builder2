import logging

from command_line import CommandRunner

__logger = logging.getLogger()


class PackageManager:
    def __init__(self, command_runner: CommandRunner):
        self._command_runner = command_runner
        self._logger = logging.getLogger()
        self._update_ran = False

    def __update_sources(self):
        self._logger.info("Running package cache update")
        if not self._update_ran:
            self._command_runner.run_process(["apt-get", "update"])
            self._update_ran = True

    def install_packages(self, packages):
        if packages:
            self.__update_sources()
            self._logger.info("Installing packages %s", str(packages))
            self._command_runner.run_process(["apt-get", "install", "-y"] + packages)
