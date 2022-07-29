import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from command_line import CommandRunner
from file_utils import FileManager
from models.metadata_models import JdkConfiguration

DIR_NAME_JAVA_HOME = 'java_home'
EXEC_NAME_JAVA = 'java'
EXEC_NAME_JAVA_COMPILER = 'javac'
EXEC_NAME_JAVA_DOC = 'javadoc'
EXEC_NAME_JAVA_KEYTOOL = 'keytool'
EXEC_NAME_JAVA_CACERTS = 'cacerts'


class JavaTools:
    __DEFAULT_KEYSTORE_PASSWORD = 'changeit'
    __MANIFEST_VERSION_FIELD_REGEX = re.compile('Implementation-Version:\\s?([\\d.]*)')
    __JAVA_RELEASE_FILE_VERSION_REGEX = re.compile('JAVA_VERSION="([\\d.]*)"')

    def __init__(self, file_manager: FileManager, command_runner: CommandRunner):
        self._file_manager = file_manager
        self._command_runner = command_runner
        self._logger = logging.getLogger(self.__class__.__name__)

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

    def install_keystore_certificate(self, installation_summary, certificate, name=None):
        cn = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        if not name:
            name = cn.replace(' ', '').lower()

        # JDKs above 8 has a -cacerts option that allows not providing an explicit cacerts path
        keystore_opts = ['-keystore',
                         installation_summary.wellknown_paths[EXEC_NAME_JAVA_CACERTS]] if int(
            installation_summary.version.split('.')[0]) < 9 else ['-cacerts']

        with tempfile.NamedTemporaryFile(mode='wb') as tmp:
            tmp.write(certificate.public_bytes(encoding=serialization.Encoding.DER))
            tmp.flush()
            self._command_runner.run_process([
                                                 installation_summary.wellknown_paths[EXEC_NAME_JAVA_KEYTOOL],
                                                 '-importcert',
                                                 '-noprompt',
                                                 '-storepass',
                                                 self.__DEFAULT_KEYSTORE_PASSWORD,
                                                 '-file',
                                                 tmp.name,
                                                 '-alias',
                                                 name
                                             ] + keystore_opts)
            self._logger.debug('Certificate with CN %s installed in JDK', cn, installation_summary.version)

    def install_jdk_certificates(self, installation_summary, certs):
        for jdk_installation in installation_summary.get_components_by_type(JdkConfiguration):
            self._logger.debug('Installing certificates for JDK %s', jdk_installation.version)
            if EXEC_NAME_JAVA_CACERTS in jdk_installation.wellknown_paths:
                for cert in certs:
                    self.install_keystore_certificate(jdk_installation, cert)
                self._logger.info('Installed %d certificates in JDK %s', len(certs), jdk_installation.version)
            else:
                self._logger.warning('Skipping java certificates installation as no cacerts path is present')

    def get_jdk_version(self, target_dir):
        try:
            version_match = self._file_manager.read_file_and_search(os.path.join(target_dir, 'release'),
                                                                    self.__JAVA_RELEASE_FILE_VERSION_REGEX)
            if version_match:
                return version_match.group(1)
        except FileNotFoundError:
            # Do nothing, just try the version file approach
            pass

        try:
            version_file_content = self._file_manager.read_file_as_text(
                os.path.join(target_dir, 'version.txt')).strip()
            if version_file_content:
                return version_file_content
        except FileNotFoundError:
            # No other ways to get version. Return none
            return None
        return None

    @classmethod
    def get_version_from_jar_manifest(cls, maven_jar_path):
        with zipfile.ZipFile(maven_jar_path, 'r') as zf:
            version_match = cls.__MANIFEST_VERSION_FIELD_REGEX.search(zf.read('META-INF/MANIFEST.MF').decode('utf-8'))
            if version_match:
                return version_match.group(1)
