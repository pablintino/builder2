import logging
import os
import pwd
import signal
import subprocess
import sys

import configargparse
from dependency_injector.wiring import inject, Provide

import builder2.loggers
from builder2.certificate_manager import CertificateManager
from builder2.command_line import CommandRunner
from builder2.commands import command_commons
from builder2.di import Container
from builder2.environment_builder import EnvironmentBuilder
from builder2.exceptions import BuilderException
from builder2.file_manager import FileManager

__logger = logging.getLogger(__name__)

__FALLBACK_SHELLS = ["/bin/bash, /bin/sh"]


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
        # Do nothing
        pass
    return None


def __get_default_shell():
    shell = __get_user_shell()
    if not shell:
        shell = __get_fallback_shell()
    if not shell:
        __logger.error("Cannot determine default shell. Exiting.")
        sys.exit(2)

    return shell


def __prepare_command(args):
    bootstrap_cmd = args.remainder
    if len(bootstrap_cmd) > 0 and bootstrap_cmd[0] == "--":
        bootstrap_cmd = bootstrap_cmd[1:]
    if len(bootstrap_cmd) > 0 and bootstrap_cmd[0] == "":
        bootstrap_cmd = bootstrap_cmd[1:]

    # If command was launched with arguments use them
    # If not, just try to get the default shell and launch it
    return bootstrap_cmd if bootstrap_cmd else [__get_default_shell()]


def __signal_handler(_, __):
    # 130 is the bash exit code for SIGINTs
    sys.exit(130)


@inject
def __bootstrap(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    certificate_manager: CertificateManager = Provide[Container.certificate_manager],
    command_runner: CommandRunner = Provide[Container.command_runner],
    environment_builder: EnvironmentBuilder = Provide[Container.environment_builder],
):
    # Listen for process SIGNITs. If listener is not added SIGINT inside a container shell hangs the shell forever
    signal.signal(signal.SIGINT, __signal_handler)

    try:
        builder2.loggers.configure("INFO" if args.output else "ERROR")

        installation_summary = command_commons.get_installation_summary_from_args(
            args, file_manager
        )

        # If cert path is given and exists go install them
        # (if path doesn't exist an exception is raised internally)
        if args.certs_dir and os.path.exists(args.certs_dir):
            certificate_manager.install_all_certificates(
                installation_summary, args.certs_dir
            )
        elif args.certs_dir:
            __logger.warning(
                "Skipping loading certificates. %s does not exist", args.certs_dir
            )

        bootstrap_cmd = __prepare_command(args)
        env_vars = environment_builder.build_environment_variables(
            installation_summary,
            args.generate_vars,
            add_python_env=args.generate_python_vars,
        )
        command_runner.exec_command(bootstrap_cmd, env_vars)
    except OSError as err:
        sys.exit(err.errno)
    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("bootstrap")
    command_parser.set_defaults(func=__bootstrap, output=True, generate_vars=False)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_certificates_arg_option(command_parser)
    command_parser.add_argument(
        "--no-output",
        dest="output",
        action="store_false",
        help="Disable all no error logs",
    )
    command_parser.add_argument(
        "--generate-vars",
        dest="generate_vars",
        action="store_true",
        help="Enable component generated environment variables",
    )
    command_parser.add_argument(
        "--generate-python-vars",
        dest="generate_python_vars",
        action="store_true",
        help="Enable python paths tweaking for builder2 venvs",
    )
    command_parser.add_argument("remainder", nargs=configargparse.REMAINDER)
