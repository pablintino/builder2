import logging
import os.path
import re
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import serialization

import utils
from command_line import CommandRunner
from exceptions import BuilderException
from file_manager import FileManager
from installation_summary import InstallationSummary
from models.metadata_models import JdkConfiguration
from tools.java_support import EXEC_NAME_JAVA_CACERTS, EXEC_NAME_JAVA_KEYTOOL


class CertificateManager:
    # TODO Assumes debian/ubuntu
    __SYSTEM_CA_LOCATION = "/usr/local/share/ca-certificates"
    __PEM_CERTIFICATE_START = "-----BEGIN CERTIFICATE-----"
    __PEM_CERTIFICATE_END = "-----END CERTIFICATE-----"
    __CERTIFICATE_RECOGNISED_EXTENSIONS = ["*.cert", "*.crt"]
    __DEFAULT_KEYSTORE_PASSWORD = "changeit"

    __PEM_REGEX = re.compile(
        f"({__PEM_CERTIFICATE_START}.*?{__PEM_CERTIFICATE_END})", re.DOTALL
    )

    def __init__(self, file_manager: FileManager, command_runner: CommandRunner):
        self._file_manager = file_manager
        self._command_runner = command_runner
        self._logger = logging.getLogger(self.__class__.__name__)

    def __read_certs_from_dir(self, cert_dir: str) -> list[x509.Certificate]:
        certs = []
        cert_files = self._file_manager.search_get_files_by_pattern(
            cert_dir, self.__CERTIFICATE_RECOGNISED_EXTENSIONS
        )
        for cert_file in cert_files:
            content = self._file_manager.read_file_as_text(cert_file)
            for cert_content in self.__PEM_REGEX.findall(content):
                certs.append(
                    x509.load_pem_x509_certificate(cert_content.encode("utf-8"))
                )

        return certs

    def __install_system_certs(self, certs: list[x509.Certificate]):
        for cert in certs:
            cn = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
            if not cn:
                raise BuilderException("Cannot get name for import certificate")
            sanitized_cn = utils.replace_non_alphanumeric(cn[0].value, "").lower()
            cert_path = os.path.join(self.__SYSTEM_CA_LOCATION, f"{sanitized_cn}.crt")
            self._file_manager.write_text_file(
                cert_path,
                cert.public_bytes(encoding=serialization.Encoding.PEM).decode("utf-8"),
            )

        # TODO Assumes debian/ubuntu
        # If no certs loaded just skip calling the SO to install them
        if certs:
            self._logger.info(
                "Installed %d certificates into system truststore", len(certs)
            )
            self._command_runner.run_process(
                ["update-ca-certificates", "--fresh"], shell=True
            )

    def __install_keystore_certificate(
        self,
        installation_summary: InstallationSummary,
        certificate: x509.Certificate,
        name: str = None,
    ):
        cn = certificate.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[
            0
        ].value
        if not name:
            name = cn.replace(" ", "").lower()

        # JDKs above 8 has a -cacerts option that allows not providing an explicit cacerts path
        keystore_opts = (
            ["-keystore", installation_summary.wellknown_paths[EXEC_NAME_JAVA_CACERTS]]
            if int(installation_summary.version.split(".")[0]) < 9
            else ["-cacerts"]
        )

        with tempfile.NamedTemporaryFile(mode="wb") as tmp:
            tmp.write(certificate.public_bytes(encoding=serialization.Encoding.DER))
            tmp.flush()
            self._command_runner.run_process(
                [
                    installation_summary.wellknown_paths[EXEC_NAME_JAVA_KEYTOOL],
                    "-importcert",
                    "-noprompt",
                    "-storepass",
                    self.__DEFAULT_KEYSTORE_PASSWORD,
                    "-file",
                    tmp.name,
                    "-alias",
                    name,
                ]
                + keystore_opts
            )
            self._logger.debug(
                "Certificate with CN %s installed in JDK",
                cn,
                installation_summary.version,
            )

    def __install_jdk_certificates(
        self, installation_summary: InstallationSummary, certs: list[x509.Certificate]
    ):
        for jdk_installation in installation_summary.get_components_by_type(
            JdkConfiguration
        ):
            self._logger.debug(
                "Installing certificates for JDK %s", jdk_installation.version
            )
            if EXEC_NAME_JAVA_CACERTS in jdk_installation.wellknown_paths:
                for cert in certs:
                    self.__install_keystore_certificate(jdk_installation, cert)
                self._logger.info(
                    "Installed %d certificates in JDK %s",
                    len(certs),
                    jdk_installation.version,
                )
            else:
                self._logger.warning(
                    "Skipping java certificates installation as no cacerts path is present"
                )

    def install_all_certificates(
        self, installation_summary: InstallationSummary, certs_path: str
    ):
        certs = self.__read_certs_from_dir(certs_path)
        self.__install_jdk_certificates(installation_summary, certs)
        self.__install_system_certs(certs)
