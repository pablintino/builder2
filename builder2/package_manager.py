import logging

import command_line

__logger = logging.getLogger()


def __update_sources():
    __logger.info('Running package cache update')
    command_line.run_process(['apt-get', 'update'])
    pass


def install_packages(packages):
    if packages:
        __update_sources()
        __logger.info('Installing packages %s', str(packages))
        command_line.run_process(['apt-get', 'install', '-y'] + packages)
