import os
import pathlib
import typing

from builder2 import constants
from builder2.utils import replace_non_alphanumeric
from builder2.installation_summary import InstallationSummary


class EnvironmentBuilder:
    @staticmethod
    def __append_component_path_var(
        variables: typing.Dict[str, str],
        name: str,
        path: str,
        version: str = None,
        triplet: str = None,
        prefix=None,
        suffix=None,
    ):
        var_name = f"BUILDER_{name}"
        if prefix:
            var_name = var_name + f"_{prefix}"
        if triplet:
            var_name = var_name + f"_{triplet}"
        if version:
            var_name = var_name + f"_{version}"
        if suffix:
            var_name = var_name + f"_{suffix}"
        var_name = (var_name + "_DIR").upper()
        variables[var_name] = path

    @staticmethod
    def __insert_into_list_var(
        envs: typing.Dict[str, str], name: str, value: str
    ) -> typing.Dict[str, str]:
        content = envs.get(name, "").strip(os.pathsep).split(os.pathsep)
        content.insert(0, str(value))
        if content:
            # use a dict to remove duplications while preserving the order
            envs.update(
                {name: os.pathsep.join(list(dict.fromkeys(content))).strip(os.pathsep)}
            )
        return envs

    @classmethod
    def __set_paths(cls, installation_summary, envs: typing.Dict[str, str]):
        for component_installation in installation_summary.get_components().values():
            for paths in component_installation.path_dirs:
                cls.__insert_into_list_var(envs, "PATH", paths)

    @classmethod
    def __build_component_generated_variables(
        cls, installation_summary: InstallationSummary
    ) -> typing.Dict[str, str]:
        variables = {}
        for component_data in installation_summary.get_components().values():
            if component_data.path:

                sanitized_name = replace_non_alphanumeric(component_data.name, "_")
                component_versions = installation_summary.get_component_versions(
                    component_data.name
                )
                # If component has more than one version/arch or both
                if len(component_versions) > 1:

                    sanitized_version = replace_non_alphanumeric(
                        component_data.version, "_"
                    )
                    sanitized_triplet = replace_non_alphanumeric(
                        (
                            component_data.triplet
                            if component_data.triplet is not None
                            else ""
                        ),
                        "_",
                    )

                    # Add triplet only if multiple triplets are available for the component
                    all_same_triplet = all(
                        version[1] == component_versions[0][1]
                        for version in component_versions
                    )

                    # If there is only one version per arch don't add the version number
                    # to simplify names and made vars usable (without name change) between
                    # component version upgrades/downgrades
                    version_per_triplet = len(
                        [
                            version
                            for version in component_versions
                            if version[1] == component_data.triplet
                        ]
                    )

                    cls.__append_component_path_var(
                        variables,
                        sanitized_name,
                        component_data.path,
                        version=sanitized_version if version_per_triplet > 1 else None,
                        triplet=sanitized_triplet if not all_same_triplet else None,
                    )

                    # If flagged with "default" in metadata json add a simplified
                    # environment variable
                    if component_data.configuration.default:
                        cls.__append_component_path_var(
                            variables, sanitized_name, component_data.path
                        )

                    # Add full qualified variables pointing to conan profiles
                    for profile, profile_path in component_data.conan_profiles.items():
                        cls.__append_component_path_var(
                            variables,
                            sanitized_name,
                            profile_path,
                            version=(
                                sanitized_version if version_per_triplet > 1 else None
                            ),
                            triplet=sanitized_triplet if not all_same_triplet else None,
                            prefix="CONAN_PROFILE",
                            suffix=replace_non_alphanumeric(profile, "_"),
                        )
                else:
                    # Only one version of the component available. Env var simplified to name only
                    cls.__append_component_path_var(
                        variables, sanitized_name, component_data.path
                    )

                    # Add simplified variables pointing to conan profiles
                    for profile, profile_path in component_data.conan_profiles.items():
                        cls.__append_component_path_var(
                            variables,
                            sanitized_name,
                            profile_path,
                            prefix="CONAN_PROFILE",
                            suffix=replace_non_alphanumeric(profile, "_"),
                        )

        return variables

    @classmethod
    def __set_python_vars(
        cls,
        installation_summary: InstallationSummary,
        envs: typing.Dict[str, str],
        add_python_env: bool,
    ):
        base_path = pathlib.Path(installation_summary.path).parent
        component_envs = {
            base_path.joinpath(name, ".venv"): data
            for name, data in installation_summary.get_components().items()
            if data.configuration.add_to_path
        }

        # Add the global venv
        cls.__set_python_env_vars(envs, base_path.joinpath(".venv"), add_python_env)

        for path in component_envs.keys():
            cls.__set_python_env_vars(envs, path, add_python_env)

    @classmethod
    def __set_python_env_vars(
        cls, envs: typing.Dict[str, str], path: pathlib.Path, add_python_env: bool
    ):
        if not path.exists():
            return
        site_packages = next(path.rglob("**/site-packages"), None)
        bins_path = path.joinpath("bin")
        if site_packages and bins_path.exists():
            cls.__insert_into_list_var(envs, "PATH", str(bins_path))
            if add_python_env:
                cls.__insert_into_list_var(envs, "PYTHONPATH", str(site_packages))

    @classmethod
    def build_environment_variables(
        cls,
        installation_summary: InstallationSummary,
        generate_variables: bool,
        append: bool = True,
        add_python_env: bool = False,
    ):
        variables = os.environ.copy() if append else {}
        for installation in installation_summary.get_components().values():
            variables.update(installation.environment_vars)
        variables.update(installation_summary.get_environment_variables())

        # Replace PATH with its value plus the paths in the summary
        cls.__set_paths(installation_summary, variables)
        cls.__set_python_vars(installation_summary, variables, add_python_env)

        # Add generated environment variables only if desired
        if generate_variables:
            variables.update(
                cls.__build_component_generated_variables(installation_summary)
            )

        # If the builder installation path env var is not present add it
        # to simplify other commands after bootstrapped
        if constants.INSTALLATION_SUMMARY_ENV_VAR not in variables:
            variables[constants.INSTALLATION_SUMMARY_ENV_VAR] = (
                installation_summary.path
            )

        # Add a prefix to the shell to make obvious that the shell is bootstrapped
        if constants.SHELL_PROMPT_FORMAT_ENV_VAR in variables:
            variables[constants.SHELL_PROMPT_FORMAT_ENV_VAR] = (
                f"[b] {variables[constants.SHELL_PROMPT_FORMAT_ENV_VAR]}"
            )

        return variables
