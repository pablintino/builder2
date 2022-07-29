import logging
import os.path
import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import utils
from command_line import CommandRunner
from exceptions import BuilderException
from file_utils import FileManager
from tooling_support.java_support import JavaTools


class CertificateManager:
    # TODO Assumes debian/ubuntu
    __SYSTEM_CA_LOCATION = '/usr/local/share/ca-certificates'
    __PEM_CERTIFICATE_START = '-----BEGIN CERTIFICATE-----'
    __PEM_CERTIFICATE_END = '-----END CERTIFICATE-----'
    __CERTIFICATE_RECOGNISED_EXTENSIONS = ['*.cert', '*.crt']

    __PEM_REGEX = re.compile(f'({__PEM_CERTIFICATE_START}.*?{__PEM_CERTIFICATE_END})', re.DOTALL)

    def __init__(self, file_manager: FileManager, java_support: JavaTools, command_runner: CommandRunner):
        self._file_manager = file_manager
        self._java_support = java_support
        self._command_runner = command_runner
        self._logger = logging.getLogger(self.__class__.__name__)

    def __read_certs_from_dir(self, cert_dir) -> [x509.Certificate]:
        certs = []
        cert_files = self._file_manager.search_get_files_by_pattern(cert_dir, self.__CERTIFICATE_RECOGNISED_EXTENSIONS)
        for cert_file in cert_files:
            content = self._file_manager.read_file_as_text(cert_file)
            for cert_content in self.__PEM_REGEX.findall(content):
                certs.append(x509.load_pem_x509_certificate(cert_content.encode('utf-8')))

        return certs

    def __install_system_certs(self, certs):
        for cert in certs:
            cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            if not cn:
                raise BuilderException('Cannot get name for import certificate')
            sanitized_cn = utils.replace_non_alphanumeric(cn[0].value, '').lower()
            cert_path = os.path.join(self.__SYSTEM_CA_LOCATION, f'{sanitized_cn}.crt')
            self._file_manager.write_text_file(cert_path,
                                               cert.public_bytes(encoding=serialization.Encoding.PEM).decode('utf-8'))

        # TODO Assumes debian/ubuntu
        # If no certs loaded just skip calling the SO to install them
        if certs:
            self._logger.info('Installed %d certificates into system truststore', len(certs))
            self._command_runner.run_process(['update-ca-certificates', '--fresh'], shell=True)

    def install_all_certificates(self, installation_summary, certs_path):
        certs = self.__read_certs_from_dir(certs_path)
        self._java_support.install_jdk_certificates(installation_summary, certs)
        self.__install_system_certs(certs)
