import dataclasses

from marshmallow import fields, Schema, post_load

from models.metadata_models import ToolchainComponentSchema


@dataclasses.dataclass
class ComponentInstallationModel:
    version: str
    name: str
    path: str
    package_hash: str
    configuration: dict
    wellknown_paths: dict
    environment_vars: dict
    path_dirs: list
    triplet: str = None


@dataclasses.dataclass
class InstallationEnvironmentModel:
    variables: dict


@dataclasses.dataclass
class InstallationSummaryModel:
    environment: InstallationEnvironmentModel
    installation_path: str
    components: dict
    system_packages: list


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
