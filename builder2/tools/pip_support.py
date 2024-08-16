import configparser
import json
import pathlib
import sys
import typing

from builder2 import command_line


def fetch_entry_points(
    package_path: pathlib.Path,
) -> typing.Optional[typing.Dict[str, str]]:
    if not package_path.exists():
        return None

    entry_points_info_path = package_path.joinpath("entry_points.txt")
    if not entry_points_info_path.exists():
        return None
    config = configparser.ConfigParser()
    if not config.read(entry_points_info_path):
        # todo log: error reading the file
        return None
    try:
        entry_points = config.options("console_scripts") or []
    except configparser.NoSectionError:
        # todo log
        return None

    # How this works:
    # 1. The parent of entry_points_install_dir points to either site-packages or dist-packages
    # 2. site/dist-packages parent is a dir named python<version>
    # 3. python<version> lives in the lib/ directory
    # 4. lib/ parent is where lib/, include/, bin/ live. No matter
    #    if it's a venv of the system python
    entry_points_install_dir = package_path.parent.parent.parent.parent.joinpath("bin")
    if not entry_points_install_dir.is_dir():
        # todo log: error computing the bin dir
        return None

    result = {}
    for entry_point in entry_points:
        path = entry_points_install_dir.joinpath(entry_point)
        if path.exists():
            result[entry_point] = str(path)
    return result


def fetch_package_location(
    package_name: str, command_runner: command_line.CommandRunner
) -> typing.Optional[pathlib.Path]:
    metadata = get_pip_inspect_information(package_name, command_runner)
    if not metadata or "metadata_location" not in metadata:
        return None
    location = pathlib.Path(metadata["metadata_location"])
    return location if location.is_dir() else None


def get_pip_inspect_information(
    package_name: str,
    command_runner: command_line.CommandRunner,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    output = json.loads(
        command_runner.check_output([sys.executable, "-m", "pip", "inspect"])
    )
    installed = output.get("installed", None)
    if not isinstance(installed, list):
        return None
    return next(
        (
            metadata
            for metadata in installed
            if metadata.get("metadata", {}).get("name", None) == package_name
        ),
        None,
    )
