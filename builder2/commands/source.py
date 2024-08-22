import logging
import os
from typing import Dict

from dependency_injector.wiring import inject, Provide

import builder2.loggers
from builder2.commands import command_commons
from builder2.di import Container
from builder2.environment_builder import EnvironmentBuilder
from builder2.exceptions import BuilderException
from builder2.file_manager import FileManager

__logger = logging.getLogger(__name__)


def __generate_vars_content(variables: Dict[str, str]):
    # TODO Assume bash for the moment
    content = ""
    for name, value in variables.items():
        content = f'{content}{name}="{value}"\n'
        content = f"{content}export {name}\n"
    return content.strip("\n")


@inject
def __source(
    args,
    file_manager: FileManager = Provide[Container.file_manager],
    environment_builder: EnvironmentBuilder = Provide[Container.environment_builder],
):
    try:
        builder2.loggers.disable()

        installation_summary = command_commons.get_installation_summary_from_args(
            args, file_manager
        )
        env_vars = environment_builder.build_environment_variables(
            installation_summary,
            args.generate_vars,
            append=False,
            add_python_env=args.generate_python_vars,
        )
        source_content = __generate_vars_content(env_vars)
        if args.certs_dir and os.path.exists(args.certs_dir):
            source_content = f"{source_content}\nbuilder2 load-certificates --no-output --certs {args.certs_dir}"

        print(source_content)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("source")
    command_parser.set_defaults(func=__source)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_certificates_arg_option(command_parser)

    command_parser.add_argument(
        "--generate-vars",
        dest="generate_vars",
        action="store_true",
        help="Enable component generated environment variables",
    )
    command_parser.add_argument(
        "--generate-python-vars",
        dest="generate_python_vars",
        action="store_true",
        help="Enable python paths tweaking for builder2 venvs",
    )
