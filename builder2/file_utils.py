import io
import logging
import os
import pathlib
import shutil
import tarfile

import requests
from tqdm import tqdm


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


def download_file(url, dst_file):
    logging.info("Start download of %s", url)
    resp = requests.get(url, stream=True)
    total = int(resp.headers.get("content-length", 0))
    with open(dst_file, "wb") as file, tqdm(
            desc=dst_file,
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


def create_directory_structure(path):
    pathlib.Path(path).mkdir(parents=True, exist_ok=True)
