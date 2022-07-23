import logging
import subprocess
import sys

import configargparse
import os
import pwd

import certificate_manager
import loggers
from commands import command_commons
from exceptions import BuilderException

__logger = logging.getLogger()

__FALLBACK_SHELLS = ['/bin/bash, /bin/sh']


def __get_fallback_shell():
    for shell in __FALLBACK_SHELLS:
        try:
            subprocess.call([shell])
        except FileNotFoundError:
            # Do nothing
            pass
        return shell
    return None


def __get_user_shell():
    try:
        pwddb = pwd.getpwuid(os.getuid())
        if pwddb.pw_shell:
            return pwddb.pw_shell
    except KeyError:
        # Do nothing, defaults as shell value
        pass
    return None


def __get_default_shell():
    shell = __get_user_shell()
    if not shell:
        shell = __get_fallback_shell()
    if not shell:
        __logger.error('Cannot determine default shell. Exiting.')
        sys.exit(2)

    return shell


def __exec_command(bootstrap_args: list, env: dict):
    if bootstrap_args:
        # If command was launched with arguments use them
        command = bootstrap_args
    else:
        # If not, just try to get the default shell and launch it
        command = [__get_default_shell()]

    try:
        os.execvpe(command[0], command, env)
    except OSError as err:
        # If failed to execute (command not found, no permissions, etc.) get the errno and set it as return code
        __logger.debug('Program exited with code %d', int(err.errno), exc_info=err)
        sys.exit(err.errno)


def __get_env_vars(installation_summary):
    # Calling process vars are the base of the ones passed to the bootstrapped command (like USER, PATH, HOME...)
    variables = os.environ.copy()
    for key, installation in installation_summary.get_components().items():
        variables.update(installation.environment_vars)
    variables.update(installation_summary.get_environment_variables())
    return variables


def __bootstrap(args):
    try:
        loggers.configure('INFO' if args.output else 'ERROR')

        installation_summary = command_commons.get_installation_summary_from_args(args)

        # If cert path is given install certificates
        if args.certs_dir:
            certificate_manager.install_all_certificates(installation_summary, args.certs_dir)

        bootstrap_cmd = args.remainder
        if len(bootstrap_cmd) > 0 and bootstrap_cmd[0] == '--':
            bootstrap_cmd = bootstrap_cmd[1:]

        env_vars = __get_env_vars(installation_summary)
        __exec_command(bootstrap_cmd, env_vars)

    except BuilderException as err:
        __logger.error(str(err.message))
        sys.exit(err.exit_code)


def register(subparsers):
    command_parser = subparsers.add_parser('bootstrap')
    command_parser.set_defaults(func=__bootstrap)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_parser.add_argument('--certs', dest='certs_dir',
                                help='Optional path to the directory with the certificates to load', required=False)
    command_parser.add_argument('-o', '--output', action="store_true", dest='output', help='Outputs non error messages',
                                default=False)
    command_parser.add_argument('remainder', nargs=configargparse.REMAINDER)
