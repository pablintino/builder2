import abc
import logging
import os
import pathlib
import re
import shutil
import sys
import tempfile
import typing
from urllib.parse import urlparse

import builder2.environment_builder
import builder2.file_manager
import builder2.utils
import builder2.command_line
import builder2.tools.compilers_support
import builder2.cryptographic_provider
from builder2.exceptions import BuilderException
from builder2.models.cli_models import CliInstallArgs
from builder2.models.installation_models import (
    ComponentInstallationModel,
    PipPackageInstallationModel,
)
from builder2.models.metadata_models import (
    AptPackageInstallationConfiguration,
    BasePackageInstallationConfiguration,
    PipPackageInstallationConfiguration,
    BaseComponentConfiguration,
)
from builder2.package_manager import PackageManager
from builder2.python_manager import PythonManager
from builder2.tools import ansible_support
from builder2.tools.compilers_support import EXEC_NAME_GCC_CC, EXEC_NAME_CLANG_CC
from builder2.tools.java_support import DIR_NAME_JAVA_HOME


class ToolInstaller(metaclass=abc.ABCMeta):
    def __init__(
        self,
        tool_key: str,
        target_path: str,
        config: BaseComponentConfiguration,
        cli_config: CliInstallArgs,
        *args,
        python_manager: PythonManager = None,
        package_manager: PackageManager = None,
        create_target: bool = True,
        known_executables: typing.List[str] = None,
        **kwargs,
    ):
        self.tool_key = tool_key
        self._config = config
        self._installation_base = target_path
        self._package_manager = package_manager
        self._temp_dir = None
        self._sources_dir = None
        self._version = None
        self._package_hash = None
        self._wellknown_paths = {}
        self._component_env_vars = {}
        self._path_directories = []
        self._executables_dir = (
            self._config.executables_dir
            if self._config.executables_dir is not None
            else kwargs.get("executables_dir", "bin")
        )
        self._known_executables = (self._config.known_executables or []) + (
            known_executables or []
        )

        self._core_count: int = cli_config.core_count or 10
        self._timeout_multiplier: float = (cli_config.timeout_multiplier or 100) / 100.0
        self._logger = logging.getLogger(self.__class__.__name__)

        # If tool is in a group install in their directory
        if self._config.group:
            self._target_dir = os.path.join(
                self._installation_base, self._config.group, self.tool_key
            )
        else:
            self._target_dir = os.path.join(self._installation_base, self.tool_key)

        if create_target and not os.path.exists(self._target_dir):
            os.makedirs(self._target_dir, exist_ok=True)

        self._tool_python_manager = python_manager.get_create_env(
            pathlib.Path(self._target_dir),
            self.tool_key,
            depends_on=self._config.depends_on,
            create_venv=self._config.use_venv,
        )

    def __enter__(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        return self

    def __exit__(self, exception_type, value, traceback):
        self._temp_dir.cleanup()
        if exception_type and self._target_dir and os.path.exists(self._target_dir):
            shutil.rmtree(self._target_dir, ignore_errors=True)

    def _create_component_installation(self) -> ComponentInstallationModel:
        tool_path = self._compute_tool_path()
        return ComponentInstallationModel(
            name=self._config.name,
            aliases=self._config.aliases,
            version=self._version,
            path=str(tool_path),
            package_hash=self._package_hash,
            configuration=self._config,
            wellknown_paths=self._wellknown_paths,
            environment_vars=self._component_env_vars,
            path_dirs=self._path_directories if self._config.add_to_path else [],
        )

    def _compute_tool_version(self):
        if not self._config.version:
            raise BuilderException(
                f"Cannot determine component version. Component key: {self.tool_key}"
            )
        self._version = self._config.version

    def _compute_tool_path(self) -> pathlib.Path:
        if not os.path.exists(self._target_dir):
            raise BuilderException(
                f"Cannot determine the tool path. Component key: {self.tool_key}"
            )
        return self._target_dir

    def _acquire_sources(self):
        parsed_url = urlparse(self._config.url)
        sources_archive_path = os.path.join(
            self._temp_dir.name, os.path.basename(parsed_url.path)
        )
        builder2.file_manager.download_file(self._config.url, sources_archive_path)

        if self._config.expected_hash:
            builder2.cryptographic_provider.validate_file_hash(
                sources_archive_path, self._config.expected_hash
            )

        self._sources_dir = builder2.file_manager.extract_file(
            sources_archive_path, self._temp_dir.name
        )
        self._package_hash = builder2.cryptographic_provider.compute_file_sha1(
            sources_archive_path
        )

    def _acquire_packages(self):
        self._package_manager.install_packages(
            self._config.required_packages + self._compute_tool_packages(),
            python_manager=self._tool_python_manager,
        )

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:
        return []

    def _compute_wellknown_paths(self):
        for executable in self._known_executables:
            executable_path = (
                pathlib.Path(self._target_dir)
                .joinpath(self._executables_dir)
                .joinpath(executable)
            )
            if executable_path.is_file():
                if not builder2.file_manager.file_is_executable(executable_path):
                    builder2.file_manager.make_file_executable(executable_path)
                self._wellknown_paths[executable] = str(executable_path.absolute())

    def _compute_component_env_vars(self):
        # Defaults to the already created empty dict
        pass

    def _compute_path_directories(self):
        # Adds /bin if exists
        bin_path = pathlib.Path(self._target_dir).joinpath(self._executables_dir)
        if bin_path.exists() and bin_path.is_dir():
            self._path_directories.append(str(bin_path.absolute()))

    def run_installation(self) -> ComponentInstallationModel:
        self._acquire_packages()
        self._compute_tool_version()
        self._compute_wellknown_paths()
        self._compute_component_env_vars()
        self._compute_path_directories()
        return self._create_component_installation()


class ToolSourceInstaller(ToolInstaller):
    def __init__(
        self,
        *args,
        in_source_build: bool = False,
        timeouts: typing.Tuple[int, int, int] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._build_dir = None
        self._in_source_build = in_source_build
        self._timeouts = timeouts or (300, 900, 300)

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
            os.makedirs(build_path, exist_ok=True)
            cwd = self._build_dir

        builder2.command_line.run_process(
            cmd,
            cwd=self._sources_dir if not cwd else cwd,
            timeout=builder2.utils.get_command_timeout(
                timeout if timeout else self._timeouts[0], self._timeout_multiplier
            ),
            # If command is a string use shell mode
            # (typical cmake cases as it has problems detecting -D opts)
            shell=shell or (isinstance(cmd, str) and shell is None),
        )

    def _build(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        builder2.command_line.run_process(
            self._create_build_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=builder2.utils.get_command_timeout(
                timeout if timeout else self._timeouts[1], self._timeout_multiplier
            ),
            shell=shell,
        )

    def _install(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        builder2.command_line.run_process(
            self._create_install_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=builder2.utils.get_command_timeout(
                timeout if timeout else self._timeouts[2], self._timeout_multiplier
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

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, known_executables=["cmake"], timeouts=(300, 1800, 300), **kwargs
        )

    def _compute_tool_version(self):
        version_files = builder2.file_manager.search_get_files_by_pattern(
            self._sources_dir, ["**/cmVersionConfig.h"]
        )
        if version_files:
            self._version = builder2.file_manager.read_file_and_search_group(
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

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:

        return [
            AptPackageInstallationConfiguration(
                name="build-essential", build_transient=True, post_installation=[]
            ),
            AptPackageInstallationConfiguration(
                name="libssl-dev", build_transient=False, post_installation=[]
            ),
        ]


class GccSourcesInstaller(ToolSourceInstaller):
    __BUILD_DEPENDENCIES = [
        "bison",
        "flex",
        "build-essential",
        "bzip2",
        "autotools-dev",
        "curl",
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, in_source_build=True, timeouts=(300, 3000, 300), **kwargs
        )

    def __get_gcc_source_version(self):
        gcc_version_file = os.path.join(self._sources_dir, "gcc", "BASE-VER")
        return builder2.file_manager.read_file_as_text(gcc_version_file).strip()

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

        arq_guess = builder2.command_line.run_process(
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
        summary = super()._create_component_installation()
        summary.triplet = builder2.command_line.run_process(
            [self._wellknown_paths[EXEC_NAME_GCC_CC], "-dumpmachine"]
        ).strip()

        return summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            builder2.tools.compilers_support.get_gcc_wellknown_paths(self._target_dir)
        )

    def _configure_pre_hook(self):
        # Download required libs before start configuration
        builder2.command_line.run_process(
            ["contrib/download_prerequisites"], cwd=self._sources_dir, timeout=1800
        )

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:

        return [
            AptPackageInstallationConfiguration(
                name=dep, build_transient=True, post_installation=[]
            )
            for dep in self.__BUILD_DEPENDENCIES
        ] + [
            AptPackageInstallationConfiguration(
                name="zlib1g-dev", build_transient=False, post_installation=[]
            )
        ]


class ClangSourcesInstaller(ToolSourceInstaller):
    __CMAKE_FILE_PATTERN = re.compile(
        r"CMAKE_PROJECT_VERSION:[a-zA-Z\d]*=([a-zA-Z\d.]*)", re.IGNORECASE
    )

    __BUILD_DEPENDENCIES = ["cmake", "build-essential", "ninja-build"]

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args, in_source_build=True, timeouts=(300, 3600, 300), **kwargs
        )

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
        self._version = builder2.file_manager.read_file_and_search_group(
            cmake_cache, self.__CMAKE_FILE_PATTERN, ignore_failure=True
        )

        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        summary = super()._create_component_installation()

        # Remember. This ic GCC native, but clang implements the command as well
        # Note: Keep in mind that clang itself could not be present if not selected to be compiled: Optional
        clang_bin_path = self._wellknown_paths.get(EXEC_NAME_CLANG_CC, None)
        if clang_bin_path:
            summary.triplet = builder2.tools.compilers_support.get_compiler_triplet(
                clang_bin_path
            )

        return summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            builder2.tools.compilers_support.get_clang_wellknown_paths(self._target_dir)
        )

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:

        return [
            AptPackageInstallationConfiguration(
                name=dep,
                post_installation=[],
                build_transient=True,
            )
            for dep in self.__BUILD_DEPENDENCIES
        ]


class CppCheckSourcesInstaller(ToolSourceInstaller):
    __VERSION_FILE_PATTERN = re.compile(
        r'SET\(VERSION\s?"([a-zA-Z\d.]*)"\)', re.IGNORECASE | re.MULTILINE
    )
    __CMAKE_FILE_PATTERN = re.compile(
        r"^CMAKE_PROJECT_VERSION:[a-zA-Z\d]*=([a-zA-Z\d.]*)$",
        re.IGNORECASE | re.MULTILINE,
    )

    __BUILD_DEPENDENCIES = ["cmake", "build-essential", "ninja-build"]

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            known_executables=["cppcheck"],
            **kwargs,
        )

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
        self._version = builder2.file_manager.read_file_and_search_group(
            cmake_versions_file, self.__VERSION_FILE_PATTERN, ignore_failure=True
        )
        if not self._version:
            cmake_cache = os.path.join(self._sources_dir, "CMakeCache.txt")
            self._version = builder2.file_manager.read_file_and_search_group(
                cmake_cache, self.__CMAKE_FILE_PATTERN, ignore_failure=True
            )

        if not self._version:
            super()._compute_tool_version()

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:

        packages = [
            AptPackageInstallationConfiguration(
                name=dep,
                post_installation=[],
                build_transient=True,
            )
            for dep in self.__BUILD_DEPENDENCIES
        ]

        # Add libpcre3 if rules compilation requested
        packages += (
            [
                AptPackageInstallationConfiguration(
                    name="libpcre3", post_installation=[], build_transient=False
                ),
                AptPackageInstallationConfiguration(
                    name="libpcre3-dev", post_installation=[], build_transient=False
                ),
            ]
            if self._config.compile_rules
            else []
        )

        return packages


class ValgrindSourcesInstaller(ToolSourceInstaller):
    __SPEC_FILE__PATTERN = re.compile(r"Version:\s?([a-zA-Z\d.]*)", re.IGNORECASE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, known_executables=["valgrind"], **kwargs)

    def _compute_tool_version(self):
        spec_file = os.path.join(self._sources_dir, "valgrind.spec")
        self._version = builder2.file_manager.read_file_and_search_group(
            spec_file, self.__SPEC_FILE__PATTERN, ignore_failure=True
        )

        if not self._version:
            super()._compute_tool_version()

    def _compute_tool_packages(
        self,
    ) -> typing.List[BasePackageInstallationConfiguration]:
        return [
            AptPackageInstallationConfiguration(
                name="build-essential",
                post_installation=[],
                build_transient=True,
            ),
            AptPackageInstallationConfiguration(
                name="libc6-dbg",
                post_installation=[],
                build_transient=False,
            ),
        ]


class DownloadOnlySourcesInstaller(ToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, create_target=False, **kwargs)

    def run_installation(self) -> ComponentInstallationModel:
        self._acquire_sources()
        self._acquire_packages()
        shutil.copytree(self._sources_dir, self._target_dir)

        # Discover paths before trying to fetch compiler version
        self._compute_wellknown_paths()
        self._compute_tool_version()
        self._compute_component_env_vars()
        self._compute_path_directories()
        return self._create_component_installation()


class DownloadOnlyCompilerInstaller(DownloadOnlySourcesInstaller):
    def __get_binary_path(self):
        if EXEC_NAME_CLANG_CC in self._wellknown_paths:
            return self._wellknown_paths[EXEC_NAME_CLANG_CC]
        if EXEC_NAME_GCC_CC in self._wellknown_paths:
            return self._wellknown_paths[EXEC_NAME_GCC_CC]

        return None

    def _compute_tool_version(self):
        binary = self.__get_binary_path()
        if binary:
            self._version = builder2.command_line.run_process(
                [binary, "-dumpversion"]
            ).strip()

        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        summary = super()._create_component_installation()
        summary.triplet = builder2.tools.compilers_support.get_compiler_triplet(
            self.__get_binary_path()
        )
        return summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            builder2.tools.compilers_support.get_gcc_wellknown_paths(self._target_dir)
        )
        self._wellknown_paths.update(
            builder2.tools.compilers_support.get_clang_wellknown_paths(self._target_dir)
        )


class JdkInstaller(DownloadOnlySourcesInstaller):
    __JAVA_RELEASE_FILE_VERSION_REGEX = re.compile('JAVA_VERSION="([\\d.-_+a-zA-Z]*)"')

    def _compute_tool_version(self):
        # Try get version from jdk files
        self._version = builder2.file_manager.read_file_and_search_group(
            os.path.join(self._target_dir, "release"),
            self.__JAVA_RELEASE_FILE_VERSION_REGEX,
            ignore_failure=True,
        )
        if not self._version:
            version_file_content = builder2.file_manager.read_file_as_text(
                os.path.join(self._target_dir, "version.txt"), ignore_failure=True
            )
            if version_file_content:
                self._version = version_file_content.strip()

        if not self._version:
            super()._compute_tool_version()

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(
            builder2.tools.java_support.get_jdk_wellknown_paths(self._target_dir)
        )

    def _compute_component_env_vars(self):
        if self._config.default and DIR_NAME_JAVA_HOME in self._wellknown_paths:
            self._component_env_vars["JAVA_HOME"] = self._wellknown_paths[
                DIR_NAME_JAVA_HOME
            ]


class MavenInstaller(DownloadOnlySourcesInstaller):
    __VERSION_REGEX = re.compile(r"Implementation-Version:\s?([\d.]*)")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, known_executables=["mvn"], **kwargs)

    def _compute_tool_version(self):
        files = builder2.file_manager.search_get_files_by_pattern(
            self._target_dir, ["lib/maven-artifact-*.jar"], recursive=False
        )
        if files:
            manifest_content = builder2.file_manager.read_text_file_from_zip(
                files[0], "META-INF/MANIFEST.MF", ignore_failure=True
            )
            if manifest_content:
                match = self.__VERSION_REGEX.search(manifest_content)
                self._version = match.group(1) if match else None

        if not self._version:
            super()._compute_tool_version()


class PipBasedToolInstaller(ToolInstaller):
    def __init__(self, *args, entry_points_package: str = None, **kwargs):
        super().__init__(*args, create_target=False, **kwargs)
        self._entry_points_package = entry_points_package
        self._pip_install_report = None
        self._pip_package_path = None
        self.python_bin = sys.executable

    def _acquire_packages(self):
        # Call the parent method first to install early dependencies if required
        super()._acquire_packages()
        install_config = PipPackageInstallationConfiguration(
            name=self._config.name,
            version=self._config.version,
            index=self._config.url,
            force=True,
        )
        self._pip_install_report = self._tool_python_manager.install_pip_package(
            install_config
        )
        if self._pip_install_report:
            self._package_hash = self._pip_install_report.pip_hash
            self._pip_package_path = pathlib.Path(self._pip_install_report.location)

    def _compute_tool_version(self):
        if (
            self._config.version
            and self._pip_install_report.version != self._config.version
        ):
            raise BuilderException(
                f"Unable to gather the specified package version {self._config.version}."
                f" Component key: {self.tool_key}"
            )
        self._version = self._pip_install_report.version
        if not self._version:
            super()._compute_tool_version()

    def _compute_tool_path(self) -> pathlib.Path:
        if self._pip_package_path:
            return self._pip_package_path
        return super()._compute_tool_path()

    def _compute_wellknown_paths(self):
        if self._pip_package_path:
            pip_entry_points = (
                self._tool_python_manager.fetch_entry_points(self._pip_package_path)
                or {}
            )
            self._wellknown_paths.update(pip_entry_points)


class AnsibleInstaller(PipBasedToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            entry_points_package="ansible-core",
            **kwargs,
        )
        self._runner_install_report: typing.Optional[PipPackageInstallationModel] = None

    def _acquire_packages(self):
        super()._acquire_packages()
        if self._config.runner and self._config.runner.install:
            self._runner_install_report = self._tool_python_manager.install_pip_package(
                PipPackageInstallationConfiguration(
                    name="ansible-runner",
                    version=self._config.runner.version,
                    index=self._config.runner.index,
                    force=True,
                    build_transient=False,
                ),
            )

    def _compute_wellknown_paths(self):
        super()._compute_wellknown_paths()
        if self._config.runner and self._config.runner.install:
            pip_entry_points = (
                self._tool_python_manager.fetch_entry_points(
                    pathlib.Path(self._runner_install_report.location)
                )
                or {}
            )
            self._wellknown_paths.update(pip_entry_points)


class AnsibleCollectionInstaller(ToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, create_target=False, **kwargs)
        self._install_report = None

    def _acquire_packages(self):
        # Call the parent method first to install early dependencies if required
        super()._acquire_packages()

        collection_dir = pathlib.Path(self._temp_dir.name)
        installer = ansible_support.AnsibleCollectionInstaller(
            collection_dir,
            self._tool_python_manager,
        )
        self._install_report = installer.install(
            url=self._config.url,
            name=self._config.name,
            install_requirements=self._config.install_requirements,
            requirements_patterns=self._config.req_regexes,
            system_wide=self._config.system_wide,
        )
        self._package_hash = self._install_report.main_collection.package_hash

    def _compute_tool_version(self):
        if (
            self._config.version
            and self._install_report.main_collection.version != self._config.version
        ):
            raise BuilderException(
                f"Unable to gather the specified collection version {self._config.version}."
                f" Component key: {self.tool_key}"
            )
        self._version = self._install_report.main_collection.version
        if not self._version:
            super()._compute_tool_version()

    def _compute_tool_path(self) -> pathlib.Path:
        if (
            self._install_report
            and self._install_report.main_collection.collection_path
        ):
            collection_path = self._install_report.main_collection.collection_path
            if collection_path.is_dir():
                return collection_path
        return super()._compute_tool_path()
