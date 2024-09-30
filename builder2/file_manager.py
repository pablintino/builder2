import dataclasses
import io
import json
import logging
import os
import pathlib
import stat
import tarfile
import typing
import urllib.error
import urllib.request
import zipfile
from typing import List

import requests
import yaml

from builder2.exceptions import BuilderException

__logger = logging.getLogger(__file__)


class __EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class __ProgressFileObject(io.FileIO):
    def __init__(self, path, logger, *args, **kwargs):
        self._total_size = os.path.getsize(path)
        self.__count = 0
        self.__last_report = 0
        self.__logger = logger
        io.FileIO.__init__(self, path, *args, **kwargs)

    def read(self, size: int = -1):
        pos = self.tell()
        if self.__count != pos and (pos - self.__last_report) > 0.2 * self._total_size:
            self.__last_report = pos
            self.__logger.info(
                "Extracting %s ... (%d %%)",
                self.name,
                int((pos / self._total_size) * 100),
            )
        self.__count = pos
        return io.FileIO.read(self, size)


def get_remote_file_content(url: str) -> str:
    __logger.info("Fetching %s", url)
    try:
        with urllib.request.urlopen(url) as file:
            return file.read().decode("utf-8")
    except urllib.error.URLError as err:
        raise BuilderException(f"Error fetching {url}") from err


def extract_file(file, target):
    __logger.info("Start extraction of %s", file)
    if zipfile.is_zipfile(file):
        with zipfile.ZipFile(file, "r") as zip_ref:
            # to mimic a tar extract inside a folder to avoid
            # the zip to be part of the extracted content
            extract_path = os.path.join(target, f"{os.path.basename(file)}-content")
            zip_ref.extractall(extract_path)
    else:
        with tarfile.open(fileobj=__ProgressFileObject(file, __logger)) as tar:
            tar.extractall(target)
            extract_path = os.path.join(target, os.path.commonprefix(tar.getnames()))
    __logger.info("Finished extraction of %s", file)
    __logger.debug("Extraction of %s returns %s", file, extract_path)
    return extract_path


def read_file_and_search(
    path: typing.Union[str, os.PathLike], regex, ignore_failure: bool = False
):
    return regex.search(read_file_as_text(path, ignore_failure=ignore_failure))


def read_file_and_search_group(
    path: typing.Union[str, os.PathLike],
    regex,
    ignore_failure: bool = False,
    group: int = 1,
) -> str:
    search = read_file_and_search(path, regex, ignore_failure=ignore_failure)
    return search.group(group) if search else None


def read_text_file_from_zip(
    path: typing.Union[str, os.PathLike],
    file_path: str,
    ignore_failure: bool = False,
) -> typing.Optional[str]:
    try:
        with zipfile.ZipFile(path, "r") as file:
            return file.read(file_path).decode("utf-8")
    except FileNotFoundError as err:
        if not ignore_failure:
            raise err
    return None


# From https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
def __sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def download_file(url: str, dst_file: typing.Union[str, os.PathLike]):
    __logger.info("Start download of %s", url)
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get("content-length", 0))
    received = 0
    last_print = 0
    with open(dst_file, "wb") as file:
        for data in resp.iter_content(chunk_size=1024):
            received = received + file.write(data)
            if total != 0 and (received - last_print) > 0.2 * total:
                last_print = received
                __logger.info(
                    "Downloading %s ... (%d %%)", url, int((received / total) * 100)
                )

    # Don't use total as size as it can be zero
    __logger.info(
        "Finished download of %s. Size %s",
        url,
        __sizeof_fmt(os.path.getsize(dst_file)),
    )


def read_file_as_text_lines(
    path: typing.Union[str, os.PathLike], ignore_failure: bool = False
) -> typing.Optional[typing.List[str]]:
    try:
        with open(path, "r") as file:
            return file.readlines()
    except FileNotFoundError as err:
        if not ignore_failure:
            raise err
    return None


def read_yaml_file(
    path: typing.Union[str, os.PathLike]
) -> typing.Dict[str, typing.Any]:
    with open(path) as file:
        return yaml.safe_load(file)


def read_json_file(
    path: typing.Union[str, os.PathLike]
) -> typing.Dict[str, typing.Any]:
    with open(path) as file:
        return json.load(file)


def read_file_as_text(
    path: typing.Union[str, os.PathLike], ignore_failure: bool = False
) -> typing.Optional[str]:
    try:
        with open(path, "r") as file:
            return file.read()
    except FileNotFoundError as err:
        if not ignore_failure:
            raise err
    return None


def write_as_json(
    path: typing.Union[str, os.PathLike], content: typing.Dict[str, typing.Any]
):
    with open(path, "w") as file:
        json.dump(content, file, indent=2, cls=__EnhancedJSONEncoder)


def write_text_file(path: typing.Union[str, os.PathLike], content: str):
    with open(path, "w") as file:
        return file.write(content)


def search_get_files_by_pattern(
    path: str, patterns: List[str], recursive: bool = False
) -> List[pathlib.Path]:
    search_path = pathlib.Path(path)
    if not search_path.exists() or not search_path.is_dir():
        raise FileNotFoundError(f"Search path {path} nof found")

    files = []
    for pattern in patterns:
        files.extend(
            search_path.glob(pattern) if not recursive else search_path.rglob(pattern)
        )
    return files


def file_is_executable(path: typing.Union[str, os.PathLike]) -> bool:
    executable_path = pathlib.Path(path) if isinstance(path, str) else path
    return (
        executable_path.exists()
        and executable_path.is_file()
        and bool(
            executable_path.stat().st_mode
            & (stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
        )
    )


def make_file_executable(path: typing.Union[str, os.PathLike]):
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
