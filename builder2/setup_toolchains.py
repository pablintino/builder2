import json
import logging
import os
import sys

import installation
import tool_installers

logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
__DEFAULT_METADATA_FILE = "/tools/builder2/toolchain-metadata.json"


def __install_tools(config):
    tools_config = config.get("tools", None)
    if tools_config and "components" in tools_config:
        # Mandatory fields: 'base-path' and 'components'
        base_path = tools_config["base-path"]
        for name, toolchain_config in tools_config["components"].items():
            with tool_installers.get_installer(
                name, toolchain_config, base_path
            ) as installer:
                installer.run_installation()


if __name__ == "__main__":
    config_file = os.environ.get("BUILDER_METADATA_PATH", __DEFAULT_METADATA_FILE)
    with open(config_file) as f:
        __install_tools(json.load(f))
    installation.save_summary()
    installation.write_environment_file()
