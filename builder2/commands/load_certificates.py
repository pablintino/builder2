import logging

import certificate_manager
import loggers
from commands import command_commons
from exceptions import BuilderException

__logger = logging.getLogger()


def __load_certificates(args):
    try:
        loggers.configure()

        installation_summary = command_commons.get_installation_summary_from_args(args)
        certificate_manager.install_all_certificates(installation_summary, args.certs_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser('load-certificates')
    command_parser.set_defaults(func=__load_certificates)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_parser.add_argument('-c', '--certs', dest='certs_dir',
                                help='Path to the directory with the certificates to load', required=True)
