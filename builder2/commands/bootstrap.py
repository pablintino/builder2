import logging
import os
import pwd
import signal
import subprocess
import sys

import configargparse

import builder2.certificate_manager
import builder2.command_line
import builder2.environment_builder
import builder2.loggers
from builder2 import constants
from builder2.commands import command_commons
from builder2.exceptions import BuilderException

__logger = logging.getLogger(__name__)

__FALLBACK_SHELLS = ["/bin/bash, /bin/sh"]


def __fetch_user_group(user_id: str):
    try:
        user_id_str, group_id_str = user_id.split(":", 1)
        user_id = int(user_id_str)
        group_id = int(group_id_str)
        return user_id, group_id
    except ValueError as e:
        __logger.error(
            "Cannot parse the given user and group IDs %s. Exiting.", user_id
        )
        sys.exit(2)


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


def __user_exists(user_id: int) -> bool:
    try:
        pwd.getpwuid(user_id)
        return True
    except KeyError:
        return False


def __create_user(uid):
    if __user_exists(uid):
        return
    try:
        # copy the shell from the running user
        default_shell = __get_default_shell()
        subprocess.check_call(
            ["useradd", "-u", str(uid), "devuser", "-ms", default_shell],
            text=True,
        )
    except subprocess.CalledProcessError:
        __logger.error("Cannot parse create a devuser with IDs %d. Exiting.", uid)
        sys.exit(3)


def __setup_user(user_id: str) -> None:
    try:
        if not user_id:
            return

        uid, gid = __fetch_user_group(user_id)

        # if we are already using the requested user just do nothing
        if uid == os.getuid():
            return

        __create_user(uid)

        os.setgid(gid)
        os.setuid(uid)

        os.environ["HOME"] = pwd.getpwuid(uid).pw_dir  # user must exist, it can't fail
    except OSError:
        __logger.error("Cannot switch to the user ID %s. Exiting.", user_id)
        sys.exit(4)


def __bootstrap(
    args,
):
    # Listen for process SIGNITs. If listener is not added SIGINT inside a container shell hangs the shell forever
    signal.signal(signal.SIGINT, __signal_handler)

    try:
        builder2.loggers.configure("INFO" if not args.quiet else "ERROR")

        installation_summary = command_commons.get_installation_summary_from_args(args)

        # If cert path is given and exists go install them
        # (if path doesn't exist an exception is raised internally)
        if args.certs_dir and os.path.exists(args.certs_dir):
            builder2.certificate_manager.install_all_certificates(
                installation_summary, args.certs_dir
            )
        elif args.certs_dir:
            __logger.warning(
                "Skipping loading certificates. %s does not exist", args.certs_dir
            )

        __setup_user(args.user_id)
        bootstrap_cmd = __prepare_command(args)
        env_vars = builder2.environment_builder.build_environment_variables(
            installation_summary, args.generate_vars
        )
        builder2.command_line.exec_command(bootstrap_cmd, env_vars)
    except OSError as err:
        sys.exit(err.errno)
    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("bootstrap")
    command_parser.set_defaults(func=__bootstrap, quiet=True, generate_vars=False)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_certificates_arg_option(command_parser)
    command_parser.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Disable all no error logs",
    )
    command_parser.add_argument(
        "--generate-vars",
        dest="generate_vars",
        action="store_true",
        env_var=constants.ENV_VAR_GENERATE_VARS,
        help="Enable component generated environment variables",
    )
    command_parser.add_argument(
        "--user",
        dest="user_id",
        env_var=constants.ENV_VAR_BOOTSTRAP_UID,
        help="The user and group IDs in format <user>:<group> to switch to",
    )
    command_parser.add_argument("remainder", nargs=configargparse.REMAINDER)
