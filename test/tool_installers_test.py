import os
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

from models.metadata_models import JdkConfiguration
from tools import java_support
from tools.tool_installers import JdkInstaller


@patch("builder2.tools.tool_installers.tempfile.TemporaryDirectory")
@patch("builder2.tools.tool_installers.pathlib.Path")
def test_jdk_basic(pathlib_path_mock, tempfile_mock):
    config = JdkConfiguration(
        name="test-tool",
        url="https://test.test.com/test-file-v.0.0.tar.bz2",
        default=True,
        add_to_path=True,
        expected_hash="04582c237a0516d67f6ccec3c32e3e40e114c219",
        group="test-group",
        required_packages=["dummy-package"],
    )

    installation_base_dir = "/base/dir"
    tool_key = "test-tool"
    target_dir = os.path.join(installation_base_dir, config.group, tool_key)

    # Make the temp file return a static path always
    tempfile_mock.return_value = tempfile_mock
    cleanup_mock = MagicMock()
    temp_path = "/test-temp"
    tempfile_mock.configure_mock(name=temp_path, cleanup=cleanup_mock)

    java_tools_mock = MagicMock()
    java_tools_mock.get_jdk_wellknown_paths.return_value = {
        java_support.EXEC_NAME_JAVA: "/test/java",
        java_support.DIR_NAME_JAVA_HOME: "/test",
        java_support.EXEC_NAME_JAVA_CACERTS: "/test/cacerts",
        java_support.EXEC_NAME_JAVA_DOC: "/test/javadoc",
        java_support.EXEC_NAME_JAVA_KEYTOOL: "/test/keytool",
    }

    file_manager = MagicMock()
    cryptographic_provider = MagicMock()
    command_runner_mock = MagicMock()
    package_manager_mock = MagicMock()

    # Fake pathlib exists to test /bin existence
    target_dir_base_path_mock = MagicMock()

    def pathlib_side_effect(*args, **kwargs):
        if args[0] == target_dir:
            return target_dir_base_path_mock
        return None

    pathlib_path_mock.side_effect = pathlib_side_effect
    bin_path_mock = MagicMock()
    target_dir_base_path_mock.joinpath.return_value = bin_path_mock
    bin_path_mock.exists.return_value = True
    bin_path_mock.is_dir.return_value = True
    bin_path_mock.absolute.return_value = os.path.join(target_dir, "bin")

    # Fake tar file destination path
    tar_file_path = os.path.join(temp_path, os.path.basename(urlparse(config.url).path))

    # Fake package computed hash
    cryptographic_provider.compute_file_sha1.return_value = (
        "04582c237a0516d0af6bbec3cace3e40e113e219"
    )

    # Tar file extract directory
    sources_directory = os.path.join(temp_path, "test-file-v.0.0")
    file_manager.extract_file.return_value = sources_directory

    # Mock release file version search
    file_manager.read_file_and_search_group.return_value = "v9.9.9"

    with JdkInstaller(
        tool_key,
        config,
        installation_base_dir,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner_mock,
        package_manager=package_manager_mock,
        java_tools=java_tools_mock,
    ) as installer:
        installation = installer.run_installation()
        assert installation
        assert installation.name == config.name
        assert installation.path == target_dir
        assert (
            installation.package_hash
            == cryptographic_provider.compute_file_sha1.return_value
        )
        assert (
            installation.version == file_manager.read_file_and_search_group.return_value
        )
        assert (
            installation.wellknown_paths
            == java_tools_mock.get_jdk_wellknown_paths.return_value
        )
        assert "JAVA_HOME" in installation.environment_vars
        assert (
            installation.environment_vars["JAVA_HOME"]
            == java_tools_mock.get_jdk_wellknown_paths.return_value[
                java_support.DIR_NAME_JAVA_HOME
            ]
        )
        assert installation.path_dirs and installation.path_dirs[0] == str(
            os.path.join(target_dir, "bin")
        )

    # Ensure tool is copied to its final destination
    file_manager.copy_file_tree.assert_called_once_with(sources_directory, target_dir)

    # Ensure tar file is extracted from sources dir to the temp dir
    file_manager.extract_file.assert_called_once_with(tar_file_path, temp_path)

    # Ensure hash is computed for the tarfile
    cryptographic_provider.compute_file_sha1.assert_called_once_with(tar_file_path)

    # Ensure hash is validated
    cryptographic_provider.validate_file_hash.assert_called_once_with(
        tar_file_path, config.expected_hash
    )

    # Ensure required packages are installed
    package_manager_mock.install_packages.assert_called_once_with(
        config.required_packages
    )

    # Ensure /bin path has been used for search for path dirs
    target_dir_base_path_mock.joinpath.assert_called_once_with("bin")

    file_manager.create_file_tree.assert_not_called()
    cleanup_mock.assert_called_once()
