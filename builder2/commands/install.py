import logging
import os
import sys

import conan_manager
import file_utils
import environment_builder
import loggers
import package_manager
import tool_installers
from exceptions import BuilderException
from execution_parameters import ExecutionParameters
from installation_summary import InstallationSummary

__logger = logging.getLogger()


def __install_components(config, execution_parameters, installation_summary):
    for component_key, components_config in config.get("components", {}).items():
        with tool_installers.get_installer(component_key, components_config, execution_parameters) as installer:
            component_installation = installer.run_installation()
            installation_summary.add_component(component_installation)


def __install_system_packages(config, installation_summary):
    system_packages = config.get('system-packages', [])
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
        config = file_utils.read_json_file(execution_parameters.file_name)
        installation_summary = InstallationSummary(installation_path=args.target_dir)

        __install_system_packages(config, installation_summary)
        __install_components(config, execution_parameters, installation_summary)

        # Add conan profiles env vars and all component ones
        installation_summary.add_environment_variables(
            conan_manager.create_profiles_from_installation(installation_summary, args.target_dir))
        installation_summary.add_environment_variables(environment_builder.get_installation_vars(installation_summary))

        installation_summary.save(args.target_dir)

    except BuilderException as err:
        __logger.error(str(err.message))
        sys.exit(err.exit_code)


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
