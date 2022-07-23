import dataclasses
import io
import json
import logging
import os
import tarfile
import urllib

import requests

from exceptions import BuilderException

__logger = logging.getLogger()


class EnhancedJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return dataclasses.asdict(o)
        return super().default(o)


class ProgressFileObject(io.FileIO):
    def __init__(self, path, logger, *args, **kwargs):
        self._total_size = os.path.getsize(path)
        self.__count = 0
        self.__last_report = 0
        self.__logger = logger
        io.FileIO.__init__(self, path, *args, **kwargs)

    def read(self, size):
        pos = self.tell()
        if self.__count != pos and (pos - self.__last_report) > 0.2 * self._total_size:
            self.__last_report = pos
            self.__logger.info('Extracting %s ... (%d %%)', self.name, int((pos / self._total_size) * 100))
        self.__count = pos
        return io.FileIO.read(self, size)

    def close(self):
        super(ProgressFileObject, self).close()


# From https://stackoverflow.com/questions/1094841/get-human-readable-version-of-file-size
def sizeof_fmt(num, suffix="B"):
    for unit in ["", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"]:
        if abs(num) < 1024.0:
            return f"{num:3.1f}{unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f}Yi{suffix}"


def download_file(url, dst_file):
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
                __logger.info('Downloading %s ... (%d %%)', url, int((received / total) * 100))

    # Don't use total as size as it can be zero
    __logger.info("Finished download of %s. Size %s", url, sizeof_fmt(os.path.getsize(dst_file)))


def get_remote_file_content(url):
    __logger.info("Fetching %s", url)
    try:
        with urllib.request.urlopen(url) as f:
            return f.read().decode('utf-8')
    except urllib.error.URLError as e:
        raise BuilderException(f'Error fetching {url}') from e


def extract_file(file, target):
    __logger.info("Start extraction of %s", file)
    with tarfile.open(fileobj=ProgressFileObject(file, __logger)) as tar:
        tar.extractall(target)
        return os.path.join(target, os.path.commonprefix(tar.getnames()))
    logging.info("Finished extraction of %s", file)


def read_file_as_bytes(path):
    with open(path, 'rb') as file:
        return file.read()


def read_file_as_text(path):
    with open(path, 'r') as file:
        return file.read()


def write_text_file(path, content):
    with open(path, 'w') as file:
        return file.write(content)


def write_binary_file(path, content: bytes):
    with open(path, 'wb') as file:
        return file.write(content)


def read_json_file(path: str):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError as err:
        raise BuilderException(f'Cannot read json file {path}') from err
