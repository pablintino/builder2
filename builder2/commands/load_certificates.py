import logging

import command_line
import file_utils
import tooling_support.java_support
import loggers
from certificate_manager import CertificateManager
from commands import command_commons
from exceptions import BuilderException

__logger = logging.getLogger()


def __load_certificates(args):
    try:
        loggers.configure()
        file_manager = file_utils.FileManager()
        command_runner = command_line.CommandRunner()
        java_tools = tooling_support.java_support.JavaTools(file_manager, command_runner)
        certificate_manager = CertificateManager(file_manager, java_tools, command_runner)
        installation_summary = command_commons.get_installation_summary_from_args(args, file_manager)
        certificate_manager.install_all_certificates(installation_summary, args.certs_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser('load-certificates')
    command_parser.set_defaults(func=__load_certificates)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_parser.add_argument('-c', '--certs', dest='certs_dir',
                                help='Path to the directory with the certificates to load', required=True)
