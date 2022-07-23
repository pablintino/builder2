import abc
import dataclasses
import logging
import os
import pathlib
import shutil
import tempfile
from urllib.parse import urlparse

import command_line
import compilers_support
import crypto_utils
import file_utils
import java_support
import package_manager
import utils
from exceptions import BuilderException
from installation_summary import ComponentInstallation


@dataclasses.dataclass
class ToolInstallationResult:
    success: bool
    installation: ComponentInstallation = None
    error: BaseException = None


class ToolInstaller(metaclass=abc.ABCMeta):
    def __init__(self, *args, **kwargs):
        self.tool_key = args[0]
        self._config = args[1]
        self._execution_parameters = args[2]
        self._url = self._config.get("url", None)
        self._expected_hash = self._config.get("expected-hash", None)
        self._temp_dir = None
        self._sources_dir = None
        self._version = None
        self._package_hash = None
        self._wellknown_paths = {}
        self._component_env_vars = {}
        self._logger = logging.getLogger(self.__class__.__name__)

        if not self._url:
            raise BuilderException(f"Tool url is mandatory. Tool key:{self.tool_key}")

        self.name = self._config.get("name", None)
        if not self.name:
            raise BuilderException(f"Tool name is mandatory. Tool key:{self.tool_key}")

        # If tool is in a group install in their directory
        if "group" in self._config and self._config["group"]:
            self._target_dir = os.path.join(self._execution_parameters.target_dir, self._config["group"], self.tool_key)
        else:
            self._target_dir = os.path.join(self._execution_parameters.target_dir, self.tool_key)

        if kwargs.get('create_target', True) and not os.path.exists(self._target_dir):
            pathlib.Path(self._target_dir).mkdir(parents=True, exist_ok=True)

    def __enter__(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        return self

    def __exit__(self, exception_type, value, traceback):
        self._temp_dir.cleanup()
        if exception_type and self._target_dir and os.path.exists(self._target_dir):
            shutil.rmtree(self._target_dir, ignore_errors=True)

    def _create_component_installation(self):
        return ComponentInstallation(
            name=self.name,
            version=self._version,
            path=self._target_dir,
            key=self.tool_key,
            type=self._config["type"],
            package_hash=self._package_hash,
            default=self._config.get('default', False),
            configuration=self._config,
            wellknown_paths=self._wellknown_paths,
            environment_vars=self._component_env_vars
        )

    def _compute_tool_version(self):
        if "version" not in self._config:
            BuilderException(
                f"Cannot determine component version. Component key: {self.tool_key}"
            )
        self._version = self._config["version"]

    def _acquire_sources(self):
        parsed_url = urlparse(self._url)
        sources_tar_path = os.path.join(
            self._temp_dir.name, os.path.basename(parsed_url.path)
        )
        file_utils.download_file(self._url, sources_tar_path)

        if self._expected_hash:
            crypto_utils.validate_file_hash(sources_tar_path, self._expected_hash)

        self._sources_dir = file_utils.extract_file(sources_tar_path, self._temp_dir.name)
        self._package_hash = crypto_utils.compute_file_sha1(sources_tar_path)

    def _acquire_packages(self):
        packages = self._config.get("required-packages", [])
        if type(packages) is list and packages:
            package_manager.install_packages(packages)

    def _compute_wellknown_paths(self):
        # Defaults to the already created empty dict
        pass

    def _compute_component_env_vars(self):
        # Defaults to the already created empty dict
        pass

    @abc.abstractmethod
    def run_installation(self) -> ComponentInstallation:
        pass


class ToolSourceInstaller(ToolInstaller):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._build_dir = None
        self._in_source_build = kwargs.get('in_source_build', False)
        self._timeouts = kwargs.get('timeouts', (300, 900, 300))

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
            os.mkdir(build_path)
            cwd = self._build_dir

        command_line.run_process(
            cmd,
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(timeout if timeout else self._timeouts[0],
                                              self._execution_parameters.time_multiplier),
            # If command is a string (typical cmake cases as it has problems detecting -D opts) use shell mode
            shell=shell or (isinstance(cmd, str) and shell is None),
        )

    def _build(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        command_line.run_process(
            self._create_build_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(timeout if timeout else self._timeouts[1],
                                              self._execution_parameters.time_multiplier),
            shell=shell,
        )

    def _install(self, timeout=None, directory=None, shell=False):
        cwd = self._build_dir if self._in_source_build else directory
        command_line.run_process(
            self._create_install_cmd(),
            cwd=self._sources_dir if not cwd else cwd,
            timeout=utils.get_command_timeout(timeout if timeout else self._timeouts[2],
                                              self._execution_parameters.time_multiplier),
            shell=shell,
        )

    def _configure_pre_hook(self):
        pass

    def run_installation(self) -> ComponentInstallation:
        try:
            self._acquire_sources()
            self._acquire_packages()
            self._configure_pre_hook()
            self._configure()
            self._build()
            self._install()
            self._compute_tool_version()
            self._compute_wellknown_paths()
            self._compute_component_env_vars()
            return self._create_component_installation()

        # TODO Reduce exception scope to something not too wide
        except BaseException as e:
            raise BuilderException(f'Error installing {self.tool_key} component') from e


class CMakeSourcesInstaller(ToolSourceInstaller):
    def _compute_tool_version(self):
        for match in pathlib.Path(self._sources_dir).glob("**/cmVersionConfig.h"):
            with open(match.absolute()) as f:
                for line in f:
                    # Trailing space forces that CMake_VERSION is the whole variable name
                    if "CMake_VERSION " in line:
                        parts = line.split(" ")
                        if len(parts) == 3:
                            self._version = parts[2].replace('"', "").strip()
                            return

        super()._compute_tool_version()

    def _create_config_cmd(self):
        return [
            os.path.join(self._sources_dir, "bootstrap"),
            f"--parallel={self._execution_parameters.core_count}",
            f"--prefix={self._target_dir}",
        ]


class GccSourcesInstaller(ToolSourceInstaller):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, in_source_build=True, timeouts=(300, 2000, 300), **kwargs)

    def __get_gcc_source_version(self):
        with open(os.path.join(self._sources_dir, "gcc", "BASE-VER")) as ver_file:
            return ver_file.readline().strip()

    def __get_gcc_custom_build_opts(self):
        opts = self._config.get("config-opts", [])
        reserved = ("--target", "--host", "--build", "--enable-languages", "--prefix")
        return [x for x in opts if not x.startswith(reserved)]

    def _create_config_cmd(self):
        opts = []
        if self._config.get("suffix-version", False):
            gcc_version = self.__get_gcc_source_version()
            self._logger.info("GCC version read from sources: %s", gcc_version)
            suffix = f"-{gcc_version.rsplit('.', 1)[0] if gcc_version.endswith('.0') else gcc_version}"
            self._logger.info("GCC executables suffixed with: %s", suffix)
            opts.append(f"--program-suffix={suffix}")
        else:
            self._logger.info("GCC executables will not be suffixed")

        arq_guess = command_line.run_process(
            ["./config.guess"], cwd=self._sources_dir
        ).strip()
        self._logger.info("GCC config.guess result: %s", arq_guess)

        languages = (
            ",".join(map(str, self._config["languages"]))
            if "languages" in self._config
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
        return ["make", "-j", f"{self._execution_parameters.core_count}"]

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
        target_triplet = command_line.run_process(
            [self._wellknown_paths[compilers_support.EXEC_NAME_GCC_CC], '-dumpmachine']).strip()
        return dataclasses.replace(base_summary, triplet=target_triplet)

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(compilers_support.get_gcc_wellknown_paths(self._target_dir))

    def _configure_pre_hook(self):
        # Download required libs before start configuration
        command_line.run_process(
            ["contrib/download_prerequisites"], cwd=self._sources_dir, timeout=1800
        )


class ClangSourcesInstaller(ToolSourceInstaller):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, in_source_build=True, timeouts=(300, 3400, 300), **kwargs)

    def __get_clang_custom_build_opts(self):
        opts = self._config.get("config-opts", [])
        reserved = (
            "-DCMAKE_BUILD_TYPE",
            "-DLLVM_ENABLE_PROJECTS",
            "-DCMAKE_INSTALL_PREFIX",
            "-DLLVM_ENABLE_RUNTIMES",
        )
        return [x for x in opts if not x.startswith(reserved)]

    def _create_config_cmd(self):
        opts = [
            os.path.join(self._sources_dir, "llvm"),
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f'-DCMAKE_INSTALL_PREFIX="{self._target_dir}"',
        ]

        llvm_modules = (
            ";".join(map(str, self._config["modules"]))
            if "modules" in self._config
            else "clang,clang-tools-extra"
        )
        self._logger.info("Clang/LLVM configured with this modules: %s", llvm_modules)
        opts.append(f'-DLLVM_ENABLE_PROJECTS="{llvm_modules}"')

        config_runtimes = self._config.get("runtimes", [])
        if config_runtimes:
            llvm_runtimes = ";".join(map(str, config_runtimes))
            self._logger.info("Clang/LLVM configured with this runtimes: %s", llvm_runtimes)
            opts.append(f'-DLLVM_ENABLE_RUNTIMES="{llvm_runtimes}"')

        opts.extend(self.__get_clang_custom_build_opts())
        command = ["cmake"]
        command.extend(opts)

        # Little hack as CMake seems to be ignoring -D opts. Command is called in shell mode
        return " ".join(map(str, command))

    def _create_build_cmd(self):
        return ["ninja", "-j", f"{self._execution_parameters.core_count}"]

    def _create_install_cmd(self):
        return ["ninja", "install"]

    def _compute_tool_version(self):
        self._version = utils.get_version_from_cmake_cache(
            os.path.join(self._temp_dir.name, "build", "CMakeCache.txt")
        )
        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        base_summary = super()._create_component_installation()

        # Remember. This ic GCC native, but clang implements the command as well
        # Note: Keep in mind that clang itself could not be present if not selected to be compiled: Optional
        clang_bin_path = self._wellknown_paths.get(compilers_support.EXEC_NAME_CLANG_CC, None)
        if clang_bin_path:
            return dataclasses.replace(
                base_summary,
                triplet=compilers_support.get_compiler_triplet(clang_bin_path)
            )
        else:
            return base_summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(compilers_support.get_clang_wellknown_paths(self._target_dir))


class CppCheckSourcesInstaller(ToolSourceInstaller):
    def _create_config_cmd(self):
        command = [
            "cmake",
            self._sources_dir,
            "-G",
            "Ninja",
            "-DCMAKE_BUILD_TYPE=Release",
            f'-DCMAKE_INSTALL_PREFIX="{self._target_dir}"',
        ]
        compile_rules = self._config.get("compile-rules", True)
        if compile_rules:
            command.append("-DHAVE_RULES=True")

        # Little hack as CMake seems to be ignoring -D opts. Command is called in shell mode
        return " ".join(map(str, command))

    def _create_build_cmd(self):
        return ["ninja", "-j", f"{self._execution_parameters.core_count}"]

    def _create_install_cmd(self):
        return ["ninja", "install"]

    def _compute_tool_version(self):
        self._version = utils.get_version_from_cmake_file(
            os.path.join(self._sources_dir, "cmake", "versions.cmake"), "VERSION"
        )
        if not self._version:
            self._version = utils.get_version_from_cmake_cache(
                os.path.join(self._sources_dir, "CMakeCache.txt")
            )
        if not self._version:
            super()._compute_tool_version()

    def _configure_pre_hook(self):
        # Hardcoded mandatory dependencies if rules are compiled
        if self._config.get("compile-rules", True):
            package_manager.install_packages(["libpcre3", "libpcre3-dev"])


class ValgrindSourcesInstaller(ToolSourceInstaller):
    def _compute_tool_version(self):
        spec_file = os.path.join(self._sources_dir, "valgrind.spec")
        if os.path.exists(spec_file):
            with open(spec_file) as f:
                for line in f:
                    if line.startswith("Version:"):
                        parts = line.split(" ")
                        if len(parts) == 2:
                            self._version = parts[1].strip()
                            return

        super()._compute_tool_version()


class CopyOnlySourcesInstaller(ToolInstaller):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, create_target=False, **kwargs)

    def run_installation(self) -> ComponentInstallation:
        try:
            self._acquire_sources()
            self._acquire_packages()
            shutil.copytree(self._sources_dir, self._target_dir)

            # Discover paths before trying to fetch compiler version
            self._compute_wellknown_paths()
            self._compute_tool_version()
            self._compute_component_env_vars()
            return self._create_component_installation()

            # TODO Reduce exception scope to something not too wide¡
        except BaseException as e:
            raise BuilderException(f'Error installing {self.tool_key} component') from e


class DownloadOnlyCompilerInstaller(CopyOnlySourcesInstaller):

    def __get_binary_path(self):
        if compilers_support.EXEC_NAME_CLANG_CC in self._wellknown_paths:
            return self._wellknown_paths[compilers_support.EXEC_NAME_CLANG_CC]
        elif compilers_support.EXEC_NAME_GCC_CC in self._wellknown_paths:
            return self._wellknown_paths[compilers_support.EXEC_NAME_GCC_CC]

        return None

    def _compute_tool_version(self):
        binary = self.__get_binary_path()
        if binary:
            self._version = command_line.run_process([binary, '-dumpversion']).strip()

        if not self._version:
            super()._compute_tool_version()

    def _create_component_installation(self):
        base_summary = super()._create_component_installation()

        binary = self.__get_binary_path()
        return dataclasses.replace(base_summary,
                                   triplet=compilers_support.get_compiler_triplet(binary)) if binary else base_summary

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(compilers_support.get_gcc_wellknown_paths(self._target_dir))
        self._wellknown_paths.update(compilers_support.get_clang_wellknown_paths(self._target_dir))


class JdkInstaller(CopyOnlySourcesInstaller):
    def _compute_tool_version(self):
        # Try get version from jdk files
        self._version = java_support.get_jdk_version(self._target_dir)
        if not self._version:
            super()._compute_tool_version()

    def _compute_wellknown_paths(self):
        self._wellknown_paths.update(java_support.get_jdk_wellknown_paths(self._target_dir))

    def _compute_component_env_vars(self):
        if self._config.get("default", False) and java_support.DIR_NAME_JAVA_HOME in self._wellknown_paths:
            self._component_env_vars['JAVA_HOME'] = self._wellknown_paths[java_support.DIR_NAME_JAVA_HOME]


def get_installer(tool_key, config, execution_parameters):
    installer_type = config["type"]
    return __INSTALLERS[installer_type](tool_key, config, execution_parameters)


__INSTALLERS = {
    "gcc-build": GccSourcesInstaller,
    "cmake-build": CMakeSourcesInstaller,
    "download-only": CopyOnlySourcesInstaller,
    "cppcheck-build": CppCheckSourcesInstaller,
    "generic-build": ToolSourceInstaller,
    "clang-build": ClangSourcesInstaller,
    "valgrind-build": ValgrindSourcesInstaller,
    "download-only-compiler": DownloadOnlyCompilerInstaller,
    "jdk": JdkInstaller
}
