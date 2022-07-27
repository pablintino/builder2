import utils


def __append_component_path_var(variables, name: str, path: str, version: str = None, triplet: str = None):
    var_name = f'BUILDER_{name}'
    if triplet:
        var_name = var_name + f'_{triplet}'
    if version:
        var_name = var_name + f'_{version}'
    var_name = (var_name + '_DIR').upper()
    variables[var_name] = path


def get_installation_vars(installation_summary):
    variables = {}
    for _, component_data in installation_summary.get_components().items():
        if component_data.path:

            sanitized_name = utils.replace_non_alphanumeric(component_data.name, "_")
            component_versions = installation_summary.get_component_versions(component_data.name)
            # If component has more than one version/arch or both
            if len(component_versions) > 1:

                sanitized_version = utils.replace_non_alphanumeric(component_data.version, "_")
                sanitized_triplet = utils.replace_non_alphanumeric(
                    component_data.triplet if component_data.triplet is not None else "", "_")

                # Add triplet only if multiple triplets are available for the component
                all_same_triplet = all(
                    version[1] == component_versions[0][1] for version in component_versions)

                # If there is only one version per arch don't add the version number to simplify names and
                # made vars usable (without name change) between component version upgrades/downgrades
                version_per_triplet = len(
                    [version for version in component_versions if version[1] == component_data.triplet])

                __append_component_path_var(variables, sanitized_name, component_data.path,
                                            version=sanitized_version if version_per_triplet > 1 else None,
                                            triplet=sanitized_triplet if not all_same_triplet else None)

                # If flagged with "default" in metadata json add a simplified environment variable
                if component_data.configuration.default:
                    __append_component_path_var(variables, sanitized_name, component_data.path)

            else:
                # Only one version of the component available. Env var simplified to name only
                __append_component_path_var(variables, sanitized_name, component_data.path)

    return variables
