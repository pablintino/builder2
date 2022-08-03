import argparse
import logging

from dependency_injector.wiring import inject, Provide

import builder2.loggers
from builder2.di import Container
from builder2.file_manager import FileManager
from builder2.commands import command_commons
from builder2.exceptions import BuilderException

__logger = logging.getLogger(__name__)


class SummaryVariableAction(argparse.Action):
    def __call__(self, parser, args, values, option_string=None):
        if args.query == "wk":
            setattr(args, self.dest, values)
        elif values:
            # Values present but type not wk
            raise ValueError("Variable name can only be used in wellknown queries")


def __get_variable_value(args, component):
    if args.query == "wk":
        return component.wellknown_paths.get(args.variable, None)
    elif args.query == "version":
        return component.version
    elif args.query == "path":
        return component.path
    elif args.query == "triplet":
        return component.triplet
    return None


@inject
def __get_variable(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
):
    try:
        builder2.loggers.configure("INFO" if args.output else "ERROR")

        installation_summary = command_commons.get_installation_summary_from_args(
            args, file_manager
        )

        component = installation_summary.get_component_by_name_and_version(
            args.tool, version=args.version
        )
        variable_value = __get_variable_value(args, component) if component else None
        if variable_value:
            # Raw print variable value (no log formatting)
            print(variable_value)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("get")
    command_parser.set_defaults(func=__get_variable, output=False)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_log_output_options(command_parser)
    command_parser.add_argument("tool", help="The tool to query")
    command_parser.add_argument(
        "query",
        choices=["wk", "path", "triplet", "version"],
        help="Wellknown path | bin folder variable query",
    )
    command_parser.add_argument(
        "variable",
        nargs="?",
        action=SummaryVariableAction,
        help="Wellknown path | bin folder variable query",
    )
    command_parser.add_argument(
        "-v",
        "--version",
        dest="version",
        help="Version of the component to query",
        required=False,
    )
