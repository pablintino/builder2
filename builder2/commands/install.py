import logging
import os

import marshmallow.exceptions

import conan_manager
import environment_builder
import file_utils
import loggers
import package_manager
import tool_installers
from commands import command_commons
from exceptions import BuilderException, BuilderValidationException
from execution_parameters import ExecutionParameters
from installation_summary import InstallationSummary
from models.metadata_models import ToolchainMetadataSchema

__logger = logging.getLogger()


def __load_toolchain_metadata(path):
    try:
        return ToolchainMetadataSchema().load(data=file_utils.read_json_file(path))
    except marshmallow.exceptions.ValidationError as err:
        raise BuilderValidationException('Validation issues in toolchain metadata', err.messages_dict)


def __install_components(components, execution_parameters, installation_summary):
    for component_key, component_config in components.items():
        with tool_installers.get_installer(component_key, component_config, execution_parameters) as installer:
            component_installation = installer.run_installation()
            installation_summary.add_component(component_key, component_installation)


def __install_system_packages(system_packages, installation_summary):
    package_manager.install_packages(system_packages)
    for package_name in system_packages:
        installation_summary.add_system_package(package_name)


def __install(args):
    execution_parameters = ExecutionParameters(
        target_dir=args.target_dir,
        file_name=args.filename,
        core_count=args.core_count,
        time_multiplier=args.timout_mult / 100.0
    )

    loggers.configure()

    try:
        toolchain_metadata = __load_toolchain_metadata(execution_parameters.file_name)
        installation_summary = InstallationSummary(installation_path=args.target_dir)

        __install_system_packages(toolchain_metadata.system_packages, installation_summary)
        __install_components(toolchain_metadata.components, execution_parameters, installation_summary)

        # Add conan profiles env vars and all component ones
        installation_summary.add_environment_variables(
            conan_manager.create_profiles_from_installation(installation_summary, args.target_dir))
        installation_summary.add_environment_variables(environment_builder.get_installation_vars(installation_summary))

        installation_summary.save(args.target_dir)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser('install')
    command_parser.set_defaults(func=__install)

    command_parser.add_argument('-f', '--file', dest='filename',
                                help='Path to the tools metadata descriptor file', required=True)
    command_parser.add_argument('-d', '--destination', dest='target_dir',
                                help='Path which tools will be deployed', required=True)

    command_parser.add_argument('-j', '--max-cpus', dest='core_count', type=int, default=os.cpu_count(),
                                help='Max core count to be used')
    command_parser.add_argument('-t', '--timeout-multiplier', dest='timout_mult', type=int, default=100,
                                help='Timeout increase by percentage for each operation')
