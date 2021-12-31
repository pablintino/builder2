import json
import os
import utils

__DEFAULT_SUMMARY_FILE = "/tools/builder2/.installation.json"
__DEFAULT_ENVIRONMENT_FILE = "/tools/builder2/.env"

__installation_summary__ = {}
__extra_env_vars__ = {}


def __component_has_multiple_versions(components, component_key):
    component = components[component_key]
    # Filter components to only those that have the same same and are not the component_key
    for _, other_details in {
        key: value
        for (key, value) in components.items()
        if (key != component_key and value["name"] == component["name"])
    }.items():
        if (
            "triplet" in other_details
            and "triplet" in component
            and other_details["triplet"] == component["triplet"]
        ):
            # Multiple components with the same name and same triplet
            if component.get("version", None) != other_details.get("version", None):
                return True
        if ("triplet" not in other_details and "triplet" in component) or (
            "triplet" in other_details and "triplet" not in component
        ):
            # One contains triplet and the other not
            return True
        if "triplet" not in other_details and "triplet" not in component:
            # No triplet in both. Distinguish by version
            if component.get("version", None) != other_details.get("version", None):
                return True

    return False


def __get_compiler_triplet_from_config(component_data):
    if (
        "group" in component_data
        and "compilers" == component_data["group"]
        and "triplet" in component_data
    ):
        return component_data["triplet"].strip().replace("-", "_")

    return None


def __tool_has_no_alternatives(components, component_key, component_data):
    # Name is mandatory, but as this code is part of the init script I prefer to make is 'safe' and not break
    component_name = component_data.get("name", None)
    if component_name:
        for key, details in {
            k: v for k, v in components.items() if k != component_key
        }.items():
            if "name" in details and details["name"] == component_name:
                return False
        return True
    return False


def __get_summary_path():
    summary_path = os.environ.get(
        "BUILDER_INSTALLATION_SUMMARY_PATH", __DEFAULT_SUMMARY_FILE
    )
    return summary_path if summary_path else __DEFAULT_SUMMARY_FILE


def __get_environment_file_path():
    environment_file_path = os.environ.get(
        "BUILDER_ENVIRONMENT_PATH", __DEFAULT_ENVIRONMENT_FILE
    )
    return (
        environment_file_path if environment_file_path else __DEFAULT_ENVIRONMENT_FILE
    )


def __is_default_tool(component_data):
    installation_config = component_data.get("installation-config", None)
    return installation_config and installation_config.get("default", False)


def save_summary():
    global __installation_summary__
    summary_path = __get_summary_path()
    os.makedirs(os.path.dirname(summary_path), exist_ok=True)
    with open(summary_path, "w") as f:
        json.dump(__installation_summary__, f, indent=2)


def add_tool_to_summary(tool_key, tool_metadata):
    global __installation_summary__
    if "tools" not in __installation_summary__:
        __installation_summary__ = {"tools": {"components": {}}}
    __installation_summary__["tools"]["components"][tool_key] = tool_metadata


def add_custom_env_var(key, value):
    __extra_env_vars__[key] = value


def get_environment_definitions():
    global __installation_summary__
    definitions = {}
    if (
        __installation_summary__
        and "tools" in __installation_summary__
        and "components" in __installation_summary__["tools"]
    ):
        components = __installation_summary__["tools"]["components"]
        for component_key, component_data in components.items():
            suffix_version = __component_has_multiple_versions(
                components, component_key
            )
            component_path = component_data.get("path", None)
            if component_path and (
                not suffix_version or (suffix_version and "version" in component_data)
            ):
                compiler_string = (
                    __get_compiler_triplet_from_config(component_data) or ""
                )
                safe_key = utils.replace_non_alphanumeric(component_key, "_")
                component_name = utils.replace_non_alphanumeric(
                    component_data["name"], "_"
                )
                if suffix_version:
                    safe_version = utils.replace_non_alphanumeric(
                        component_data["version"].strip(), "_"
                    )
                    var_name = f"BUILDER_{safe_key}_{compiler_string}_{safe_version}_DIR".upper().replace(
                        "__", "_"
                    )
                    definitions[var_name] = component_path

                    # If flagged with "default" in metadata json add a simplified environment variable
                    if __is_default_tool(component_data):
                        var_name = f"BUILDER_{component_name}_DIR".upper().replace(
                            "__", "_"
                        )
                        definitions[var_name] = component_path
                else:
                    var_name = (
                        f"BUILDER_{safe_key}_{compiler_string}_DIR".upper().replace(
                            "__", "_"
                        )
                    )
                    definitions[var_name] = component_path

                    # If version is not mandatory is safe to add a simplified env var too based on name
                    var_name = f"BUILDER_{component_name}_{compiler_string}_DIR".upper().replace(
                        "__", "_"
                    )
                    definitions[var_name] = component_path

                    # If component is unique (no more versions or triplets) add a simple var that contains only its name
                    # Note: This applies to compilers only. Other tools already simplified by the previous variable
                    if compiler_string and __tool_has_no_alternatives(
                        components, component_key, component_data
                    ):
                        var_name = f"BUILDER_{component_name}_DIR".upper().replace(
                            "__", "_"
                        )
                        definitions[var_name] = component_path

    return definitions


def write_environment_file():
    with open(__get_environment_file_path(), "w") as f:
        merged_dict = dict(
            list(get_environment_definitions().items())
            + list(__extra_env_vars__.items())
        )
        for var_name, value in merged_dict.items():
            f.write(f"{var_name}={value}\n")
