import os
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

from builder2.models.metadata_models import JdkConfiguration
from builder2.tools import java_support
from builder2.tools import JdkInstaller


class TestJdk:
    @patch("builder2.tools.tool_installers.tempfile.TemporaryDirectory")
    @patch("builder2.tools.tool_installers.pathlib.Path")
    def test_jdk_basic_release_version(self, pathlib_path_mock, tempfile_mock):
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

        file_manager = MagicMock()
        cryptographic_provider_mock = MagicMock()
        command_runner_mock = MagicMock()
        package_manager_mock = MagicMock()

        # Fake pathlib exists to test /bin existence
        bin_path_mock = self.__build_pathlib_bin_mock(pathlib_path_mock, target_dir)

        # Fake tar file destination path
        tar_file_path = os.path.join(
            temp_path, os.path.basename(urlparse(config.url).path)
        )

        # Fake package computed hash
        cryptographic_provider_mock.compute_file_sha1.return_value = (
            "04582c237a0516d0af6bbec3cace3e40e113e219"
        )

        # Tar file extract directory
        sources_directory = os.path.join(temp_path, "test-file-v.0.0")
        file_manager.extract_file.return_value = sources_directory

        # Mock release file version search
        def read_file_and_search_group_side_effect(*args, **kwargs):
            if args[0] == os.path.join(target_dir, "release"):
                with open(
                    os.path.join(
                        os.path.join(
                            os.path.dirname(__file__), "data", "jdk-release-file"
                        )
                    ),
                    "r",
                ) as f:
                    release_content = f.read()
                    return args[1].search(release_content).group(1)

            return None

        file_manager.read_file_and_search_group.side_effect = (
            read_file_and_search_group_side_effect
        )

        java_tools_mock = self.__build_java_tools_mock()
        with JdkInstaller(
            tool_key,
            config,
            installation_base_dir,
            file_manager=file_manager,
            cryptographic_provider=cryptographic_provider_mock,
            command_runner=command_runner_mock,
            package_manager=package_manager_mock,
            java_tools=java_tools_mock,
        ) as installer:
            installation = installer.run_installation()
            assert installation
            assert installation.name == config.name
            assert installation.version == "11.0.1"
            assert installation.path == target_dir
            assert (
                installation.package_hash
                == cryptographic_provider_mock.compute_file_sha1.return_value
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

        self.__comon_jdk_Installer_mock_assertions(
            cleanup_mock,
            config,
            cryptographic_provider_mock,
            file_manager,
            package_manager_mock,
            sources_directory,
            tar_file_path,
            target_dir,
            bin_path_mock,
            temp_path,
        )

    @patch("builder2.tools.tool_installers.tempfile.TemporaryDirectory")
    @patch("builder2.tools.tool_installers.pathlib.Path")
    def test_jdk_basic_version_file(self, pathlib_path_mock, tempfile_mock):
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
        temp_path = "/test-temp"
        target_dir = os.path.join(installation_base_dir, config.group, tool_key)

        # Make the temp file return a static path always
        tempfile_mock.return_value = tempfile_mock
        cleanup_mock = MagicMock()
        tempfile_mock.configure_mock(name=temp_path, cleanup=cleanup_mock)

        cryptographic_provider_mock = MagicMock()
        command_runner_mock = MagicMock()
        package_manager_mock = MagicMock()

        # Fake pathlib exists to test /bin existence
        bin_path_mock = self.__build_pathlib_bin_mock(pathlib_path_mock, target_dir)

        # Fake tar file destination path
        tar_file_path = os.path.join(
            temp_path, os.path.basename(urlparse(config.url).path)
        )

        # Fake package computed hash
        cryptographic_provider_mock.compute_file_sha1.return_value = (
            "04582c237a0516d0af6bbec3cace3e40e113e219"
        )

        # Tar file extract directory
        sources_directory = os.path.join(temp_path, "test-file-v.0.0")

        file_manager = MagicMock()
        file_manager.extract_file.return_value = sources_directory

        # Mock read version file
        def read_file_and_search_group_side_effect(*args, **kwargs):
            if args[0] == os.path.join(target_dir, "version.txt"):
                with open(
                    os.path.join(
                        os.path.join(
                            os.path.dirname(__file__), "data", "jdk-version-file"
                        )
                    ),
                    "r",
                ) as f:
                    return f.read()
            return None

        file_manager.read_file_as_text.side_effect = (
            read_file_and_search_group_side_effect
        )
        file_manager.read_file_and_search_group.return_value = None
        java_tools_mock = self.__build_java_tools_mock()
        with JdkInstaller(
            tool_key,
            config,
            installation_base_dir,
            file_manager=file_manager,
            cryptographic_provider=cryptographic_provider_mock,
            command_runner=command_runner_mock,
            package_manager=package_manager_mock,
            java_tools=java_tools_mock,
        ) as installer:
            installation = installer.run_installation()
            assert installation
            assert installation.name == config.name
            assert installation.version == "8.342.07.4"
            assert installation.path == target_dir
            assert (
                installation.package_hash
                == cryptographic_provider_mock.compute_file_sha1.return_value
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

        self.__comon_jdk_Installer_mock_assertions(
            cleanup_mock,
            config,
            cryptographic_provider_mock,
            file_manager,
            package_manager_mock,
            sources_directory,
            tar_file_path,
            target_dir,
            bin_path_mock,
            temp_path,
        )

    @staticmethod
    def __build_pathlib_bin_mock(pathlib_path_mock, target_dir):
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
        return bin_path_mock

    @staticmethod
    def __comon_jdk_Installer_mock_assertions(
        cleanup_mock,
        config,
        cryptographic_provider_mock,
        file_manager,
        package_manager_mock,
        sources_directory,
        tar_file_path,
        target_dir,
        bin_path_mock,
        temp_path,
    ):
        # Ensure tool is copied to its final destination
        file_manager.copy_file_tree.assert_called_once_with(
            sources_directory, target_dir
        )
        # Ensure tar file is extracted from sources dir to the temp dir
        file_manager.extract_file.assert_called_once_with(tar_file_path, temp_path)
        # Ensure hash is computed for the tarfile
        cryptographic_provider_mock.compute_file_sha1.assert_called_once_with(
            tar_file_path
        )
        # Ensure hash is validated
        cryptographic_provider_mock.validate_file_hash.assert_called_once_with(
            tar_file_path, config.expected_hash
        )
        # Ensure required packages are installed
        package_manager_mock.install_packages.assert_called_once_with(
            config.required_packages
        )
        # Ensure /bin path has been used for search for path dirs
        bin_path_mock.is_dir.assert_called_once_with()
        bin_path_mock.exists.assert_called_once_with()
        file_manager.create_file_tree.assert_not_called()
        cleanup_mock.assert_called_once()

    @staticmethod
    def __build_java_tools_mock():
        java_tools_mock = MagicMock()
        java_tools_mock.get_jdk_wellknown_paths.return_value = {
            java_support.EXEC_NAME_JAVA: "/test/java",
            java_support.DIR_NAME_JAVA_HOME: "/test",
            java_support.EXEC_NAME_JAVA_CACERTS: "/test/cacerts",
            java_support.EXEC_NAME_JAVA_DOC: "/test/javadoc",
            java_support.EXEC_NAME_JAVA_KEYTOOL: "/test/keytool",
        }
        return java_tools_mock
