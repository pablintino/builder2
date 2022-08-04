import logging
import os

from dependency_injector.wiring import inject, Provide

import builder2.loggers
from builder2.commands import command_commons
from builder2.conan_manager import CONAN_PROFILE_TYPES
from builder2.di import Container
from builder2.exceptions import BuilderException
from builder2.file_manager import FileManager
from builder2.models.installation_models import ComponentInstallationModel

__logger = logging.getLogger(__name__)


def __print_result(args, data):
    if data:
        to_print = data if type(data) == str else os.linesep.join(data)
        if args.output:
            __logger.info("Query result: %s", to_print)
        else:
            print(to_print)
    else:
        __logger.info("Query returned no data")


def __conan_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        list(component.conan_profiles.keys())
        if not args.type
        else component.conan_profiles.get(args.type, None),
    )


def __wellknown_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        list(component.wellknown_paths.keys())
        if not args.wellknown
        else component.wellknown_paths.get(args.wellknown, None),
    )


def __path_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        component.path,
    )


def __version_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        component.version,
    )


def __triplet_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        component.triplet,
    )


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

        component = installation_summary.get_component(
            args.component, version=args.version, default_if_not_found=True
        )

        if component:
            args.query_func(args, component)
        else:
            __logger.info("Component %s not found", args.component)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def __register_common_command_options(command_parser):
    command_parser.add_argument("component", help="The name of the component to query")
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_log_output_options(command_parser)
    command_parser.add_argument(
        "-v",
        "--version",
        required=False,
        help="The component version to refine component search",
    )


def __register_conan_query(query_subparsers):
    command_parser = query_subparsers.add_parser("conan")
    command_parser.set_defaults(query_func=__conan_query)
    __register_common_command_options(command_parser)
    command_parser.add_argument(
        "type",
        nargs="?",
        help="Conan profile type",
        choices=[conan_type.lower() for conan_type in CONAN_PROFILE_TYPES],
    )


def __register_path_query(query_subparsers):
    command_parser = query_subparsers.add_parser("path")
    command_parser.set_defaults(query_func=__path_query)
    __register_common_command_options(command_parser)


def __register_version_query(query_subparsers):
    command_parser = query_subparsers.add_parser("version")
    command_parser.set_defaults(query_func=__version_query)
    __register_common_command_options(command_parser)


def __register_triplet_query(query_subparsers):
    command_parser = query_subparsers.add_parser("triplet")
    command_parser.set_defaults(query_func=__triplet_query)
    __register_common_command_options(command_parser)


def __register_wellknown_query(query_subparsers):
    command_parser = query_subparsers.add_parser("wk")
    command_parser.set_defaults(query_func=__wellknown_query)
    __register_common_command_options(command_parser)
    command_parser.add_argument(
        "wellknown", nargs="?", help="The wellknown to retrieve"
    )


def register(subparsers):
    command_parser = subparsers.add_parser("get")
    command_parser.set_defaults(func=__get_variable, output=False)
    query_subparsers = command_parser.add_subparsers(dest="query", required=True)

    __register_conan_query(query_subparsers)
    __register_path_query(query_subparsers)
    __register_version_query(query_subparsers)
    __register_triplet_query(query_subparsers)
    __register_wellknown_query(query_subparsers)
