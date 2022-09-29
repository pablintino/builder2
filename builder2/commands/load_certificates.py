import logging

from dependency_injector.wiring import inject, Provide

import builder2.loggers
from builder2.di import Container
from builder2.file_manager import FileManager
from builder2.certificate_manager import CertificateManager
from builder2.commands import command_commons
from builder2.exceptions import BuilderException

__logger = logging.getLogger(__name__)


@inject
def __load_certificates(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    certificate_manager: CertificateManager = Provide[Container.certificate_manager],
):
    try:
        builder2.loggers.configure("INFO" if args.output else "ERROR")

        installation_summary = command_commons.get_installation_summary_from_args(
            args, file_manager
        )
        certificate_manager.install_all_certificates(
            installation_summary, args.certs_dir
        )

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("load-certificates")
    command_parser.set_defaults(func=__load_certificates, output=True)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_certificates_arg_option(command_parser, required=True)
    command_parser.add_argument(
        "--no-output",
        dest="output",
        action="store_false",
        help="Disable all no error logs",
    )
