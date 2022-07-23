import logging
import os.path
import pathlib
import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import command_line
import file_utils
import java_support
import utils
# TODO Assumes debian/ubuntu
from exceptions import BuilderException

__SYSTEM_CA_LOCATION = '/usr/local/share/ca-certificates'
__PEM_CERTIFICATE_START = '-----BEGIN CERTIFICATE-----'
__PEM_CERTIFICATE_END = '-----END CERTIFICATE-----'
__CERTIFICATE_RECOGNISED_EXTENSIONS = ['*.cert', '*.crt']

__pem_regex = re.compile(f'({__PEM_CERTIFICATE_START}.*?{__PEM_CERTIFICATE_END})', re.DOTALL)
__logger = logging.getLogger()


def __get_certificate_paths(cert_dir):
    certs_path = pathlib.Path(cert_dir)
    if not certs_path.exists():
        raise BuilderException('Certificates directory does not exist')

    if not certs_path.is_dir():
        raise BuilderException('Certificates directory isn\'t a folder', exit_code=2)

    cert_files = []
    for files in __CERTIFICATE_RECOGNISED_EXTENSIONS:
        cert_files.extend(certs_path.glob(files))
    return cert_files


def __read_certs_from_dir(cert_dir) -> [x509.Certificate]:
    certs = []
    cert_files = __get_certificate_paths(cert_dir)
    for cert_file in cert_files:
        content = file_utils.read_file_as_text(cert_file)
        for cert_content in __pem_regex.findall(content):
            certs.append(x509.load_pem_x509_certificate(cert_content.encode('utf-8')))

    return certs


def __install_system_certs(certs):
    for cert in certs:
        cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if not cn:
            raise BuilderException('Cannot get name for import certificate')
        sanitized_cn = utils.replace_non_alphanumeric(cn[0].value, '').lower()
        cert_path = os.path.join(__SYSTEM_CA_LOCATION, f'{sanitized_cn}.crt')
        file_utils.write_text_file(cert_path, cert.public_bytes(encoding=serialization.Encoding.PEM).decode('utf-8'))

    # TODO Assumes debian/ubuntu
    # If no certs loaded just skip calling the SO to install them
    if certs:
        __logger.info('Installed %d certificates into system truststore', len(certs))
        command_line.run_process(['update-ca-certificates', '--fresh'], shell=True)


def install_all_certificates(installation_summary, certs_path):
    certs = __read_certs_from_dir(certs_path)
    java_support.install_jdk_certificates(installation_summary, certs)
    __install_system_certs(certs)
