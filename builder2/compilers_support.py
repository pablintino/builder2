import os
import stat
import subprocess
from pathlib import Path

import command_line

EXEC_NAME_GCC_CC = 'gcc'
EXEC_NAME_GCC_CXX = 'g++'
EXEC_NAME_CLANG_CC = 'clang'
EXEC_NAME_CLANG_CXX = 'clang++'
EXEC_NAME_CLANG_TIDY = 'clang-tidy'
EXEC_NAME_CLANG_FORMAT = 'clang-format'

__COMMON_COMPILER_BINARY_OPTIONS = ["-v", "-dumpmachine", "-dumpversion"]
__CLANG_TOOLS_BINARY_OPTIONS = ["--version"]


def __verify_is_gcc_clang_executable(binary_path, must_support_options):
    is_ok = False
    try:
        for option in must_support_options:
            result = subprocess.check_output(
                [binary_path, option],
                timeout=20,
                encoding="UTF-8",
                stderr=subprocess.STDOUT,
            )

            is_ok = result != ""
            if not is_ok:
                return False
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False
    return is_ok


def __is_executable(file_name):
    return bool(os.stat(file_name).st_mode & (stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH))


def get_compiler_binary_path(base_dir, target_name, ignore=None, must_support=None):
    ignore_names = ignore if ignore else []
    last_exec = None
    for path in Path(base_dir).rglob(f"*{target_name}*"):
        exec_path = str(path.absolute())
        if (
                not path.is_dir()
                and not path.name.endswith(
            (".py", ".perl", ".sh", ".bash", ".el", ".applescript")
        )
                and __is_executable(path.absolute())
                # Discard clang++ executables
                and all([(to_ignore_name not in path.stem) for to_ignore_name in ignore_names])
                and (
                path.stem.endswith(f"-{target_name}")
                or path.stem.startswith(f"{target_name}-")
                or path.stem == target_name
        )
                and (must_support and __verify_is_gcc_clang_executable(exec_path, must_support) or not must_support)
        ):
            # Many times gcc has prefixed names. Try to spot the shortest one
            if not last_exec or len(os.path.basename(exec_path)) < len(
                    os.path.basename(last_exec)
            ):
                last_exec = exec_path

    return last_exec


def get_clang_wellknown_paths(target_dir):
    wellknown_paths = {}
    clang_path = get_compiler_binary_path(target_dir, EXEC_NAME_CLANG_CC, ignore=[EXEC_NAME_CLANG_CXX],
                                          must_support=__COMMON_COMPILER_BINARY_OPTIONS)
    if clang_path:
        wellknown_paths[EXEC_NAME_CLANG_CC] = clang_path

    clang_cpp_path = get_compiler_binary_path(target_dir, EXEC_NAME_CLANG_CXX,
                                              must_support=__COMMON_COMPILER_BINARY_OPTIONS)
    if clang_cpp_path:
        wellknown_paths[EXEC_NAME_CLANG_CXX] = clang_cpp_path

    clang_format_path = get_compiler_binary_path(target_dir,
                                                 EXEC_NAME_CLANG_FORMAT, must_support=__CLANG_TOOLS_BINARY_OPTIONS)
    if clang_format_path:
        wellknown_paths[EXEC_NAME_CLANG_FORMAT] = clang_format_path

    clang_tidy_path = get_compiler_binary_path(target_dir,
                                               EXEC_NAME_CLANG_TIDY, must_support=__CLANG_TOOLS_BINARY_OPTIONS)
    if clang_tidy_path:
        wellknown_paths[EXEC_NAME_CLANG_TIDY] = clang_tidy_path

    return wellknown_paths


def get_gcc_wellknown_paths(target_dir):
    wellknown_paths = {}
    gcc_path = get_compiler_binary_path(target_dir, EXEC_NAME_GCC_CC, ignore=[EXEC_NAME_GCC_CXX],
                                        must_support=__COMMON_COMPILER_BINARY_OPTIONS)
    if gcc_path:
        wellknown_paths[EXEC_NAME_GCC_CC] = gcc_path
    gpp_path = get_compiler_binary_path(target_dir, EXEC_NAME_GCC_CXX, must_support=__COMMON_COMPILER_BINARY_OPTIONS)
    if gpp_path:
        wellknown_paths[EXEC_NAME_GCC_CXX] = gpp_path
    return wellknown_paths


def get_compiler_triplet(compiler_bin_path):
    return command_line.run_process([compiler_bin_path, '-dumpmachine']).strip()
