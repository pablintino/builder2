import dataclasses
from typing import List, Dict

from marshmallow import fields, Schema, post_load

from builder2.models.metadata_models import (
    ToolchainComponentSchema,
    BaseComponentConfiguration,
)


class ComponentInstallationModel:
    def __init__(
        self,
        name: str,
        version: str,
        path: str,
        package_hash: str,
        configuration: BaseComponentConfiguration,
        triplet: str = None,
        wellknown_paths: Dict[str, str] = None,
        environment_vars: Dict[str, str] = None,
        path_dirs: List[str] = None,
        conan_profiles: Dict[str, str] = None,
    ):
        self.version = version
        self.name = name
        self.path = path
        self.package_hash = package_hash
        self.configuration = configuration
        self.wellknown_paths = wellknown_paths if wellknown_paths else {}
        self.environment_vars = environment_vars if environment_vars else {}
        self.conan_profiles = conan_profiles if conan_profiles else {}
        self.path_dirs = path_dirs if path_dirs else []
        self.triplet = triplet


@dataclasses.dataclass
class InstallationEnvironmentModel:
    variables: Dict[str, str]


@dataclasses.dataclass
class InstallationSummaryModel:
    environment: InstallationEnvironmentModel
    installation_path: str
    components: Dict[str, ComponentInstallationModel]
    system_packages: List[str]


class InstallationEnvironmentSchema(Schema):
    variables = fields.Dict(
        keys=fields.String(), values=fields.String(), dump_default={}, load_default={}
    )

    @post_load
    def make_environment(self, data, **kwargs):
        return InstallationEnvironmentModel(**data)


class ComponentInstallationSchema(Schema):
    name = fields.Str(required=True)
    package_hash = fields.Str(data_key="package-hash", required=True)
    version = fields.Str(required=True)
    path = fields.Str(required=True)
    triplet = fields.Str(required=False, dump_default=None, load_default=None)
    wellknown_paths = fields.Dict(
        keys=fields.String(),
        values=fields.String(),
        dump_default={},
        load_default={},
        data_key="wellknown-paths",
    )
    environment_vars = fields.Dict(
        keys=fields.String(),
        values=fields.String(),
        dump_default={},
        load_default={},
        data_key="environment-vars",
    )
    conan_profiles = fields.Dict(
        keys=fields.String(),
        values=fields.String(),
        dump_default={},
        load_default={},
        data_key="conan-profiles",
    )
    path_dirs = fields.List(fields.String, data_key="path-dirs", load_default=[])
    configuration = fields.Nested(ToolchainComponentSchema, required=True)

    @post_load
    def make_component_installation(self, data, **kwargs):
        return ComponentInstallationModel(**data)


class InstallationSummarySchema(Schema):
    installation_path = fields.String(data_key="installation-path", required=True)
    components = fields.Dict(
        keys=fields.Str(), values=fields.Nested(ComponentInstallationSchema)
    )
    environment = fields.Nested(
        InstallationEnvironmentSchema,
        required=False,
        dump_default=InstallationEnvironmentModel({}),
        load_default=InstallationEnvironmentModel({}),
    )
    system_packages = fields.List(
        fields.String, data_key="system-packages", load_default=[]
    )

    @post_load
    def make_installation_summary(self, data, **kwargs):
        return InstallationSummaryModel(**data)
