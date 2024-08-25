import hashlib
import os
import pathlib
import re
import typing
import urllib.parse

from builder2.exceptions import BuilderException
from builder2.file_manager import FileManager


class CryptographicProvider:
    __HASH_CHUNK_SIZE = 65536

    __md5_string_regex = re.compile("^[a-fA-F\\d]{32}$")
    __sha1_string_regex = re.compile("^[a-fA-F\\d]{40}$")
    __sha256_string_regex = re.compile("^[a-fA-F\\d]{64}$")
    __sha512_string_regex = re.compile("^[a-fA-F\\d]{128}$")
    __hex_extract_regex = re.compile("\\s?([a-fA-F\\d]*)\\s?")

    def __init__(self, file_manager: FileManager):
        self._file_manager = file_manager

    def __get_hash_algorithm_and_value(self, hash_str: str):
        match = self.__hex_extract_regex.search(hash_str)
        hex_string = match.group(1) if match else None
        if not hex_string:
            raise BuilderException(f"Cannot infer hash string from {hash_str}")
        if self.__md5_string_regex.match(hex_string):
            return hashlib.md5(), hex_string
        if self.__sha1_string_regex.match(hex_string):
            return hashlib.sha1(), hex_string
        if self.__sha256_string_regex.match(hex_string):
            return hashlib.sha256(), hex_string
        if self.__sha512_string_regex.match(hex_string):
            return hashlib.sha512(), hex_string

        raise BuilderException(f"Cannot infer hash algorithm for {hash_str}")

    def add_file_to_hash(self, path: typing.Union[str, os.PathLike], algorithm):
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(self.__HASH_CHUNK_SIZE), b""):
                algorithm.update(chunk)
        return

    def add_files_to_hash(
        self,
        paths: typing.List[typing.Union[str, os.PathLike]],
        algorithm,
        add_names: bool = True,
        names_base: typing.Union[str, os.PathLike] = None,
    ):
        names_base = pathlib.Path(names_base) if names_base else None
        abs_names = {
            name if names_base is None else names_base.joinpath(name): name
            for name in sorted(paths)
        }
        for abs_name, original_name in abs_names.items():
            if add_names:
                algorithm.update(
                    str(original_name if names_base else abs_name).encode("utf-8")
                )
            self.add_file_to_hash(abs_name, algorithm)

    def compute_file_sha1(self, path: typing.Union[str, os.PathLike]) -> str:
        algorithm = hashlib.sha1()
        self.add_file_to_hash(path, algorithm)
        return algorithm.hexdigest()

    def compute_files_hash_sha1(
        self,
        paths: typing.List[typing.Union[str, os.PathLike]],
        add_names: bool = True,
        names_base: typing.Union[str, os.PathLike] = None,
    ) -> str:
        algorithm = hashlib.sha1()
        self.add_files_to_hash(
            paths, algorithm, add_names=add_names, names_base=names_base
        )
        return algorithm.hexdigest()

    def validate_file_hash(
        self, file_path: typing.Union[str, os.PathLike], hash_or_url_string: str
    ):
        parse_result = urllib.parse.urlparse(hash_or_url_string)
        if parse_result.netloc and parse_result.scheme:
            expected_hash = self._file_manager.get_remote_file_content(
                hash_or_url_string
            )
            algorithm, hash_value = self.__get_hash_algorithm_and_value(expected_hash)
        else:
            algorithm, hash_value = self.__get_hash_algorithm_and_value(
                hash_or_url_string
            )

        file_hash = self.add_file_to_hash(file_path, algorithm)
        if file_hash != hash_value:
            raise BuilderException(
                f"File {file_hash} hash is not the expected one {hash_value}"
            )
