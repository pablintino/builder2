import configparser
import os.path
import pathlib

import utils
import installation

__DEFAULT_CONAN_PROFILES_PATH = "/tools/conan/profiles"


def __get_conan_profiles_path():
    conan_profiles_path = os.environ.get(
        "BUILDER_CONAN_PROFILES_PATH", __DEFAULT_CONAN_PROFILES_PATH
    )
    return conan_profiles_path if conan_profiles_path else __DEFAULT_CONAN_PROFILES_PATH


def __prepare_common_profile_file(installation_info, compiler, release_type):
    config = configparser.ConfigParser()
    # Preserve uppercase
    config.optionxform = str

    config.add_section("env")
    config.add_section("build_requires")
    config.add_section("options")
    config.add_section("settings")

    compiler_installation_path = installation_info["path"]
    triplet = installation_info.get("triplet", "").split("-")
    if "triplet" not in installation_info or (len(triplet) != 3 and len(triplet) != 4):
        raise SystemExit(f"Compiler triplet empty or not recognised: {triplet}")

    config["settings"]["arch"] = triplet[0]
    config["settings"]["os"] = (
        triplet[1] if len(triplet) == 3 else triplet[2]
    ).capitalize()
    config["settings"]["compiler"] = compiler
    config["settings"]["compiler.version"] = (
        installation_info["version"].strip().split(".")[0]
    )
    config["settings"]["build_type"] = release_type

    compiler_bin_path = utils.get_compiler_binary_path(compiler_installation_path)
    if compiler == "clang":
        config["settings"]["compiler.libcxx"] = "libc++"
        config["env"]["CC"] = compiler_bin_path
        config["env"]["CXX"] = os.path.join(
            os.path.dirname(compiler_bin_path),
            os.path.basename(compiler_bin_path).replace("clang", "clang++"),
        )
    else:
        gcc_version_output = utils.check_output_compiler_reference_binary(
            installation_info["path"], "-v"
        )
        config["settings"]["compiler.libcxx"] = (
            "libstdc++11"
            if "--with-default-libstdcxx-abi=new" in gcc_version_output
            else "libstdc++"
        )
        config["env"]["CC"] = compiler_bin_path
        config["env"]["CXX"] = os.path.join(
            os.path.dirname(compiler_bin_path),
            os.path.basename(compiler_bin_path).replace("gcc", "g++"),
        )
    return config


def create_profiles_from_compiler(tool_key, tool_metadata, installation_info):
    tool_name = tool_metadata["name"]
    create_profiles_flag = tool_metadata.get("conan-profile", False)
    if create_profiles_flag and (tool_name == "clang" or tool_name == "gcc"):
        conan_profiles_path = __get_conan_profiles_path()
        # Create conan profiles dir if not exists
        pathlib.Path(conan_profiles_path).mkdir(parents=True, exist_ok=True)

        for release_type in ["Debug", "Release"]:
            config = __prepare_common_profile_file(
                installation_info, tool_name, release_type
            )
            profile_name = f"cpp-builder-{utils.replace_non_alphanumeric(tool_key, '-')}-{release_type.lower()}.profile"
            profile_path = os.path.join(conan_profiles_path, profile_name)
            with open(profile_path, "w") as configfile:
                config.write(configfile)

            # Add a custom env var that point to profile path
            profile_env_name = f"BUILDER_CONAN_PROFILE_{utils.replace_non_alphanumeric(tool_key, '_')}_{release_type}".upper()
            installation.add_custom_env_var(profile_env_name, profile_path)
