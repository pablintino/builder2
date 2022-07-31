import configparser
import os.path

import utils
from command_line import CommandRunner
from file_manager import FileManager
import tools.compilers_support
from exceptions import BuilderException
from installation_summary import InstallationSummary
from models.metadata_models import GccBuildConfiguration, ClangBuildConfiguration


class ConanManager:

    def __init__(self, file_manager: FileManager, command_runner: CommandRunner):
        self._file_manager = file_manager
        self._command_runner = command_runner

    @staticmethod
    def __prepare_common_profile_file(component_installation, release_type):
        config = configparser.ConfigParser()
        # Preserve uppercase
        config.optionxform = str

        config.add_section("env")
        config.add_section("build_requires")
        config.add_section("options")
        config.add_section("settings")

        triplet = component_installation.triplet.split("-") if component_installation.triplet else None
        if len(triplet) != 3 and len(triplet) != 4:
            raise BuilderException(f"Compiler triplet empty or not recognised: {triplet}")

        config["settings"]["arch"] = triplet[0]
        config["settings"]["os"] = (
            triplet[1] if len(triplet) == 3 else triplet[2]
        ).capitalize()

        config["settings"]["compiler.version"] = (
            component_installation.version.strip().split(".")[0]
        )
        config["settings"]["build_type"] = release_type

        return config

    @staticmethod
    def __prepare_clang_profile_file(component_installation, config_parser):
        clang_path = component_installation.wellknown_paths.get(tools.compilers_support.EXEC_NAME_CLANG_CC,
                                                                None)
        if not clang_path:
            raise BuilderException('Cannot determine clang executable path to create conan profile')
        clang_cpp_path = component_installation.wellknown_paths.get(
            tools.compilers_support.EXEC_NAME_CLANG_CXX, None)
        if not clang_cpp_path:
            raise BuilderException('Cannot determine clang++ executable path to create conan profile')

        config_parser["settings"]["compiler.libcxx"] = "libc++"
        config_parser["env"]["CC"] = clang_path
        config_parser["env"]["CXX"] = clang_cpp_path
        config_parser["settings"]["compiler"] = 'clang'

        return config_parser

    def __prepare_gcc_profile_file(self, component_installation, config_parser):
        gcc_path = component_installation.wellknown_paths.get(tools.compilers_support.EXEC_NAME_GCC_CC, None)
        if not gcc_path:
            raise BuilderException('Cannot determine gcc executable path to create conan profile')
        gpp_path = component_installation.wellknown_paths.get(tools.compilers_support.EXEC_NAME_GCC_CXX, None)
        if not gpp_path:
            raise BuilderException('Cannot determine g++ executable path to create conan profile')

        config_parser["env"]["CC"] = gcc_path
        config_parser["env"]["CXX"] = gpp_path
        config_parser["settings"]["compiler"] = 'gcc'

        gcc_version_output = self._command_runner.run_process([gcc_path, '-v'])
        config_parser["settings"]["compiler.libcxx"] = (
            "libstdc++11"
            if "--with-default-libstdcxx-abi=new" in gcc_version_output
            else "libstdc++"
        )

        return config_parser

    def create_profiles_from_installation(self, installation_summary: InstallationSummary, target_dir: str):
        profile_vars = {}
        for component_key, component_installation in installation_summary.get_components().items():

            is_gcc = isinstance(installation_summary, GccBuildConfiguration)
            is_clang = isinstance(installation_summary, ClangBuildConfiguration)

            if (is_gcc or is_clang) and installation_summary.conan_profile:

                conan_profiles_path = os.path.join(target_dir, 'conan', 'profiles')
                # Create conan profiles dir if not exists
                self._file_manager.create_file_tree(conan_profiles_path)

                for release_type in ["Debug", "Release"]:
                    config_parser = self.__prepare_common_profile_file(component_installation, release_type)
                    if is_clang:
                        config_parser = self.__prepare_clang_profile_file(component_installation, config_parser)
                    else:
                        config_parser = self.__prepare_gcc_profile_file(component_installation, config_parser)

                    profile_name = f"cpp-builder-{utils.replace_non_alphanumeric(component_key, '-')}" \
                                   f"-{release_type.lower()}.profile"
                    profile_path = os.path.join(conan_profiles_path, profile_name)
                    with open(profile_path, "w") as configfile:
                        config_parser.write(configfile)

                    # Add a custom env var that point to profile path
                    profile_env_name = f"BUILDER_CONAN_PROFILE_{utils.replace_non_alphanumeric(component_key, '_')}" \
                                       f"_{release_type}".upper()
                    profile_vars[profile_env_name] = profile_path

        return profile_vars
