import json
import logging
import sys

from exceptions import BuilderException, BuilderValidationException
from installation_summary import InstallationSummary

__logger = logging.getLogger()


def get_installation_summary_from_args(args, file_manager):
    try:
        return InstallationSummary.from_path(args.summary_path, file_manager)
    except FileNotFoundError as err:
        raise BuilderException(err) from err


def register_installation_summary_arg_option(command_parser):
    command_parser.add_argument(
        "-i",
        "--installation-summary",
        dest="summary_path",
        help="Path to the installation summary descriptor file or installation directory",
        env_var="BUILDER_INSTALLATION",
        required=True,
    )


def manage_builder_exceptions(exception):
    if isinstance(exception, BuilderValidationException):
        __logger.error(exception.message)
        if exception.details:
            __logger.error(json.dumps(exception.details, sort_keys=True, indent=4))
        sys.exit(1)
    elif isinstance(exception, BuilderException):
        __logger.error(str(exception.message))
        sys.exit(exception.exit_code)
    else:
        raise exception
