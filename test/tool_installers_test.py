import os
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

from tool_installers import CopyOnlySourcesInstaller


@patch('builder2.tool_installers.file_utils.download_file')
@patch('builder2.tool_installers.file_utils.extract_file')
@patch('builder2.tool_installers.file_utils.create_directory_structure')
@patch('builder2.tool_installers.shutil.copytree')
@patch('builder2.tool_installers.tempfile.TemporaryDirectory')
def test_basic_all_ok(tempfile_mock, copytree_mock, create_directory_structure_mock, extract_file_mock,
                      download_file_mock):
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

    with CopyOnlySourcesInstaller('test-tool', config, '/test') as installer:
        installer.run_installation()

    tarfile_target_path = os.path.join(
        tempfile_mock.name, os.path.basename(urlparse(config['url']).path)
    )
    download_file_mock.assert_called_once_with(config['url'], tarfile_target_path)
    extract_file_mock.assert_called_once_with(tarfile_target_path, tempfile_mock.name)
    create_directory_structure_mock.assert_not_called()
    copytree_mock.assert_called_once_with(tool_extract_path,  os.path.join('/test', config["group"], 'test-tool'))
    cleanup_mock.assert_called_once()
