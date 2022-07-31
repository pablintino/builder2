import abc
import dataclasses
import logging
import os
import pathlib
import re
import tempfile
from urllib.parse import urlparse

import utils
from command_line import CommandRunner
from cryptographic_provider import CryptographicProvider
from exceptions import BuilderException
from file_manager import FileManager
from models.installation_models import ComponentInstallationModel
from package_manager import PackageManager
from tools import CompilersSupport, JavaTools
from tools.compilers_support import EXEC_NAME_GCC_CC, EXEC_NAME_CLANG_CC
from tools.java_support import DIR_NAME_JAVA_HOME


class ToolInstaller(metaclass=abc.ABCMeta):
    def __init__(self, *args, **kwargs):
        self.tool_key = args[0]
        self._config = args[1]
        self._installation_base = args[2]
        self._temp_dir = None
        self._sources_dir = None
        self._version = None
        self._package_hash = None
        self._wellknown_paths = {}
        self._component_env_vars = {}
        self._path_directories = []

        self._file_manager: FileManager = kwargs.get("file_manager")
        self._cryptographic_provider: CryptographicProvider = kwargs.get("cryptographic_provider")
        self._command_runner: CommandRunner = kwargs.get("command_runner")
        self._package_manager: PackageManager = kwargs.get("package_manager")
        self._core_count: int = kwargs.get("core_count", 10)
        self._time_multiplier: float = kwargs.get("time_multiplier", 100) / 100.0
        self._logger = logging.getLogger(self.__class__.__name__)

        # If tool is in a group install in their directory
        if self._config.group:
            self._target_dir = os.path.join(
                self._installation_base, self._config.group, self.tool_key
            )
        else:
            self._target_dir = os.path.join(self._installation_base, self.tool_key)

        if kwargs.get("create_target", True) and not os.path.exists(self._target_dir):
            self._file_manager.create_file_tree(self._target_dir)

    def __enter__(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        return self

    def __exit__(self, exception_type, value, traceback):
        self._temp_dir.cleanup()
        if exception_type and self._target_dir and os.path.exists(self._target_dir):
            self._file_manager.delete_file_tree(self._target_dir)

    def _create_component_installation(self):
        return ComponentInstallationModel(
            name=self._config.name,
            version=self._version,
            path=self._target_dir,
            package_hash=self._package_hash,
            configuration=self._config,
            wellknown_paths=self._wellknown_paths,
            environment_vars=self._component_env_vars,
            path_dirs=self._path_directories if self._config.add_to_path else [],
        )

    def _compute_tool_version(self):
        if not self._config.version:
            BuilderException(
                f"Cannot determine component version. Component key: {self.tool_key}"
            )
        self._version = self._config.version

    def _acquire_sources(self):
        parsed_url = urlparse(self._config.url)
        sources_tar_path = os.path.join(
            self._temp_dir.name, os.path.basename(parsed_url.path)
        )
        self._file_manager.download_file(self._config.url, sources_tar_path)

        if self._config.expected_hash:
            self._cryptographic_provider.validate_file_hash(
                sources_tar_path, self._config.expected_hash
            )

        self._sources_dir = self._file_manager.extract_file(
            sources_tar_path, self._temp_dir.name
        )
        self._package_hash = self._cryptographic_provider.compute_file_sha1(
            sources_tar_path
        )

    def _acquire_packages(self):
        self._package_manager.install_packages(self._config.required_packages)

    def _compute_wellknown_paths(self):
        # Defaults to the already created empty dict
        pass

    def _compute_component_env_vars(self):
        # Defaults to the already created empty dict
        pass

    def _compute_path_directories(self):
        # Adds /bin if exists
        bin_path = pathlib.Path(self._target_dir).joinpath("bin")
        if bin_path.exists() and bin_path.is_dir():
            self._path_directories.append(str(bin_path.absolute()))

    @abc.abstractmethod
    def run_installation(self) -> ComponentInstallationModel:
        pass


class ToolSourceInstaller(ToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._build_dir = None
        self._in_source_build = kwargs.get("in_source_build", False)
        self._timeouts = kwargs.get("timeouts", (300, 900, 300))

    def _create_config_cmd(self):
        return [
            os.path.join(self._sources_dir, "configure"),
            f"--prefix={self._target_dir}",
        ]

    def _create_build_cmd(self):
        return ["make"]

    def _create_install_cmd(self):
        return ["make", "install"]

    def _configure(self, timeout=None, directory=None, shell=None):
        cmd = self._create_config_cmd()
        cwd = directory
        if self._in_source_build:
            self._build_dir = build_path = os.path.join(self._temp_dir.name, "build")
            self._file_manager.create_file_tree(build_path)
            cwd = self._build_dir

        self._command_runner.run_process(
            cmd,
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(
                timeout if timeout else self._timeouts[0], self._time_multiplier
            ),
            # If command is a string (typical cmake cases as it has problems detecting -D opts) use shell mode
            shell=shell or (isinstance(cmd, str) and shell is None),
        )

    def _build(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        self._command_runner.run_process(
            self._create_build_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(
                timeout if timeout else self._timeouts[1], self._time_multiplier
            ),
            shell=shell,
        )

    def _install(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        self._command_runner.run_process(
            self._create_install_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(
                timeout if timeout else self._timeouts[2], self._time_multiplier
            ),
            shell=shell,
        )

    def _configure_pre_hook(self):
        pass

    def run_installation(self) -> ComponentInstallationModel:
        self._acquire_sources()
        self._acquire_packages()
        self._configure_pre_hook()
        self._configure()
        self._build()
        self._install()
        self._compute_tool_version()
        self._compute_wellknown_paths()
        self._compute_component_env_vars()
        self._compute_path_directories()
        return self._create_component_installation()


class CMakeSourcesInstaller(ToolSourceInstaller):
    __VERSION_REGEX = re.compile(r'CMake_VERSION\s"([a-zA-Z\d.]*)"')

    def _compute_tool_version(self):
        version_files = self._file_manager.search_get_files_by_pattern(
            self._sources_dir, ["**/cmVersionConfig.h"]
        )
        if version_files:
            self._version = self._file_manager.read_file_and_search_group(
                version_files[0], self.__VERSION_REGEX, ignore_failure=True
            )

        if not self._version:
            super()._compute_tool_version()

    def _create_config_cmd(self):
        return [
            os.path.join(self._sources_dir, "bootstrap"),
            f"--parallel={self._core_count}",
            f"--prefix={self._target_dir}",
        ]


class GccSourcesInstaller(ToolSourceInstaller):
    def __init__(self, *args, compilers_support: CompilersSupport = None, **kwargs):
        super().__init__(
            *args, in_source_build=True, timeouts=(300, 2000, 300), **kwargs
        )
        self._compilers_support = compilers_support

    def __get_gcc_source_version(self):
        gcc_version_file = os.path.join(self._sources_dir, "gcc", "BASE-VER")
        return self._file_manager.read_file_as_text(gcc_version_file).strip()

    def __get_gcc_custom_build_opts(self):
        reserved = ("--target", "--host", "--build", "--enable-languages", "--prefix")
        return [x for x in self._config.config_opts if not x.startswith(reserved)]

    def _create_config_cmd(self):
        opts = []
        if self._config.suffix_version:
            gcc_version = self.__get_gcc_source_version()
            self._logger.info("GCC version read from sources: %s", gcc_version)
            suffix = f"-{gcc_version.rsplit('.', 1)[0] if gcc_version.endswith('.0') else gcc_version}"
            self._logger.info("GCC executables suffixed with: %s", suffix)
            opts.append(f"--program-suffix={suffix}")
        else:
            self._logger.info("GCC executables will not be suffixed")

        arq_guess = self._command_runner.run_process(
            ["./config.guess"], cwd=self._sources_dir
        ).strip()
        self._logger.info("GCC config.guess result: %s", arq_guess)

        languages = (
            ",".join(map(str, self._config.languages))
            if self._config.languages
            else "c,c++"
        )
        self._logger.info("GCC configured languages: %s", languages)

        self._logger.info("GCC installation path: %s", self._target_dir)

        opts.extend(
            [
                f"--build={arq_guess}",
                f"--host={arq_guess}",
                f"--target={arq_guess}",
                f"--prefix={self._target_dir}",
                f"--enable-languages={languages}",
            ]
        )
        opts.extend(self.__get_gcc_custom_build_opts())
        self._logger.info("GCC configure options: %s", " ".join(map(str, opts)))

        command = [os.path.join(self._sources_dir, "configure")]
        command.extend(opts)
        return command

    def _create_build_cmd(self):
        return ["make", "-j", f"{self._core_count}"]

    def _create_install_cmd(self):
        return ["make", "install-strip"]

    def _compute_tool_version(self):
        version = self.__get_gcc_source_version()
        if version:
            self._version = version
        else:
            super()._compute_tool_version()

    def _create_component_installation(self):
        base_summary = super()._create_component_installation()
        target_triplet = self._command_runner.run_process(
            [self._wellknown_paths[EXEC_NAME_GCC_CC], "-dumpmachine"]
        ).strip()
        return dataclasses.replace(base_summary, triplet=target_triplet)

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            self._compilers_support.get_gcc_wellknown_paths(self._target_dir)
        )

    def _configure_pre_hook(self):
        # Download required libs before start configuration
        self._command_runner.run_process(
            ["contrib/download_prerequisites"], cwd=self._sources_dir, timeout=1800
        )


class ClangSourcesInstaller(ToolSourceInstaller):
    __CMAKE_FILE_PATTERN = re.compile(
        r"CMAKE_PROJECT_VERSION:[a-zA-Z\d]*=([a-zA-Z\d.]*)", re.IGNORECASE
    )

    def __init__(self, *args, compilers_support: CompilersSupport = None, **kwargs):
        super().__init__(
            *args, in_source_build=True, timeouts=(300, 3400, 300), **kwargs
        )
        self._compilers_support = compilers_support

    def __get_clang_custom_build_opts(self):
        reserved = (
            "-DCMAKE_BUILD_TYPE",
            "-DLLVM_ENABLE_PROJECTS",
            "-DCMAKE_INSTALL_PREFIX",
            "-DLLVM_ENABLE_RUNTIMES",
        )
        return [x for x in self._config.config_opts if not x.startswith(reserved)]

    def _create_config_cmd(self):
        opts = [
            os.path.join(self._sources_dir, "llvm"),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f'-DCMAKE_INSTALL_PREFIX="{self._target_dir}"',
        ]

        llvm_modules = (
            ";".join(map(str, self._config.modules))
            if self._config.modules
            else "clang,clang-tools-extra"
        )
        self._logger.info("Clang/LLVM configured with this modules: %s", llvm_modules)
        opts.append(f'-DLLVM_ENABLE_PROJECTS="{llvm_modules}"')

        if self._config.runtimes:
            llvm_runtimes = ";".join(map(str, self._config.runtimes))
            self._logger.info(
                "Clang/LLVM configured with this runtimes: %s", llvm_runtimes
            )
            opts.append(f'-DLLVM_ENABLE_RUNTIMES="{llvm_runtimes}"')

        opts.extend(self.__get_clang_custom_build_opts())
        command = ["cmake"]
        command.extend(opts)

        # Little hack as CMake seems to be ignoring -D opts. Command is called in shell mode
        return " ".join(map(str, command))

    def _create_build_cmd(self):
        return ["ninja", "-j", f"{self._core_count}"]

    def _create_install_cmd(self):
        return ["ninja", "install"]

    def _compute_tool_version(self):
        cmake_cache = os.path.join(self._temp_dir.name, "build/CMakeCache.txt")
        self._version = self._file_manager.read_file_and_search_group(
            cmake_cache, self.__CMAKE_FILE_PATTERN, ignore_failure=True
        )

        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        base_summary = super()._create_component_installation()

        # Remember. This ic GCC native, but clang implements the command as well
        # Note: Keep in mind that clang itself could not be present if not selected to be compiled: Optional
        clang_bin_path = self._wellknown_paths.get(EXEC_NAME_CLANG_CC, None)
        if clang_bin_path:
            return dataclasses.replace(
                base_summary,
                triplet=self._compilers_support.get_compiler_triplet(clang_bin_path),
            )
        else:
            return base_summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            self._compilers_support.get_clang_wellknown_paths(self._target_dir)
        )


class CppCheckSourcesInstaller(ToolSourceInstaller):
    __VERSION_FILE_PATTERN = re.compile(
        r'SET\(VERSION\s?"([a-zA-Z\d.]*)"\)', re.IGNORECASE
    )
    __CMAKE_FILE_PATTERN = re.compile(
        r"^CMAKE_PROJECT_VERSION:[a-zA-Z\d]*=([a-zA-Z\d.]*)$", re.IGNORECASE
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _create_config_cmd(self):
        command = [
            "cmake",
            self._sources_dir,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f'-DCMAKE_INSTALL_PREFIX="{self._target_dir}"',
        ]

        if self._config.compile_rules:
            command.append("-DHAVE_RULES=True")

        # Little hack as CMake seems to be ignoring -D opts. Command is called in shell mode
        return " ".join(map(str, command))

    def _create_build_cmd(self):
        return ["ninja", "-j", f"{self._core_count}"]

    def _create_install_cmd(self):
        return ["ninja", "install"]

    def _compute_tool_version(self):
        cmake_versions_file = os.path.join(self._sources_dir, "cmake", "versions.cmake")
        self._version = self._file_manager.read_file_and_search_group(
            cmake_versions_file, self.__VERSION_FILE_PATTERN, ignore_failure=True
        )
        if not self._version:
            cmake_cache = os.path.join(self._sources_dir, "CMakeCache.txt")
            self._version = self._file_manager.read_file_and_search_group(
                cmake_cache, self.__CMAKE_FILE_PATTERN, ignore_failure=True
            )

        if not self._version:
            super()._compute_tool_version()

    def _configure_pre_hook(self):
        # Hardcoded mandatory dependencies if rules are compiled
        if self._config.compile_rules:
            self._package_manager.install_packages(["libpcre3", "libpcre3-dev"])


class ValgrindSourcesInstaller(ToolSourceInstaller):
    __SPEC_FILE__PATTERN = re.compile(r"Version:\s?([a-zA-Z\d.]*)", re.IGNORECASE)

    def _compute_tool_version(self):
        spec_file = os.path.join(self._sources_dir, "valgrind.spec")
        self._version = self._file_manager.read_file_and_search_group(
            spec_file, self.__SPEC_FILE__PATTERN, ignore_failure=True
        )

        if not self._version:
            super()._compute_tool_version()


class DownloadOnlySourcesInstaller(ToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, create_target=False, **kwargs)

    def run_installation(self) -> ComponentInstallationModel:
        self._acquire_sources()
        self._acquire_packages()
        self._file_manager.copy_file_tree(self._sources_dir, self._target_dir)

        # Discover paths before trying to fetch compiler version
        self._compute_wellknown_paths()
        self._compute_tool_version()
        self._compute_component_env_vars()
        self._compute_path_directories()
        return self._create_component_installation()


class DownloadOnlyCompilerInstaller(DownloadOnlySourcesInstaller):
    def __init__(self, *args, compilers_support: CompilersSupport = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._compilers_support = compilers_support

    def __get_binary_path(self):
        if EXEC_NAME_CLANG_CC in self._wellknown_paths:
            return self._wellknown_paths[EXEC_NAME_CLANG_CC]
        elif EXEC_NAME_GCC_CC in self._wellknown_paths:
            return self._wellknown_paths[EXEC_NAME_GCC_CC]

        return None

    def _compute_tool_version(self):
        binary = self.__get_binary_path()
        if binary:
            self._version = self._command_runner.run_process(
                [binary, "-dumpversion"]
            ).strip()

        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        base_summary = super()._create_component_installation()

        binary = self.__get_binary_path()
        return (
            dataclasses.replace(
                base_summary,
                triplet=self._compilers_support.get_compiler_triplet(binary),
            )
            if binary
            else base_summary
        )

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            self._compilers_support.get_gcc_wellknown_paths(self._target_dir)
        )
        self._wellknown_paths.update(
            self._compilers_support.get_clang_wellknown_paths(self._target_dir)
        )


class JdkInstaller(DownloadOnlySourcesInstaller):
    __JAVA_RELEASE_FILE_VERSION_REGEX = re.compile('JAVA_VERSION="([\\d.]*)"')

    def __init__(self, *args, java_tools: JavaTools = None, **kwargs):
        super().__init__(*args, **kwargs)
        self._java_tools = java_tools

    def _compute_tool_version(self):
        # Try get version from jdk files
        self._version = self._file_manager.read_file_and_search_group(
            os.path.join(self._target_dir, "release"),
            self.__JAVA_RELEASE_FILE_VERSION_REGEX,
            ignore_failure=True,
        )
        if not self._version:
            version_file_content = self._file_manager.read_file_as_text(
                os.path.join(self._target_dir, "version.txt"), ignore_failure=True
            )
            if version_file_content:
                self._version = version_file_content.strip()

        if not self._version:
            super()._compute_tool_version()

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            self._java_tools.get_jdk_wellknown_paths(self._target_dir)
        )

    def _compute_component_env_vars(self):
        if self._config.default and DIR_NAME_JAVA_HOME in self._wellknown_paths:
            self._component_env_vars["JAVA_HOME"] = self._wellknown_paths[
                DIR_NAME_JAVA_HOME
            ]


class MavenInstaller(DownloadOnlySourcesInstaller):
    __VERSION_REGEX = re.compile(r"Implementation-Version:\s?([\d.]*)")

    def _compute_tool_version(self):

        files = self._file_manager.search_get_files_by_pattern(
            self._target_dir, ["lib/maven-artifact-*.jar"], recursive=False
        )
        if files:
            manifest_content = self._file_manager.read_text_file_from_zip(
                files[0], "META-INF/MANIFEST.MF", ignore_failure=True
            )
            if manifest_content:
                match = self.__VERSION_REGEX.search(manifest_content)
                self._version = match.group(1) if match else None

        if not self._version:
            super()._compute_tool_version()
