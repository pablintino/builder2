import os
import re
from pathlib import Path

import builder2.file_manager

DIR_NAME_JAVA_HOME = "java_home"
EXEC_NAME_JAVA = "java"
EXEC_NAME_JAVA_COMPILER = "javac"
EXEC_NAME_JAVA_DOC = "javadoc"
EXEC_NAME_JAVA_KEYTOOL = "keytool"
EXEC_NAME_JAVA_CACERTS = "cacerts"


def __add_wellknown_if_exists(base, name, wellknown_paths):
    bin_path = base.absolute().joinpath(name)
    if bin_path.exists():
        wellknown_paths[name] = str(bin_path.absolute())


def get_jdk_wellknown_paths(target_dir):
    wellknown_paths = {DIR_NAME_JAVA_HOME: target_dir}
    bin_dir = Path(os.path.join(target_dir, "bin"))

    if bin_dir.exists() and bin_dir.is_dir():
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_COMPILER, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_DOC, wellknown_paths)
        __add_wellknown_if_exists(bin_dir, EXEC_NAME_JAVA_KEYTOOL, wellknown_paths)

        cacerts_path = os.path.join(
            target_dir, "lib", "security", EXEC_NAME_JAVA_CACERTS
        )
        if os.path.exists(cacerts_path):
            wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_path
        else:
            # Old versions come with cacerts inside jre folder
            cacerts_jre_path = os.path.join(
                target_dir, "jre", "lib", "security", EXEC_NAME_JAVA_CACERTS
            )
            if os.path.exists(cacerts_jre_path):
                wellknown_paths[EXEC_NAME_JAVA_CACERTS] = cacerts_jre_path

    return wellknown_paths


def get_from_manifest_var(maven_jar_path, var_name, ignore_failure=False, default=None):
    manifest_content = builder2.file_manager.read_text_file_from_zip(
        maven_jar_path, "META-INF/MANIFEST.MF", ignore_failure=ignore_failure
    )
    if manifest_content:
        match = re.search(r"{}:\s?([\d.]*)".format(var_name), manifest_content)
        return match.group(1) if match else default

    return None
