import abc
import logging
import os
import pathlib
import shutil
import subprocess

import conan_manager
import utils
import tempfile
import installation
from urllib.parse import urlparse


class ToolInstaller(metaclass=abc.ABCMeta):
    def __init__(self, tool_key, config, base_install_dir, create_target=True):
        self.tool_key = tool_key
        self._config = config
        self._url = config.get("url", None)
        if not self._url:
            raise SystemExit(f"Tool url is mandatory. Tool key:{tool_key}")

        self.name = config.get("name", None)
        if not self.name:
            raise SystemExit(f"Tool name is mandatory. Tool key:{tool_key}")

        self._target_dir = os.path.join(base_install_dir, tool_key)

        # If tool is in a group install in their directory
        if "group" in config and config["group"]:
            self._target_dir = os.path.join(base_install_dir, config["group"], tool_key)
        else:
            self._target_dir = os.path.join(base_install_dir, tool_key)

        if create_target and not os.path.exists(self._target_dir):
            pathlib.Path(self._target_dir).mkdir(parents=True, exist_ok=True)

        self._temp_dir = None
        self._sources_dir = None
        self._version = None

    def __enter__(self):
        self._temp_dir = tempfile.TemporaryDirectory()
        return self

    def __exit__(self, exception_type, value, traceback):
        self._temp_dir.cleanup()
        if exception_type and self._target_dir and os.path.exists(self._target_dir):
            shutil.rmtree(self._target_dir, ignore_errors=True)

    def _create_installation_summary(self):
        tool_summary = {
            "version": self._version,
            "path": self._target_dir,
            "name": self.name,
            "installation-config": self._config,
        }
        if "group" in self._config:
            tool_summary["group"] = self._config["group"]

        return tool_summary

    def _compute_tool_version(self):
        if "version" not in self._config:
            SystemExit(
                f"Cannot determine component version. Component key: {self.tool_key}"
            )
        self._version = self._config["version"]

    @abc.abstractmethod
    def run_installation(self):
        pass


class ToolSourceInstaller(ToolInstaller):
    def _acquire_sources(self):
        parsed_url = urlparse(self._url)
        sources_tar_path = os.path.join(
            self._temp_dir.name, os.path.basename(parsed_url.path)
        )
        utils.download_file(self._url, sources_tar_path)
        self._sources_dir = utils.extract_file(sources_tar_path, self._temp_dir.name)

    def _acquire_packages(self):
        packages = self._config.get("required-packages", [])
        if type(packages) is list and packages:
            utils.install_apt_packages(packages)

    def _create_config_cmd(self):
        return [
            os.path.join(self._sources_dir, "configure"),
            f"--prefix={self._target_dir}",
        ]

    def _create_build_cmd(self):
        return ["make"]

    def _create_install_cmd(self):
        return ["make", "install"]

    def _configure(self, timeout=300, directory=None, shell=False):
        utils.run_process(
            self._create_config_cmd(),
            cwd=self._sources_dir if not directory else directory,
            timeout=utils.get_command_timeout(timeout),
            shell=shell,
        )

    def _build(self, timeout=900, directory=None, shell=False):
        utils.run_process(
            self._create_build_cmd(),
            cwd=self._sources_dir if not directory else directory,
            timeout=utils.get_command_timeout(timeout),
            shell=shell,
        )

    def _install(self, timeout=300, directory=None, shell=False):
        utils.run_process(
            self._create_install_cmd(),
            cwd=self._sources_dir if not directory else directory,
            timeout=utils.get_command_timeout(timeout),
            shell=shell,
        )
        installation_summary = self._create_installation_summary()
        installation.add_tool_to_summary(self.tool_key, installation_summary)
        conan_manager.create_profiles_from_compiler(
            self.tool_key, self._config, installation_summary
        )

    def run_installation(self):
        self._acquire_sources()
        self._acquire_packages()
        self._configure()
        self._compute_tool_version()
        self._build()
        self._install()


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

        super(CMakeSourcesInstaller, self)._compute_tool_version()

    def _create_config_cmd(self):
        return [
            os.path.join(self._sources_dir, "bootstrap"),
            f"--parallel={utils.get_max_allowed_cpus()}",
            f"--prefix={self._target_dir}",
        ]


class GccSourcesInstaller(ToolSourceInstaller):
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
            logging.info("GCC version read from sources: %s", gcc_version)
            suffix = f"-{gcc_version.rsplit('.', 1)[0] if gcc_version.endswith('.0') else gcc_version}"
            logging.info("GCC executables suffixed with: %s", suffix)
            opts.append(f"--program-suffix={suffix}")
        else:
            logging.info("GCC executables will not be suffixed")

        arq_guess = utils.call_process(
            ["./config.guess"], cwd=self._sources_dir
        ).strip()
        logging.info("GCC config.guess result: %s", arq_guess)

        languages = (
            ",".join(map(str, self._config["languages"]))
            if "languages" in self._config
            else "c,c++"
        )
        logging.info("GCC configured languages: %s", languages)

        logging.info("GCC installation path: %s", self._target_dir)

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
        logging.info("GCC configure options: %s", " ".join(map(str, opts)))

        command = [os.path.join(self._sources_dir, "configure")]
        command.extend(opts)
        return command

    def _create_build_cmd(self):
        return ["make", "-j", f"{utils.get_max_allowed_cpus()}"]

    def _create_install_cmd(self):
        return ["make", "install-strip"]

    def _compute_tool_version(self):
        version = self.__get_gcc_source_version()
        if version:
            self._version = version
        else:
            super(GccSourcesInstaller, self)._compute_tool_version()

    def _create_installation_summary(self):
        base_summary = super(GccSourcesInstaller, self)._create_installation_summary()

        target_triplet = utils.check_output_compiler_reference_binary(
            self._target_dir, "-dumpmachine"
        ).strip()
        base_summary["triplet"] = target_triplet
        return base_summary

    def run_installation(self):
        self._acquire_sources()
        self._acquire_packages()
        self._compute_tool_version()

        # Download required libs before start configuration
        utils.run_process(
            ["contrib/download_prerequisites"], cwd=self._sources_dir, timeout=1800
        )

        build_path = os.path.join(self._temp_dir.name, "build")
        os.mkdir(build_path)

        self._configure(directory=build_path, timeout=300)
        try:
            # Timeout for GCC with all languages enabled
            self._build(directory=build_path, timeout=2000)
            self._install(directory=build_path, timeout=300)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
            utils.capture_file_stdout(os.path.join(build_path, "Makefile"))
            raise


class ClangSourcesInstaller(ToolSourceInstaller):
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
        logging.info("Clang/LLVM configured with this modules: %s", llvm_modules)
        opts.append(f'-DLLVM_ENABLE_PROJECTS="{llvm_modules}"')

        config_runtimes = self._config.get("runtimes", [])
        if config_runtimes:
            llvm_runtimes = ";".join(map(str, config_runtimes))
            logging.info("Clang/LLVM configured with this runtimes: %s", llvm_runtimes)
            opts.append(f'-DLLVM_ENABLE_RUNTIMES="{llvm_runtimes}"')

        opts.extend(self.__get_clang_custom_build_opts())
        command = ["cmake"]
        command.extend(opts)

        # Little hack as CMake seems to be ignoring -D opts. Command is called in shell mode
        return " ".join(map(str, command))

    def _create_build_cmd(self):
        return ["ninja", "-j", f"{utils.get_max_allowed_cpus()}"]

    def _create_install_cmd(self):
        return ["ninja", "install"]

    def _compute_tool_version(self):
        self._version = utils.get_version_from_cmake_cache(
            os.path.join(self._temp_dir.name, "build", "CMakeCache.txt")
        )
        if not self._version:
            super(ClangSourcesInstaller, self)._compute_tool_version()

    def _create_installation_summary(self):
        base_summary = super(ClangSourcesInstaller, self)._create_installation_summary()

        # Remember. This ic GCC native, but clang implements the command as well
        # Note: Keep in mind that clang itself could not be present if not selected to be compiled: Optional
        target_triplet = utils.check_output_compiler_reference_binary(
            self._target_dir, "-dumpmachine", optional=True
        )
        if target_triplet:
            target_triplet = target_triplet.strip()
            base_summary["triplet"] = target_triplet
        return base_summary

    def run_installation(self):
        self._acquire_sources()
        self._acquire_packages()

        build_path = os.path.join(self._temp_dir.name, "build")
        os.mkdir(build_path)

        # Shell is mandatory (command is passed as string, not list) as it seems that by using the normal way
        #  CMake ignores -D options
        self._configure(directory=build_path, timeout=300, shell=True)

        # Version depends on CMakeCache created after configuration
        self._compute_tool_version()

        # Simplified timeout that assumes all options enabled
        self._build(directory=build_path, timeout=3400)
        self._install(directory=build_path, timeout=300)


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
        return ["ninja", "-j", f"{utils.get_max_allowed_cpus()}"]

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
            super(CppCheckSourcesInstaller, self)._compute_tool_version()

    def run_installation(self):
        self._acquire_sources()

        # Hardcoded mandatory dependency if rules are compiled
        compile_rules = self._config.get("compile-rules", True)
        if compile_rules:
            utils.install_apt_packages(["libpcre3", "libpcre3-dev"])

        # Shell is mandatory (command is passed as string, not list) as it seems that by using the normal way
        #  CMake ignores -D options
        self._configure(timeout=120, shell=True)

        self._compute_tool_version()

        self._build(timeout=300)
        self._install(timeout=120)


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

        super(ToolSourceInstaller, self)._compute_tool_version()


class CopyOnlySourcesInstaller(ToolInstaller):
    def __init__(self, tool_name, config, base_install_dir):
        super(CopyOnlySourcesInstaller, self).__init__(
            tool_name, config, base_install_dir, create_target=False
        )

    def run_installation(self):
        parsed_url = urlparse(self._url)
        sources_tar_path = os.path.join(
            self._temp_dir.name, os.path.basename(parsed_url.path)
        )
        utils.download_file(self._url, sources_tar_path)
        source_dir = utils.extract_file(sources_tar_path, self._temp_dir.name)
        shutil.copytree(source_dir, self._target_dir)

        self._compute_tool_version()
        installation.add_tool_to_summary(
            self.tool_key, self._create_installation_summary()
        )


class DownloadOnlyCompilerInstaller(CopyOnlySourcesInstaller):
    def _compute_tool_version(self):
        self._version = utils.check_output_compiler_reference_binary(
            self._target_dir, "-dumpversion"
        ).strip()
        if not self._version:
            super(CopyOnlySourcesInstaller, self)._compute_tool_version()

    def _create_installation_summary(self):
        base_summary = super(
            DownloadOnlyCompilerInstaller, self
        )._create_installation_summary()

        # Remember. This ic GCC native, but clang implements the command as well
        target_triplet = utils.check_output_compiler_reference_binary(
            self._target_dir, "-dumpmachine"
        ).strip()
        base_summary["triplet"] = target_triplet
        return base_summary


def get_installer(tool_key, config, base_install_dir):
    installer_type = config["type"]
    if installer_type == "gcc-build":
        return GccSourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "cmake-build":
        return CMakeSourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "download-only":
        return CopyOnlySourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "cppcheck-build":
        return CppCheckSourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "generic-build":
        return ToolSourceInstaller(tool_key, config, base_install_dir)
    if installer_type == "clang-build":
        return ClangSourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "valgrind-build":
        return ValgrindSourcesInstaller(tool_key, config, base_install_dir)
    if installer_type == "download-only-compiler":
        return DownloadOnlyCompilerInstaller(tool_key, config, base_install_dir)
    raise SystemExit(f"Installer type not supported {installer_type}")
