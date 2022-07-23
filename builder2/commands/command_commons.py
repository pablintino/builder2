import logging

from exceptions import BuilderException
from installation_summary import InstallationSummary

__logger = logging.getLogger()


def get_installation_summary_from_args(args):
    try:
        return InstallationSummary.from_path(args.summary_path)
    except FileNotFoundError as err:
        raise BuilderException(err) from err


def register_installation_summary_arg_option(command_parser):
    command_parser.add_argument('-i', '--installation-summary', dest='summary_path',
                                help='Path to the installation summary descriptor file or installation directory',
                                env_var='BUILDER_INSTALLATION', required=True)
