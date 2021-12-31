import io
import logging
import math
import os
import re
import stat
import subprocess
import tarfile
import time
from pathlib import Path

import requests
from tqdm import tqdm

__toolchain_reference_binaries = {}


class ProgressFileObject(io.FileIO):
    def __init__(self, path, *args, **kwargs):
        self._total_size = os.path.getsize(path)
        self.__count = 0
        self.__tqdm = tqdm(
            total=self._total_size, unit="iB", unit_scale=True, unit_divisor=1024
        )
        io.FileIO.__init__(self, path, *args, **kwargs)

    def read(self, size):
        pos = self.tell()
        if self.__count != pos:
            self.__tqdm.update(pos - self.__count)
        self.__count = pos
        return io.FileIO.read(self, size)

    def close(self):
        super(ProgressFileObject, self).close()
        self.__tqdm.close()


def __verify_is_gcc_clang_executable(binary_path, compiler_name):
    must_support_options = ["-v", "-dumpmachine", "-dumpversion"]
    is_ok = False
    try:
        for option in must_support_options:
            result = subprocess.check_output(
                [binary_path, option],
                timeout=20,
                encoding="UTF-8",
                stderr=subprocess.STDOUT,
            )
            if option == "-v":
                is_ok = result and f"{compiler_name} version" in result.strip().lower()
            else:
                is_ok = result != ""

            if not is_ok:
                return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return is_ok


def __is_executable(file_name):
    st = os.stat(file_name)
    mode = st.st_mode
    return mode & (stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def __get_gcc_binary_path(base_dir):
    last_exec = None
    for path in Path(base_dir).rglob("*gcc*"):
        exec_path = str(path.absolute())
        if (
            not path.is_dir()
            and not path.name.endswith((".py", ".perl", ".sh", ".bash"))
            and __is_executable(path.absolute())
            # Discard g++ executables
            and "g++" not in path.stem
            and (
                path.stem.endswith("-gcc")
                or path.stem.startswith("gcc-")
                or path.stem == "gcc"
            )
            and __verify_is_gcc_clang_executable(exec_path, "gcc")
        ):
            # Many times gcc has prefixed names. Try to spot the shortest one
            if not last_exec or len(os.path.basename(exec_path)) < len(
                os.path.basename(last_exec)
            ):
                last_exec = exec_path
    return last_exec


def __get_clang_binary_path(base_dir):
    last_exec = None
    for path in Path(base_dir).rglob("*clang*"):
        exec_path = str(path.absolute())
        if (
            not path.is_dir()
            and not path.name.endswith(
                (".py", ".perl", ".sh", ".bash", ".el", ".applescript")
            )
            and __is_executable(path.absolute())
            # Discard clang++ executables
            and "clang++" not in path.stem
            and (
                path.stem.endswith("-clang")
                or path.stem.startswith("clang-")
                or path.stem == "clang"
            )
            and __verify_is_gcc_clang_executable(exec_path, "clang")
        ):
            # Many times gcc has prefixed names. Try to spot the shortest one
            if not last_exec or len(os.path.basename(exec_path)) < len(
                os.path.basename(last_exec)
            ):
                last_exec = exec_path

    return last_exec


def replace_non_alphanumeric(string, replace):
    return re.sub("[^0-9a-zA-Z]+", replace, string) if string else string


def get_compiler_binary_path(base_dir):
    if base_dir in __toolchain_reference_binaries:
        return __toolchain_reference_binaries[base_dir]
    exec_path = __get_gcc_binary_path(base_dir)
    if not exec_path:
        exec_path = __get_clang_binary_path(base_dir)
    if exec_path:
        __toolchain_reference_binaries[base_dir] = exec_path

    return exec_path


def download_file(url, fname):
    logging.info("Start download of %s", url)
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get("content-length", 0))
    with open(fname, "wb") as file, tqdm(
        desc=fname,
        total=total,
        unit="iB",
        unit_scale=True,
        unit_divisor=1024,
    ) as bar:
        for data in resp.iter_content(chunk_size=1024):
            size = file.write(data)
            bar.update(size)


def extract_file(file, target):
    logging.info("Start extraction of %s", file)
    with tarfile.open(fileobj=ProgressFileObject(file)) as tar:
        tar.extractall(target)
        return os.path.join(target, os.path.commonprefix(tar.getnames()))


def call_process(arg_list, cwd=None, timeout=180, shell=False):
    command_str = " ".join(map(str, arg_list))
    working_dir = os.getcwd() if not cwd else cwd
    try:
        return subprocess.check_output(
            arg_list,
            stdin=subprocess.DEVNULL,
            universal_newlines=True,
            cwd=working_dir,
            timeout=timeout,
            shell=shell,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError:
        logging.error("Failed to execute [%s]. Exit code non-zero.", command_str)
        raise
    except subprocess.TimeoutExpired:
        logging.error("Failed to execute [%s]. Timeout (%d)", command_str, timeout)
        raise


def run_process(arg_list, cwd=None, timeout=180, shell=False):
    command_str = (
        " ".join(map(str, arg_list)) if isinstance(arg_list, list) else arg_list
    )
    working_dir = os.getcwd() if not cwd else cwd
    start_time = time.time()
    try:
        subprocess.run(
            arg_list, cwd=working_dir, timeout=timeout, check=True, shell=shell
        )
    except subprocess.CalledProcessError:
        logging.error("Failed to execute [%s]. Exit code non-zero.", command_str)
        raise
    except subprocess.TimeoutExpired:
        logging.error("Failed to execute [%s]. Timeout (%d)", command_str, timeout)
        raise
    finally:
        logging.debug(
            " Command '%s' took %f seconds to execute",
            command_str,
            (time.time() - start_time),
        )


def capture_file_stdout(path):
    print("##################### START OF FILE OUTPUT ##################### ")
    print(f"####### Path {path}")
    with open(path, "r") as fin:
        print(fin.read(), end="")
    print("##################### END OF FILE OUTPUT ##################### ")


def install_apt_packages(names, timeout=None):
    # Note: use apt-get (debian based distro assumed), not apt (not safe for CLI)
    command = ["apt-get", "install", "-y"]
    command.extend(names)
    subprocess.check_call(
        command,
        stdout=open(os.devnull, "wb"),
        stderr=subprocess.STDOUT,
        # By default use 3 minutes as timeout for each packet
        timeout=3 * 60 * len(names) if not timeout else timeout,
    )


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


def check_output_compiler_reference_binary(target_dir, args, optional=False):
    exec_path = get_compiler_binary_path(target_dir)
    if not exec_path and not optional:
        SystemExit(f"Cannot find reference binary in target {target_dir}")
    elif exec_path:
        command = [exec_path]
        command.extend(args if isinstance(args, list) else [args])
        return call_process(command)
    else:
        return None


def get_max_allowed_cpus():
    core_count = os.cpu_count()
    return min(
        int(os.environ.get("BUILDER_MAX_CPU_COUNT", core_count if core_count else 4)),
        core_count,
    )


def get_command_timeout(reference_timeout):
    multiplier = float(
        os.environ.get("BUILDER_TIMEOUT_MULTIPLIER", "1").replace(",", "")
    )
    return (
        int(math.ceil(multiplier * reference_timeout))
        if multiplier > 1.0
        else reference_timeout
    )
