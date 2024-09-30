import json
import logging
import sys

from builder2 import constants
from builder2.exceptions import BuilderException, BuilderValidationException
from builder2.installation_summary import InstallationSummary

__logger = logging.getLogger(__name__)


def get_installation_summary_from_args(args) -> InstallationSummary:
    try:
        return InstallationSummary.from_path(args.summary_path)
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
        env_var=constants.ENV_VAR_INSTALLATION_SUMMARY,
        required=True,
    )


def register_certificates_arg_option(command_parser, required=False):
    command_parser.add_argument(
        "--certs",
        dest="certs_dir",
        help="Path to the directory with the certificates to load",
        env_var=constants.ENV_VAR_CERTIFICATES,
        required=required,
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
