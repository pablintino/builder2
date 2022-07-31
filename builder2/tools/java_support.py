import os
import re
from pathlib import Path

from command_line import CommandRunner
from file_manager import FileManager

DIR_NAME_JAVA_HOME = 'java_home'
EXEC_NAME_JAVA = 'java'
EXEC_NAME_JAVA_COMPILER = 'javac'
EXEC_NAME_JAVA_DOC = 'javadoc'
EXEC_NAME_JAVA_KEYTOOL = 'keytool'
EXEC_NAME_JAVA_CACERTS = 'cacerts'


class JavaTools:

    def __init__(self, file_manager: FileManager, command_runner: CommandRunner):
        self._file_manager = file_manager
        self._command_runner = command_runner

    @staticmethod
    def __add_wellknown_if_exists(base, name, wellknown_paths):
        bin_path = base.absolute().joinpath(name)
        if bin_path.exists():
            wellknown_paths[name] = str(bin_path.absolute())

    def get_jdk_wellknown_paths(self, target_dir):
        wellknown_paths = {DIR_NAME_JAVA_HOME: target_dir}
        bin_dir = Path(os.path.join(target_dir, 'bin'))

        if bin_dir.exists() and bin_dir.is_dir():
            self.__add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA, wellknown_paths)
            self.__add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_COMPILER, wellknown_paths)
            self.__add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_DOC, wellknown_paths)
            self.__add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_KEYTOOL, wellknown_paths)

            cacerts_path = os.path.join(target_dir, 'lib', 'security', EXEC_NAME_JAVA_CACERTS)
            if os.path.exists(cacerts_path):
                wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_path
            else:
                # Old versions come with cacerts inside jre folder
                cacerts_jre_path = os.path.join(target_dir, 'jre', 'lib', 'security', EXEC_NAME_JAVA_CACERTS)
                if os.path.exists(cacerts_jre_path):
                    wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_jre_path

        return wellknown_paths

    def get_from_manifest_var(self, maven_jar_path, var_name, ignore_failure=False, default=None):
        manifest_content = self._file_manager.read_text_file_from_zip(maven_jar_path, 'META-INF/MANIFEST.MF',
                                                                      ignore_failure=ignore_failure)
        if manifest_content:
            match = re.search(r'{}:\s?([\d.]*)'.format(var_name), manifest_content)
            return match.group(1) if match else default

        return None
