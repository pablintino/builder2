import logging
import os

import marshmallow.exceptions
from dependency_injector.wiring import inject, Provide

import builder2.loggers
import builder2.environment_builder
from builder2.file_manager import FileManager
from builder2.di import Container
from builder2.package_manager import PackageManager
from builder2.commands import command_commons
from builder2.exceptions import BuilderException, BuilderValidationException
from builder2.installation_summary import InstallationSummary
from builder2.models.metadata_models import ToolchainMetadataSchema
from builder2.conan_manager import ConanManager

__logger = logging.getLogger(__name__)


def __load_toolchain_metadata(path, file_manager):
    try:
        return ToolchainMetadataSchema().load(data=file_manager.read_json_file(path))
    except marshmallow.exceptions.ValidationError as err:
        raise BuilderValidationException(
            "Validation issues in toolchain metadata", err.messages_dict
        )


def __install_components(components, target_dir, installation_summary):
    for component_key, component_config in components.items():
        with Container.tool_installers[type(component_config)](
            component_key, component_config, target_dir
        ) as installer:
            component_installation = installer.run_installation()
            installation_summary.add_component(component_key, component_installation)


def __install_system_packages(system_packages, installation_summary, package_manager):
    package_manager.install_packages(system_packages)
    installation_summary.add_system_packages(system_packages)


@inject
def __install(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    package_manager: PackageManager = Provide[Container.package_manager],
    conan_manager: ConanManager = Provide[Container.conan_manager],
    target_dir: str = Provide[Container.config.target_dir],
):
    builder2.loggers.configure()

    try:
        toolchain_metadata = __load_toolchain_metadata(args.filename, file_manager)
        installation_summary = InstallationSummary(file_manager)

        __install_system_packages(
            toolchain_metadata.system_packages, installation_summary, package_manager
        )
        __install_components(
            toolchain_metadata.components, target_dir, installation_summary
        )

        # Add conan profiles env vars and all component ones
        installation_summary.add_environment_variables(
            conan_manager.create_profiles_from_installation(
                installation_summary, target_dir
            )
        )
        installation_summary.add_environment_variables(
            builder2.environment_builder.get_installation_vars(installation_summary)
        )

        installation_summary.save(target_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("install")
    command_parser.set_defaults(func=__install)

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
