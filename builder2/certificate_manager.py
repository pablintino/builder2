import logging
import os.path
import re
import tempfile
from typing import List

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from builder2.models import installation_models
from builder2.utils import replace_non_alphanumeric
import builder2.command_line
from builder2.exceptions import BuilderException
import builder2.file_manager
from builder2.installation_summary import InstallationSummary
from builder2.models.metadata_models import JdkConfiguration
from builder2.tools.java_support import EXEC_NAME_JAVA_CACERTS, EXEC_NAME_JAVA_KEYTOOL


__logger = logging.getLogger(__file__)

# TODO Assumes debian/ubuntu
__SYSTEM_CA_LOCATION = "/usr/local/share/ca-certificates"
__PEM_CERTIFICATE_START = "-----BEGIN CERTIFICATE-----"
__PEM_CERTIFICATE_END = "-----END CERTIFICATE-----"
__CERTIFICATE_RECOGNISED_EXTENSIONS = ["*.cert", "*.crt"]
__DEFAULT_KEYSTORE_PASSWORD = "changeit"

__PEM_REGEX = re.compile(
    f"({__PEM_CERTIFICATE_START}.*?{__PEM_CERTIFICATE_END})", re.DOTALL
)


def __read_certs_from_dir(cert_dir: str) -> List[x509.Certificate]:
    certs = []
    try:
        cert_files = builder2.file_manager.search_get_files_by_pattern(
            cert_dir, __CERTIFICATE_RECOGNISED_EXTENSIONS
        )
    except FileNotFoundError as err:
        raise BuilderException(
            f"Certificate path '{cert_dir}' does not exist or is not a valid directory"
        ) from err

    for cert_file in cert_files:
        content = builder2.file_manager.read_file_as_text(cert_file)
        for cert_content in __PEM_REGEX.findall(content):
            certs.append(x509.load_pem_x509_certificate(cert_content.encode("utf-8")))

    return certs


def __install_system_certs(certs: List[x509.Certificate]):
    for cert in certs:
        common_name = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if not common_name:
            raise BuilderException("Cannot get name for import certificate")
        sanitized_cn = replace_non_alphanumeric(common_name[0].value, "").lower()
        cert_path = os.path.join(__SYSTEM_CA_LOCATION, f"{sanitized_cn}.crt")
        builder2.file_manager.write_text_file(
            cert_path,
            cert.public_bytes(encoding=serialization.Encoding.PEM).decode("utf-8"),
        )

    # TODO Assumes debian/ubuntu
    # If no certs loaded just skip calling the SO to install them
    if certs:
        __logger.info("Installed %d certificates into system truststore", len(certs))
        builder2.command_line.run_process(
            ["update-ca-certificates", "--fresh"], shell=True
        )


def __install_keystore_certificate(
    installation_summary: installation_models.ComponentInstallationModel,
    certificate: x509.Certificate,
    name: str = None,
):
    common_name = certificate.subject.get_attributes_for_oid(
        x509.oid.NameOID.COMMON_NAME
    )[0].value
    if not name:
        name = common_name.replace(" ", "").lower()

    # JDKs above 8 has a -cacerts option that allows not providing an explicit cacerts path
    keystore_opts = (
        ["-keystore", installation_summary.wellknown_paths[EXEC_NAME_JAVA_CACERTS]]
        if int(installation_summary.version.split(".")[0]) < 9
        else ["-cacerts"]
    )

    with tempfile.NamedTemporaryFile(mode="wb") as tmp:
        tmp.write(certificate.public_bytes(encoding=serialization.Encoding.DER))
        tmp.flush()
        builder2.command_line.run_process(
            [
                installation_summary.wellknown_paths[EXEC_NAME_JAVA_KEYTOOL],
                "-importcert",
                "-noprompt",
                "-storepass",
                __DEFAULT_KEYSTORE_PASSWORD,
                "-file",
                tmp.name,
                "-alias",
                name,
            ]
            + keystore_opts
        )
        __logger.debug(
            "Certificate with CN %s installed in JDK %s",
            common_name,
            installation_summary.version,
        )


def __install_jdk_certificates(
    installation_summary: InstallationSummary, certs: List[x509.Certificate]
):
    for jdk_installation in installation_summary.get_components_by_type(
        JdkConfiguration
    ):
        __logger.debug("Installing certificates for JDK %s", jdk_installation.version)
        if EXEC_NAME_JAVA_CACERTS in jdk_installation.wellknown_paths:
            for cert in certs:
                __install_keystore_certificate(jdk_installation, cert)
            __logger.info(
                "Installed %d certificates in JDK %s",
                len(certs),
                jdk_installation.version,
            )
        else:
            __logger.warning(
                "Skipping java certificates installation as no cacerts path is present"
            )


def install_all_certificates(
    installation_summary: InstallationSummary, certs_path: str
):
    certs = __read_certs_from_dir(certs_path)
    __install_jdk_certificates(installation_summary, certs)
    __install_system_certs(certs)
