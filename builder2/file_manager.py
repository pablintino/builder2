import dataclasses
import io
import json
import logging
import os
import pathlib
import shutil
import tarfile
import urllib
import zipfile

import requests

from exceptions import BuilderException

__logger = logging.getLogger()


class FileManager:
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

        def read(self, size):
            pos = self.tell()
            if (
                self.__count != pos
                and (pos - self.__last_report) > 0.2 * self._total_size
            ):
                self.__last_report = pos
                self.__logger.info(
                    "Extracting %s ... (%d %%)",
                    self.name,
                    int((pos / self._total_size) * 100),
                )
            self.__count = pos
            return io.FileIO.read(self, size)

        def close(self):
            super().close()

    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)

    def get_remote_file_content(self, url):
        self._logger.info("Fetching %s", url)
        try:
            with urllib.request.urlopen(url) as f:
                return f.read().decode("utf-8")
        except urllib.error.URLError as e:
            raise BuilderException(f"Error fetching {url}") from e

    def extract_file(self, file, target):
        self._logger.info("Start extraction of %s", file)
        with tarfile.open(fileobj=self.__ProgressFileObject(file, self._logger)) as tar:
            tar.extractall(target)
            return os.path.join(target, os.path.commonprefix(tar.getnames()))
        self._logger.info("Finished extraction of %s", file)

    @staticmethod
    def delete_file_tree(path: str):
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def create_file_tree(path: str):
        pathlib.Path(path).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def copy_file_tree(src: str, dst: str):
        shutil.copytree(src, dst)

    @staticmethod
    def read_file_as_bytes(path: str):
        with open(path, "rb") as file:
            return file.read()

    @classmethod
    def read_file_as_text(cls, path: str, ignore_failure=False):
        try:
            with open(path, "r") as file:
                return file.read()
        except FileNotFoundError as err:
            if not ignore_failure:
                raise err
        return None

    @classmethod
    def read_file_and_search(cls, path: str, regex, ignore_failure=False):
        return regex.search(cls.read_file_as_text(path, ignore_failure=ignore_failure))

    @classmethod
    def read_file_and_search_group(
        cls, path: str, regex, ignore_failure=False, group=1
    ):
        search = cls.read_file_and_search(path, regex, ignore_failure=ignore_failure)
        return search.group(group) if search else None

    @staticmethod
    def write_text_file(path: str, content):
        with open(path, "w") as file:
            return file.write(content)

    @classmethod
    def write_as_json(cls, path: str, content):
        with open(path, "w") as f:
            json.dump(content, f, indent=2, cls=cls.__EnhancedJSONEncoder)

    @staticmethod
    def write_binary_file(path, content: bytes):
        with open(path, "wb") as file:
            return file.write(content)

    @staticmethod
    def read_text_file_from_zip(path: str, file_path: str, ignore_failure=False):
        try:
            with zipfile.ZipFile(path, "r") as zf:
                return zf.read(file_path).decode("utf-8")
        except FileNotFoundError as err:
            if not ignore_failure:
                raise err
        return None

    @staticmethod
    def read_json_file(path: str):
        try:
            with open(path) as f:
                return json.load(f)
        except FileNotFoundError as err:
            raise BuilderException(f"Cannot read json file {path}") from err

    @staticmethod
    def search_get_files_by_pattern(
        path: str, patterns: list, recursive: bool = False
    ) -> list[pathlib.Path]:
        search_path = pathlib.Path(path)
        if not search_path.exists():
            raise BuilderException(f"Search path {path} doesn't exist", exit_code=2)

        if not search_path.is_dir():
            raise BuilderException(f"Search path {path} is not a proper directory")

        files = []
        for pattern in patterns:
            files.extend(
                search_path.glob(pattern)
                if not recursive
                else search_path.rglob(pattern)
            )
        return files

    def download_file(self, url, dst_file):
        self._logger.info("Start download of %s", url)
        resp = requests.get(url, stream=True)
        total = int(resp.headers.get("content-length", 0))
        received = 0
        last_print = 0
        with open(dst_file, "wb") as file:
            for data in resp.iter_content(chunk_size=1024):
                received = received + file.write(data)
                if total != 0 and (received - last_print) > 0.2 * total:
                    last_print = received
                    self._logger.info(
                        "Downloading %s ... (%d %%)", url, int((received / total) * 100)
                    )

        # Don't use total as size as it can be zero
        self._logger.info(
            "Finished download of %s. Size %s",
            url,
            self.__sizeof_fmt(os.path.getsize(dst_file)),
        )

    # From https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
    @staticmethod
    def __sizeof_fmt(num, suffix="B"):
        for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
            if abs(num) < 1024.0:
                return f"{num:3.1f}{unit}{suffix}"
            num /= 1024.0
        return f"{num:.1f}Yi{suffix}"