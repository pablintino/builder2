import math
import os
import re


def replace_non_alphanumeric(string, replace):
    return re.sub("[^\\da-zA-Z]+", replace, string) if string else string


def get_version_from_cmake_cache(cmake_cache_file, version_var=None):
    if os.path.exists(cmake_cache_file):
        with open(cmake_cache_file) as f:
            for line in f:
                if line.startswith(
                        "CMAKE_PROJECT_VERSION:" if not version_var else f"{version_var}:"
                ):
                    parts = line.strip().split("=")
                    if len(parts) > 1:
                        return parts[-1].strip()
    return None


def get_version_from_cmake_file(file, variable):
    if os.path.exists(file):
        with open(file) as f:
            for line in f:
                if line.startswith(("set", "SET")) and variable in line:
                    parts = line.strip().split(" ")
                    if len(parts) > 1:
                        return parts[-1].strip().replace('"', "").replace(")", "")
    return None


def get_command_timeout(reference_timeout, timeout_multiplier):
    return int(math.ceil(timeout_multiplier * reference_timeout)) if timeout_multiplier > 1.0 else reference_timeout
