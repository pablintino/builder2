import json
import logging
import os
import pathlib

import marshmallow.exceptions

import file_utils
from exceptions import BuilderException, BuilderValidationException
from file_utils import EnhancedJSONEncoder
from models.installation_models import ComponentInstallationModel, InstallationSummarySchema, InstallationSummaryModel, \
    InstallationEnvironmentModel


class InstallationSummary:
    SUMMARY_FILE_NAME = '.toolchain-installation-summary.json'
    __logger = logging.getLogger(__name__)

    def __init__(self, installation_path: str = None, summary: InstallationSummaryModel = None):
        if not installation_path and not summary:
            raise BuilderException('One of both summary or installation path must be given')

        self.__components = {}
        self.__system_packages = []
        self.__installation_path = installation_path
        self.__environment_vars = {}

        if summary:
            # Mandatory as cannot use the rest without the installation path
            self.__installation_path = summary.installation_path
            self.__system_packages = summary.system_packages
            self.__components = summary.components
            self.__environment_vars = summary.environment.variables

    @classmethod
    def from_path(cls, path):
        cls.__logger.info('Loading installation summary from %s', path)
        summary_path = pathlib.Path(path)
        summary_path = summary_path.joinpath(
            InstallationSummary.SUMMARY_FILE_NAME) if summary_path.is_dir() else summary_path
        try:
            return cls(summary=InstallationSummarySchema().load(data=file_utils.read_json_file(summary_path)))
        except marshmallow.exceptions.ValidationError as err:
            raise BuilderValidationException(f'Validation issues in toolchain installation summary from {summary_path}',
                                             err.messages_dict)

    def save(self, target_dir):
        file_name = os.path.join(target_dir, InstallationSummary.SUMMARY_FILE_NAME)
        self.__logger.info('Saving installation summary to %s', file_name)
        os.makedirs(target_dir, exist_ok=True)

        inventory = InstallationSummarySchema().dump(
            InstallationSummaryModel(installation_path=self.__installation_path, components=self.__components,
                                     environment=InstallationEnvironmentModel(variables=self.__environment_vars),
                                     system_packages=self.__system_packages))
        with open(file_name, "w") as f:
            json.dump(inventory, f, indent=2, cls=EnhancedJSONEncoder)

    def add_component(self, tool_key: str, tool_summary: ComponentInstallationModel):
        self.__components[tool_key] = tool_summary

    def add_system_package(self, name: str):
        self.__system_packages.append(name)

    def add_environment_variable(self, name: str, value: str):
        self.__environment_vars[name] = value

    def add_environment_variables(self, variables: dict):
        for key, value in variables.items():
            self.add_environment_variable(key, value)

    def get_environment_variables(self) -> dict:
        return self.__environment_vars

    def get_components(self) -> dict:
        return self.__components

    def get_components_by_type(self, component_type) -> [ComponentInstallationModel]:
        return [comp_installation for comp_installation in self.__components.values() if
                type(comp_installation.configuration) == component_type]

    def get_component_versions(self, component_name) -> [(str, str)]:
        return [(comp_installation.version, comp_installation.triplet) for comp_installation in
                self.__components.values() if
                comp_installation.name == component_name]

    def is_component_unique(self, name) -> bool:
        """
        Tell whether a component is unique in the whole installation in terms of triplet and/or version.
        :param name: The component name to be checked
        :return: True if the component is unique. False otherwise.
        """

        return len(self.get_component_versions(name)) < 2
