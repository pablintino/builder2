import dataclasses
import typing
from typing import List, Dict

from datetime import datetime
from marshmallow import fields, Schema, post_load
from marshmallow_oneofschema import OneOfSchema

from builder2.models.metadata_models import (
    ToolchainComponentSchema,
    BaseComponentConfiguration,
    BasePackageInstallationConfiguration,
    AptPackageInstallationConfiguration,
    PipPackageInstallationConfiguration, PipPackageInstallationConfigurationSchema,
    AptPackageInstallationConfigurationSchema,
)


class ComponentInstallationModel:
    def __init__(
            self,
            name: str,
            aliases: typing.List[str],
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
        self.aliases = aliases
        self.path = path
        self.package_hash = package_hash
        self.configuration = configuration
        self.wellknown_paths = wellknown_paths if wellknown_paths else {}
        self.environment_vars = environment_vars if environment_vars else {}
        self.conan_profiles = conan_profiles if conan_profiles else {}
        self.path_dirs = path_dirs if path_dirs else []
        self.triplet = triplet


class PackageInstallationModel:
    def __init__(
            self,
            name: str,
            version: str,
            configuration: BasePackageInstallationConfiguration = None,
    ):
        self.version = version
        self.name = name
        self.configuration = configuration

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, other) -> bool:
        if not isinstance(other, PackageInstallationModel):
            return False
        return self.name == other.name and self.version == other.version


class AptPackageInstallationModel(PackageInstallationModel):
    pass


class PipPackageInstallationModel(PackageInstallationModel):
    def __init__(self, *args, pip_hash: str, location: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.pip_hash = pip_hash
        self.location = location

    def __hash__(self) -> int:
        return hash((super().__hash__(), self.location))

    def __eq__(self, other) -> bool:
        if not isinstance(other, PipPackageInstallationModel):
            return False
        return super().__eq__(other) and self.location == other.location


@dataclasses.dataclass
class InstallationEnvironmentModel:
    variables: Dict[str, str]


@dataclasses.dataclass
class InstallationSummaryModel:
    environment: InstallationEnvironmentModel
    installation_path: str
    components: Dict[str, ComponentInstallationModel]
    packages: List[PackageInstallationModel]
    installed_at: datetime


class InstallationEnvironmentSchema(Schema):
    variables = fields.Dict(
        keys=fields.String(), values=fields.String(), dump_default={}, load_default={}
    )

    @post_load
    def make_environment(self, data, **__):
        return InstallationEnvironmentModel(**data)


class ComponentInstallationSchema(Schema):
    name = fields.Str(required=True)
    aliases = fields.List(
        fields.String, required=False, load_default=[], allow_none=True
    )
    package_hash = fields.Str(data_key="package-hash", required=True)
    version = fields.Str(required=True)
    path = fields.Str(required=False)
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
    def make_component_installation(self, data, **__):
        return ComponentInstallationModel(**data)


class PackageInstallationSchema(Schema):
    name = fields.Str(required=True)
    version = fields.Str(required=False, load_default=None, dump_default=None)


class AptPackageInstallationSchema(PackageInstallationSchema):
    name = fields.Str(required=True)
    version = fields.Str(required=False, load_default=None, dump_default=None)
    configuration = fields.Nested(AptPackageInstallationConfigurationSchema, required=True)

    @post_load
    def make_apt_package_installation(self, data, **__):
        return AptPackageInstallationModel(**data)


class PipPackageInstallationSchema(PackageInstallationSchema):
    name = fields.Str(required=True)
    version = fields.Str(required=True)
    pip_hash = fields.Str(required=True)
    location = fields.Str(required=True)
    # Not required: Some packages are automatically installed
    # as a dependency and don't have an associated metadata
    configuration = fields.Nested(
        PipPackageInstallationConfigurationSchema,
        required=False,
        dump_default=None,
        load_default=None,
        missing=None,
    )

    @post_load
    def make_apt_package_installation(self, data, **__):
        return PipPackageInstallationModel(**data)


class PackageInstallationSchema(OneOfSchema):
    type_schemas = {
        "pip": PipPackageInstallationSchema,
        "apt": AptPackageInstallationSchema,
    }

    def get_obj_type(self, obj):
        if isinstance(obj, PipPackageInstallationModel):
            return "pip"
        if isinstance(obj, AptPackageInstallationModel):
            return "apt"

        raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


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
    packages = fields.List(
        fields.Nested(PackageInstallationSchema), data_key="packages", load_default=[]
    )
    installed_at = fields.DateTime(data_key="installed-at", required=True)

    @post_load
    def make_installation_summary(self, data, **__):
        return InstallationSummaryModel(**data)
