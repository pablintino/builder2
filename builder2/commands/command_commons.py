import json
import logging
import sys

from builder2.exceptions import BuilderException, BuilderValidationException
from builder2.installation_summary import InstallationSummary

__logger = logging.getLogger(__name__)


def get_installation_summary_from_args(args, file_manager):
    try:
        return InstallationSummary.from_path(args.summary_path, file_manager)
    except FileNotFoundError as err:
        raise BuilderException(
            f"Installation summary '{args.summary_path}' not found", exit_code=2
        ) from err


def register_installation_summary_arg_option(command_parser):
    command_parser.add_argument(
        "-i",
        "--installation-summary",
        dest="summary_path",
        help="Path to the installation summary descriptor file or installation directory",
        env_var="BUILDER_INSTALLATION",
        required=True,
    )


def register_log_output_options(command_parser):
    command_parser.add_argument(
        "--output", action="store_true", help="Enables log messages"
    )
    command_parser.add_argument(
        "--no-output",
        dest="output",
        action="store_false",
        help="Disable all no error logs",
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
