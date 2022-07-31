import hashlib
import re
import urllib.parse

from exceptions import BuilderException
from file_manager import FileManager


class CryptographicProvider:
    __HASH_CHUNK_SIZE = 65536

    __md5_string_regex = re.compile("^[a-fA-F\\d]{32}$")
    __sha1_string_regex = re.compile("^[a-fA-F\\d]{40}$")
    __sha256_string_regex = re.compile("^[a-fA-F\\d]{64}$")
    __sha512_string_regex = re.compile("^[a-fA-F\\d]{128}$")

    def __init__(self, file_manager: FileManager):
        self._file_manager = file_manager

    def __get_hash_algorithm_for_string(self, hash_str: str):
        if self.__md5_string_regex.match(hash_str):
            return hashlib.md5()
        elif self.__sha1_string_regex.match(hash_str):
            return hashlib.sha1()
        elif self.__sha256_string_regex.match(hash_str):
            return hashlib.sha256()
        elif self.__sha512_string_regex.match(hash_str):
            return hashlib.sha512()
        raise BuilderException(f"Cannot infer hash algorithm for {hash_str}")

    def compute_file_hash(self, path: str, algorithm):
        with open(path, "rb") as f:
            fb = f.read(self.__HASH_CHUNK_SIZE)
            while len(fb) > 0:
                algorithm.update(fb)
                fb = f.read(self.__HASH_CHUNK_SIZE)

        return algorithm.hexdigest()

    def compute_file_sha1(self, path: str):
        return self.compute_file_hash(path, hashlib.sha1())

    def validate_file_hash(self, file_path, expected_hash_string):
        parse_result = urllib.parse.urlparse(expected_hash_string)
        if parse_result.netloc and parse_result.scheme:
            remote_hash = self._file_manager.get_remote_file_content(
                expected_hash_string
            )
            algorithm = self.__get_hash_algorithm_for_string(remote_hash)
        else:
            algorithm = self.__get_hash_algorithm_for_string(expected_hash_string)

        file_hash = self.compute_file_hash(file_path, algorithm)
        if file_hash != remote_hash:
            raise BuilderException(
                f"File {file_hash} hash is not the expected one {remote_hash}"
            )
