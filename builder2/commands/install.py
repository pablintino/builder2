import logging
import os
import pathlib
import typing
from typing import Dict

import marshmallow.exceptions
from dependency_injector.wiring import inject, Provide

import builder2.loggers
import builder2.environment_builder
from builder2.file_manager import FileManager
from builder2.di import Container, container_instance
from builder2.package_manager import PackageManager
from builder2.commands import command_commons
from builder2.exceptions import BuilderException, BuilderValidationException
from builder2.installation_summary import InstallationSummary
from builder2.models.metadata_models import (
    ToolchainMetadataConfigurationSchema,
    ToolchainMetadataConfiguration,
    BaseComponentConfiguration,
)
from builder2.conan_manager import ConanManager

__logger = logging.getLogger(__name__)


def __load_toolchain_metadata(path, file_manager) -> ToolchainMetadataConfiguration:
    try:
        return ToolchainMetadataConfigurationSchema().load(
            data=file_manager.read_json_file(pathlib.Path(path).absolute())
        )
    except FileNotFoundError as err:
        raise BuilderException(
            f"Toolchain metadata file '{path}' not found", exit_code=2
        ) from err
    except marshmallow.exceptions.ValidationError as err:
        raise BuilderValidationException(
            "Validation issues in toolchain metadata", err.messages_dict
        ) from err


def __sort_components_stack(
    components_dependencies_graph, graph_iface, visited, components_stack
):
    visited.append(graph_iface)

    element = components_dependencies_graph[graph_iface]
    if element and element not in visited:
        __sort_components_stack(
            components_dependencies_graph, element, visited, components_stack
        )
    components_stack.append(graph_iface)


def __sort_components(
    component_configs: typing.Dict[str, BaseComponentConfiguration]
) -> typing.Dict[str, BaseComponentConfiguration]:
    # Prepare the dependency graph
    components_dependencies_graph = {}
    components_graph_set = set()

    for name, data in component_configs.items():
        if name not in components_dependencies_graph:
            components_dependencies_graph[name] = None
        components_dependencies_graph[name] = data.depends_on
        components_graph_set.add(name)

    visited = []
    components_stack = []
    for graph_iface in components_graph_set:
        if graph_iface not in visited:
            __sort_components_stack(
                components_dependencies_graph,
                graph_iface,
                visited,
                components_stack,
            )

    return {name: component_configs[name] for name in components_stack}


def __install_components(
    components: Dict[str, BaseComponentConfiguration],
    target_dir: str,
    installation_summary: InstallationSummary,
    conan_manager: ConanManager,
):
    for component_key, component_config in __sort_components(components).items():
        with container_instance.tool_installers(
            type(component_config).__name__, component_key, component_config, target_dir
        ) as installer:
            installation_model = installer.run_installation()
            conan_manager.add_profiles_to_component(
                component_key,
                installation_model,
                target_dir,
            )
            installation_summary.add_component(component_key, installation_model)


@inject
def __install(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    package_manager: PackageManager = Provide[Container.package_manager],
    conan_manager: ConanManager = Provide[Container.conan_manager],
    target_dir: str = Provide[Container.config.target_dir],
):
    builder2.loggers.configure("INFO" if not args.quiet else "ERROR")

    try:
        toolchain_metadata = __load_toolchain_metadata(args.filename, file_manager)
        installation_summary = InstallationSummary(file_manager)

        # Install globally declared packages
        package_manager.install_packages(toolchain_metadata.packages)

        __install_components(
            toolchain_metadata.components,
            target_dir,
            installation_summary,
            conan_manager,
        )

        installation_summary.add_environment_variables(
            toolchain_metadata.global_variables
        )

        # Ensure build transient packages are removed before saving the installation summary
        package_manager.cleanup()

        installation_summary.add_packages(
            list(package_manager.get_installed_packages())
        )

        installation_summary.save(target_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("install")
    command_parser.set_defaults(func=__install, quiet=False)

    command_parser.add_argument(
        "-f",
        "--file",
        dest="filename",
        help="Path to the tools metadata descriptor file",
        required=True,
    )
    command_parser.add_argument(
        "-d",
        "--destination",
        dest="target_dir",
        help="Path which tools will be deployed",
        required=True,
    )
    command_parser.add_argument(
        "--quiet",
        dest="quiet",
        action="store_true",
        help="Disable all no error logs",
    )
    command_parser.add_argument(
        "-j",
        "--max-cpus",
        dest="core_count",
        type=int,
        default=os.cpu_count(),
        help="Max core count to be used",
    )
    command_parser.add_argument(
        "-t",
        "--timeout-multiplier",
        dest="timout_mult",
        type=int,
        default=100,
        help="Timeout increase by percentage for each operation",
    )
