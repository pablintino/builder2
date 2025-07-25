import logging
import os
from typing import Dict

import builder2.loggers
from builder2 import constants
from builder2.commands import command_commons
import builder2.environment_builder
from builder2.exceptions import BuilderException

__logger = logging.getLogger(__name__)


def __generate_vars_content(variables: Dict[str, str]):
    # TODO Assume bash for the moment
    content = ""
    for name, value in variables.items():
        content = f'{content}{name}="{value}"\n'
        content = f"{content}export {name}\n"
    return content.strip("\n")


def __source(
    args,
):
    try:
        builder2.loggers.disable()

        installation_summary = command_commons.get_installation_summary_from_args(args)
        env_vars = builder2.environment_builder.build_environment_variables(
            installation_summary, args.generate_vars, append=False
        )
        source_content = __generate_vars_content(env_vars)
        if args.certs_dir and os.path.exists(args.certs_dir):
            source_content = f"{source_content}\nbuilder2 load-certificates --quiet --certs {args.certs_dir}"

        print(source_content)

    except BuilderException as err:
        command_commons.manage_builder_exceptions(err)


def register(subparsers):
    command_parser = subparsers.add_parser("source")
    command_parser.set_defaults(func=__source, generate_vars=False)
    command_commons.register_installation_summary_arg_option(command_parser)
    command_commons.register_certificates_arg_option(command_parser)

    command_parser.add_argument(
        "--generate-vars",
        dest="generate_vars",
        action="store_true",
        env_var=constants.ENV_VAR_GENERATE_VARS,
        help="Enable component generated environment variables",
    )
