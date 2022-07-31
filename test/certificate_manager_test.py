import os
import shutil
import tempfile

import certificate_manager


def test_add_cert_to_keystore_ok():
    with tempfile.NamedTemporaryFile() as tmp_keystore, tempfile.NamedTemporaryFile() as tmp_crt:
        test_data_path = os.path.join(os.path.dirname(__file__), "data")
        shutil.copy2(
            os.path.join(test_data_path, "test-keystore.jks"), tmp_keystore.name
        )
        shutil.copy2(os.path.join(test_data_path, "test-cert.crt"), tmp_crt.name)
        certificate_manager.install_keystore_certificate(
            tmp_keystore.name, tmp_crt.name
        )

        updated_keystore = jks.KeyStore.load(tmp_keystore.name, "changeit")
        assert "test.test.com" in updated_keystore.certs
