import logging
import os
import pathlib
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
    ToolchainMetadataSchema,
    ToolchainMetadataConfiguration,
    BaseComponentConfiguration,
)
from builder2.conan_manager import ConanManager

__logger = logging.getLogger(__name__)


def __load_toolchain_metadata(path, file_manager) -> ToolchainMetadataConfiguration:
    try:
        return ToolchainMetadataSchema().load(
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


def __install_components(
    components: Dict[str, BaseComponentConfiguration],
    target_dir: str,
    installation_summary: InstallationSummary,
    conan_manager: ConanManager,
):
    for component_key, component_config in components.items():
        with container_instance.tool_installers(
            type(component_config).__name__, component_key, component_config, target_dir
        ) as installer:
            component_installation = installer.run_installation()
            conan_manager.add_profiles_to_component(
                component_key, component_installation, target_dir
            )
            installation_summary.add_component(component_key, component_installation)


@inject
def __install(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    package_manager: PackageManager = Provide[Container.package_manager],
    conan_manager: ConanManager = Provide[Container.conan_manager],
    target_dir: str = Provide[Container.config.target_dir],
):
    builder2.loggers.configure("INFO" if args.output else "ERROR")

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
        package_manager.clean_transient()

        installation_summary.add_packages(
            list(package_manager.installed_packages.values())
        )

        installation_summary.save(target_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("install")
    command_parser.set_defaults(func=__install, output=True)

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
        "--no-output",
        dest="output",
        action="store_false",
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
