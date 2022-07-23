import logging
import os
import re
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import command_line
import file_utils

__logger = logging.getLogger()
__DEFAULT_KEYSTORE_PASSWORD = 'changeit'

DIR_NAME_JAVA_HOME = 'java_home'
EXEC_NAME_JAVA = 'java'
EXEC_NAME_JAVA_COMPILER = 'javac'
EXEC_NAME_JAVA_DOC = 'javadoc'
EXEC_NAME_JAVA_KEYTOOL = 'keytool'
EXEC_NAME_JAVA_CACERTS = 'cacerts'


def __add_wellknown_if_exists(base, name, wellknown_paths):
    bin_path = base.absolute().joinpath(name)
    if bin_path.exists():
        wellknown_paths[name] = str(bin_path.absolute())


def get_jdk_wellknown_paths(target_dir):
    wellknown_paths = {DIR_NAME_JAVA_HOME: target_dir}
    bin_dir = Path(os.path.join(target_dir, 'bin'))

    if bin_dir.exists() and bin_dir.is_dir():
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_COMPILER, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_DOC, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_KEYTOOL, wellknown_paths)

        cacerts_path = os.path.join(target_dir, 'lib', 'security', EXEC_NAME_JAVA_CACERTS)
        if os.path.exists(cacerts_path):
            wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_path
        else:
            # Old versions come with cacerts inside jre folder
            cacerts_jre_path = os.path.join(target_dir, 'jre', 'lib', 'security', EXEC_NAME_JAVA_CACERTS)
            if os.path.exists(cacerts_jre_path):
                wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_jre_path

    return wellknown_paths


def install_keystore_certificate(installation_summary, certificate, name=None):
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
        command_line.run_process([
                                     installation_summary.wellknown_paths[EXEC_NAME_JAVA_KEYTOOL],
                                     '-importcert',
                                     '-noprompt',
                                     '-storepass',
                                     __DEFAULT_KEYSTORE_PASSWORD,
                                     '-file',
                                     tmp.name,
                                     '-alias',
                                     name
                                 ] + keystore_opts)
        __logger.debug('Certificate with CN %s installed in %s jdk', cn, installation_summary.key)


def install_jdk_certificates(installation_summary, certs):
    for jdk_installation in installation_summary.get_components_by_type('jdk'):
        __logger.debug('Installing certificates for %s jdk', jdk_installation.key)
        if EXEC_NAME_JAVA_CACERTS in jdk_installation.wellknown_paths:
            for cert in certs:
                install_keystore_certificate(jdk_installation, cert)
            __logger.info('Installed %d certificates in %s jdk', len(certs), jdk_installation.key)
        else:
            __logger.warning('Skipping java certificates installation as no cacerts path is present')


def get_jdk_version(target_dir):
    release_file = os.path.join(target_dir, 'release')
    if os.path.exists(release_file):
        release_content = file_utils.read_file_as_text(release_file)
        version_match = re.search('JAVA_VERSION="([\\d.]*)"', release_content)
        if version_match:
            return version_match.group(1)

    version_file = os.path.join(target_dir, 'version.txt')
    if os.path.exists(version_file):
        version_file_content = file_utils.read_file_as_text(version_file).strip()
        if version_file_content:
            return version_file_content

    return None
