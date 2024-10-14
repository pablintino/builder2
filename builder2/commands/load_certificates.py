import logging

import builder2.certificate_manager
import builder2.loggers
import builder2.commands.command_commons
import builder2.exceptions

__logger = logging.getLogger(__name__)


def __load_certificates(
    args,
):
    try:
        builder2.loggers.configure("INFO" if not args.quiet else "ERROR")

        installation_summary = (
            builder2.commands.command_commons.get_installation_summary_from_args(args)
        )
        builder2.certificate_manager.install_all_certificates(
            installation_summary, args.certs_dir
        )

    except builder2.exceptions.BuilderException as err:
        builder2.commands.command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("load-certificates")
    command_parser.set_defaults(func=__load_certificates, quiet=False)
    builder2.commands.command_commons.register_installation_summary_arg_option(
        command_parser
    )
    builder2.commands.command_commons.register_certificates_arg_option(
        command_parser, required=True
    )
    command_parser.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Disable all no error logs",
    )
