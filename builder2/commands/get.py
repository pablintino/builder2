import logging
import os

import builder2.loggers
import builder2.commands.command_commons
import builder2.conan_manager
import builder2.exceptions
from builder2.models.installation_models import ComponentInstallationModel

__logger = logging.getLogger(__name__)


def __print_result(args, data):
    if data:
        to_print = data if isinstance(data, str) else os.linesep.join(data)
        __logger.info("Query result: %s", to_print)
        print(to_print)
    else:
        __logger.info("Query returned no data")


def __conan_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        (
            list(component.conan_profiles.keys())
            if not args.type
            else component.conan_profiles.get(args.type, None)
        ),
    )


def __wellknown_query(args, component: ComponentInstallationModel):
    __print_result(
        args,
        (
            list(component.wellknown_paths.keys())
            if not args.wellknown
            else component.wellknown_paths.get(args.wellknown, None)
        ),
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


def __get_variable(
    args,
):
    try:
        builder2.loggers.configure("INFO" if not args.quiet else "ERROR")

        installation_summary = (
            builder2.commands.command_commons.get_installation_summary_from_args(args)
        )
        component = installation_summary.get_component(
            args.component,
            version=args.version,
            triplet=args.triplet,
            default_if_not_found=True,
        )

        if component:
            args.query_func(args, component)
        else:
            __logger.info("Component %s not found", args.component)

    except builder2.exceptions.BuilderException as err:
        builder2.commands.command_commons.manage_builder_exceptions(err)


def __register_common_command_options(command_parser):
    command_parser.add_argument("component", help="The name of the component to query")
    builder2.commands.command_commons.register_installation_summary_arg_option(
        command_parser
    )
    command_parser.add_argument(
        "--quiet", dest="quiet", action="store_true", help="Disable all no error logs"
    )
    command_parser.add_argument(
        "--component-version",
        dest="version",
        required=False,
        help="The component version to refine component search",
    )
    command_parser.add_argument(
        "--component-triplet",
        dest="triplet",
        required=False,
        help="The component triplet to refine component search",
    )


def __register_conan_query(query_subparsers):
    command_parser = query_subparsers.add_parser("conan")
    command_parser.set_defaults(query_func=__conan_query, quiet=True)
    __register_common_command_options(command_parser)
    command_parser.add_argument(
        "type",
        nargs="?",
        help="Conan profile type",
        choices=[
            conan_type.lower()
            for conan_type in builder2.conan_manager.CONAN_PROFILE_TYPES
        ],
    )


def __register_path_query(query_subparsers):
    command_parser = query_subparsers.add_parser("path")
    command_parser.set_defaults(query_func=__path_query, quiet=True)
    __register_common_command_options(command_parser)


def __register_version_query(query_subparsers):
    command_parser = query_subparsers.add_parser("version")
    command_parser.set_defaults(query_func=__version_query, quiet=True)
    __register_common_command_options(command_parser)


def __register_triplet_query(query_subparsers):
    command_parser = query_subparsers.add_parser("triplet")
    command_parser.set_defaults(query_func=__triplet_query, quiet=True)
    __register_common_command_options(command_parser)


def __register_wellknown_query(query_subparsers):
    command_parser = query_subparsers.add_parser("wk")
    command_parser.set_defaults(query_func=__wellknown_query, quiet=True)
    __register_common_command_options(command_parser)
    command_parser.add_argument(
        "wellknown", nargs="?", help="The wellknown to retrieve"
    )


def register(subparsers):
    command_parser = subparsers.add_parser("get")
    command_parser.set_defaults(func=__get_variable)
    query_subparsers = command_parser.add_subparsers(dest="query", required=True)

    __register_conan_query(query_subparsers)
    __register_path_query(query_subparsers)
    __register_version_query(query_subparsers)
    __register_triplet_query(query_subparsers)
    __register_wellknown_query(query_subparsers)
