from __future__ import annotations

import logging
import os
from typing import List, Dict

from datetime import datetime
import marshmallow.exceptions
from builder2.exceptions import BuilderValidationException, BuilderException
from builder2.file_manager import FileManager
from builder2.models.installation_models import (
    ComponentInstallationModel,
    InstallationSummarySchema,
    InstallationSummaryModel,
    InstallationEnvironmentModel,
    PackageInstallationModel,
)


class InstallationSummary:
    __SUMMARY_FILE_NAME = ".toolchain-installation-summary.json"
    __logger = logging.getLogger(__name__)

    def __init__(
        self,
        file_manager: FileManager,
        summary: InstallationSummaryModel = None,
        path=None,
    ):
        self._file_manager = file_manager
        self.__components = {}
        self.__packages = []
        self.__environment_vars = {}
        self.path = path
        self.installed_at = None
        if summary:
            self.__packages = summary.packages
            self.__components = summary.components
            self.__environment_vars = summary.environment.variables
            self.installed_at = summary.installed_at

    @classmethod
    def from_path(cls, path: str, file_manager: FileManager) -> InstallationSummary:
        cls.__logger.info("Loading installation summary from %s", path)
        summary_path = (
            path
            if path.endswith(cls.__SUMMARY_FILE_NAME)
            else os.path.join(path, cls.__SUMMARY_FILE_NAME)
        )
        try:
            return cls(
                file_manager,
                summary=InstallationSummarySchema().load(
                    data=file_manager.read_json_file(summary_path)
                ),
                path=summary_path,
            )
        except marshmallow.exceptions.ValidationError as err:
            raise BuilderValidationException(
                f"Validation issues in toolchain installation summary from {summary_path}",
                err.messages_dict,
            )

    def save(self, target_dir: str):
        file_name = os.path.join(target_dir, self.__SUMMARY_FILE_NAME)
        self.__logger.info("Saving installation summary to %s", file_name)
        self._file_manager.create_file_tree(target_dir)

        inventory = InstallationSummarySchema().dump(
            InstallationSummaryModel(
                installation_path=target_dir,
                components=self.__components,
                environment=InstallationEnvironmentModel(
                    variables=self.__environment_vars
                ),
                packages=self.__packages,
                installed_at=datetime.now(),
            )
        )

        self._file_manager.write_as_json(file_name, inventory)

    def add_component(self, tool_key: str, tool_summary: ComponentInstallationModel):
        self.__components[tool_key] = tool_summary

    def add_packages(self, package: List[PackageInstallationModel]):
        self.__packages.extend(package)

    def add_environment_variable(self, name: str, value: str):
        self.__environment_vars[name] = value

    def add_environment_variables(self, variables: Dict[str, str]):
        for key, value in variables.items():
            self.add_environment_variable(key, value)

    def get_environment_variables(self) -> Dict[str, str]:
        return self.__environment_vars

    def get_components(self) -> Dict[str, ComponentInstallationModel]:
        return self.__components

    def get_component(
        self, name: str, version=None, triplet=None, default_if_not_found=False
    ) -> ComponentInstallationModel:
        elements = self.__search_matching_component(name, triplet, version)
        if len(elements) > 1 and not default_if_not_found:
            raise BuilderException(f"Multiple versions of {name} component")
        if len(elements) == 1:
            return elements[0]
        if default_if_not_found and elements:
            return next(
                (
                    element
                    for element in self.__components.values()
                    # Default to only a component of the same triplet. Never return a default component
                    # of a different triplet of the indicated one
                    if (
                        element.name == name
                        and element.configuration.default
                        and (triplet is None or triplet == element.triplet)
                    )
                ),
                None,
            )

        return None

    def __search_matching_component(self, name, triplet, version):
        def __name_match(element, target_name) -> bool:
            return (element.name == target_name) or any(
                alias == target_name for alias in element.aliases
            )

        elements = [
            element
            for element in self.__components.values()
            if (
                __name_match(element, name)
                and version
                and not triplet
                and element.version == version
            )
            or (
                __name_match(element, name)
                and triplet
                and not version
                and element.triplet == triplet
            )
            or (
                __name_match(element, name)
                and version
                and element.version == version
                and triplet
                and element.triplet == triplet
            )
            or (__name_match(element, name) and not version and not triplet)
        ]
        return elements

    def get_components_by_type(
        self, component_type: type
    ) -> [ComponentInstallationModel]:
        return [
            comp_installation
            for comp_installation in self.__components.values()
            if type(comp_installation.configuration) == component_type
        ]

    def get_component_versions(self, component_name: str) -> [(str, str)]:
        return [
            (comp_installation.version, comp_installation.triplet)
            for comp_installation in self.__components.values()
            if comp_installation.name == component_name
        ]
