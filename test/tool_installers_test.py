import os
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

import java_support
from execution_parameters import ExecutionParameters
from models.metadata_models import JdkConfiguration
from tool_installers import DownloadOnlySourcesInstaller, JdkInstaller


@patch('builder2.tool_installers.file_utils.compute_file_sha1')
@patch('builder2.tool_installers.file_utils.download_file')
@patch('builder2.tool_installers.file_utils.extract_file')
@patch('builder2.tool_installers.pathlib.Path')
@patch('builder2.tool_installers.shutil.copytree')
@patch('builder2.tool_installers.tempfile.TemporaryDirectory')
def test_basic_all_ok(tempfile_mock, copytree_mock, pathlib_path_mock, extract_file_mock,
                      download_file_mock, compute_file_sha1_mock):
    config = {
        "group": "test-group",
        "type": "download-only-compiler",
        "name": "test-tool",
        "version": "1.0.0",
        "url": "https://test.test.com/test-file-v.0.0.tar.bz2"
    }

    # Make the temp file return a static path always
    tempfile_mock.return_value = tempfile_mock
    cleanup_mock = MagicMock()
    tempfile_mock.configure_mock(name='/test', cleanup=cleanup_mock)

    tool_extract_path = os.path.join(tempfile_mock.name, 'test-tool')
    extract_file_mock.return_value = tool_extract_path

    parameters = ExecutionParameters(core_count=1, file_name='/file-name', time_multiplier=1.0,
                                     target_dir='/target-dir')
    with DownloadOnlySourcesInstaller('test-tool', config, parameters) as installer:
        result = installer.run_installation()
        assert result.success
        assert not result.error

    tarfile_target_path = os.path.join(
        tempfile_mock.name, os.path.basename(urlparse(config['url']).path)
    )
    download_file_mock.assert_called_once_with(config['url'], tarfile_target_path)
    compute_file_sha1_mock.assert_called_once_with(tarfile_target_path)
    extract_file_mock.assert_called_once_with(tarfile_target_path, tempfile_mock.name)
    pathlib_path_mock.assert_not_called()
    copytree_mock.assert_called_once_with(tool_extract_path, os.path.join('/test', config["group"], 'test-tool'))
    cleanup_mock.assert_called_once()


@patch('builder2.tool_installers.java_support.get_jdk_wellknown_paths')
@patch('builder2.tool_installers.crypto_utils.compute_file_sha1')
@patch('builder2.tool_installers.file_utils.download_file')
@patch('builder2.tool_installers.file_utils.extract_file')
@patch('builder2.tool_installers.shutil.copytree')
@patch('builder2.tool_installers.tempfile.TemporaryDirectory')
@patch('builder2.tool_installers.file_utils.read_file_as_text')
def test_jdk_basic(read_file_as_text_mock, tempfile_mock, copytree_mock, pathlib_path_mock,
                   extract_file_mock, download_file_mock, compute_file_sha1_mock, get_jdk_wellknown_paths_mock):
    config = JdkConfiguration(
        name='test-tool',
        url='https://test.test.com/test-file-v.0.0.tar.bz2',
        default=False,
        add_to_path=False,
        expected_hash=None,
        group='test-group',
        version='1.0.0',
        required_packages=[]
    )

    # Make the temp file return a static path always
    tempfile_mock.return_value = tempfile_mock
    cleanup_mock = MagicMock()
    tempfile_mock.configure_mock(name='/test', cleanup=cleanup_mock)

    tool_extract_path = os.path.join(tempfile_mock.name, 'test-tool')
    extract_file_mock.return_value = tool_extract_path
    compute_file_sha1_mock.return_value = '98ab7aefeaa9ee253eaa30c50d3e6c9eb8d863bf'

    get_jdk_wellknown_paths_mock.return_value = {
        java_support.EXEC_NAME_JAVA: '/test/java',
        java_support.DIR_NAME_JAVA_HOME: '/test',
        java_support.EXEC_NAME_JAVA_CACERTS: '/test/cacerts',
        java_support.EXEC_NAME_JAVA_DOC: '/test/javadoc',
        java_support.EXEC_NAME_JAVA_KEYTOOL: '/test/keytool'
    }

    with open(os.path.join(os.path.join(os.path.dirname(__file__), 'data', 'jdk-release-file')), 'r') as f:
        read_file_as_text_mock.return_value = f.read()

    parameters = ExecutionParameters(core_count=1, file_name='/file-name', time_multiplier=1.0,
                                     target_dir='/target-dir')
    with JdkInstaller('test-tool', config, parameters) as installer:
        installation = installer.run_installation()
        assert installation.wellknown_paths == get_jdk_wellknown_paths_mock.return_value
        assert installation.package_hash == compute_file_sha1_mock.return_value

    tarfile_target_path = os.path.join(
        tempfile_mock.name, os.path.basename(urlparse(config.url).path)
    )
    download_file_mock.assert_called_once_with(config.url, tarfile_target_path)
    compute_file_sha1_mock.assert_called_once_with(tarfile_target_path)
    extract_file_mock.assert_called_once_with(tarfile_target_path, tempfile_mock.name)
    copytree_mock.assert_called_once_with(tool_extract_path, os.path.join('/test', config.group, 'test-tool'))
    cleanup_mock.assert_called_once()
