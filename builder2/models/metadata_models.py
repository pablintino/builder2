import dataclasses
import typing

from marshmallow import (
    Schema,
    fields,
    post_load,
    validates_schema,
    ValidationError,
    validate,
)
from marshmallow_oneofschema import OneOfSchema


@dataclasses.dataclass
class BasePackageInstallationConfiguration:
    name: str = None
    version: str = None
    build_transient: bool = False
    post_installation: typing.List[str] = None


@dataclasses.dataclass
class PipPackageInstallationConfiguration(BasePackageInstallationConfiguration):
    index: str = None
    force: bool = False


@dataclasses.dataclass
class AptPackageInstallationConfiguration(BasePackageInstallationConfiguration):
    pass


@dataclasses.dataclass
class BaseComponentConfiguration:
    name: str = None
    url: str = None
    default: bool = False
    add_to_path: bool = False
    expected_hash: str = None
    executables_dir: str = None
    known_executables: typing.List[str] = None
    group: str = None
    version: str = None
    required_packages: list = None
    aliases: list = None
    use_venv: bool = False
    depends_on: str = None


@dataclasses.dataclass
class SourceBuildConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class CompilerBuildConfiguration(BaseComponentConfiguration):
    config_opts: list = None
    conan_profile: bool = None


@dataclasses.dataclass
class GccBuildConfiguration(CompilerBuildConfiguration):
    languages: list = None
    suffix_version: bool = None


@dataclasses.dataclass
class ClangBuildConfiguration(CompilerBuildConfiguration):
    modules: list = None
    runtimes: list = None


@dataclasses.dataclass
class CppCheckBuildConfiguration(BaseComponentConfiguration):
    compile_rules: bool = None


@dataclasses.dataclass
class ValgrindBuildConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class DownloadOnlyCompilerConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class DownloadOnlyConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class CmakeBuildConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class JdkConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class MavenConfiguration(BaseComponentConfiguration):
    pass


@dataclasses.dataclass
class PipBasedToolConfiguration(BaseComponentConfiguration):
    index: str = None
    use_venv: bool = False


@dataclasses.dataclass
class AnsibleRunnerConfiguration:
    version: str = None
    install: bool = True
    index: str = None


@dataclasses.dataclass
class AnsibleConfiguration(PipBasedToolConfiguration):
    runner: AnsibleRunnerConfiguration = None


@dataclasses.dataclass
class AnsibleCollectionConfiguration(BaseComponentConfiguration):
    install_requirements: bool = None
    system_wide: bool = None
    req_regexes: typing.List[str] = None
    use_venv: bool = False


@dataclasses.dataclass
class ToolchainMetadataConfiguration:
    components: typing.Dict[str, BaseComponentConfiguration] = None
    packages: typing.List[BasePackageInstallationConfiguration] = None
    global_variables: typing.Dict[str, str] = None


class BasePackageInstallationSchema(Schema):
    name = fields.Str(required=True)
    version = fields.Str(required=False, load_default=None)
    build_transient = fields.Boolean(
        data_key="build-transient",
        required=False,
        load_default=False,
        dump_default=False,
    )
    post_installation = fields.List(
        fields.String,
        data_key="post-installation",
        load_default=[],
        dump_default=[],
        required=False,
        allow_none=True,
    )


class PipPackageInstallationConfigurationSchema(BasePackageInstallationSchema):
    index = fields.String(required=False, load_default=None, dump_default=None)

    @post_load
    def make_pip_config(self, data, **__):
        return PipPackageInstallationConfiguration(**data)


class AptPackageInstallationConfigurationSchema(BasePackageInstallationSchema):
    @post_load
    def make_atp_config(self, data, **__):
        return AptPackageInstallationConfiguration(**data)


class PackageInstallationConfigurationSchema(OneOfSchema):
    type_schemas = {
        "pip": PipPackageInstallationConfigurationSchema,
        "apt": AptPackageInstallationConfigurationSchema,
    }

    def get_obj_type(self, obj):
        if isinstance(obj, PipPackageInstallationConfiguration):
            return "pip"
        if isinstance(obj, AptPackageInstallationConfiguration):
            return "apt"

        raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


class BaseComponentSchema(Schema):
    name = fields.Str(required=True)
    aliases = fields.List(
        fields.String, required=False, load_default=[], allow_none=True
    )
    default = fields.Boolean(required=False, load_default=False)
    add_to_path = fields.Boolean(
        data_key="add-to-path", required=False, load_default=False
    )
    expected_hash = fields.Str(
        data_key="expected-hash", required=False, load_default=None
    )
    group = fields.Str(required=False, load_default=None)
    known_executables = fields.List(
        fields.String,
        data_key="known-executables",
        load_default=[],
    )
    executables_dir = fields.Str(
        data_key="executables-dir", required=False, load_default=None
    )

    required_packages = fields.List(
        fields.Nested(PackageInstallationConfigurationSchema),
        data_key="required-packages",
        load_default=[],
    )
    version = fields.Str(required=False, load_default=None)
    depends_on = fields.Str(
        data_key="depends-on", required=False, load_default=None, dump_default=None
    )


class UrlBasedComponentSchema(BaseComponentSchema):
    url = fields.Str(required=True)


class SourceBuildSchema(UrlBasedComponentSchema):
    pass


class CompilerBuildSchema(UrlBasedComponentSchema):
    conan_profile = fields.Boolean(
        data_key="conan-profile", required=False, load_default=False
    )
    config_opts = fields.List(
        fields.String, data_key="config-opts", required=False, load_default=[]
    )


class GccBuildConfigurationSchema(CompilerBuildSchema):
    languages = fields.List(fields.String, required=True)
    suffix_version = fields.Boolean(
        data_key="suffix-version", required=False, load_default=False
    )

    @post_load
    def make_gcc_config(self, data, **__):
        return GccBuildConfiguration(**data)


class ClangBuildConfigurationSchema(CompilerBuildSchema):
    modules = fields.List(fields.String, required=True)
    runtimes = fields.List(fields.String, required=False, load_default=[])

    @post_load
    def make_clang_config(self, data, **__):
        return ClangBuildConfiguration(**data)


class CppCheckBuildConfigurationSchema(UrlBasedComponentSchema):
    compile_rules = fields.Boolean(
        data_key="compile-rules", required=False, load_default=True
    )

    @post_load
    def make_cppcheck_config(self, data, **__):
        return CppCheckBuildConfiguration(**data)


class ValgrindBuildConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_valgrind_config(self, data, **__):
        return ValgrindBuildConfiguration(**data)


class DownloadOnlyCompilerConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_download_only_compiler_config(self, data, **__):
        return DownloadOnlyCompilerConfiguration(**data)


class DownloadOnlyConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_download_only_config(self, data, **__):
        return DownloadOnlyConfiguration(**data)


class CmakeBuildConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_cmake_config(self, data, **__):
        return CmakeBuildConfiguration(**data)


class JdkConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_jdk_config(self, data, **__):
        return JdkConfiguration(**data)


class MavenConfigurationSchema(UrlBasedComponentSchema):
    @post_load
    def make_maven_config(self, data, **__):
        return MavenConfiguration(**data)


class AnsibleCollectionConfigurationSchema(BaseComponentSchema):
    url = fields.Str(required=False)
    install_requirements = fields.Boolean(
        data_key="install-requirements", required=False, load_default=True
    )
    system_wide = fields.Boolean(
        data_key="system-wide", required=False, load_default=False
    )

    req_regexes = fields.List(
        fields.String, data_key="requirements-regexes", load_default=[]
    )
    use_venv = fields.Boolean(
        data_key="use-venv", load_default=False, dump_default=False
    )

    @validates_schema
    def validate_numbers(self, data, **_):
        if "name" not in data and "url" not in data:
            raise ValidationError("one of name or url is required")

    @post_load
    def make_ansible_collection_config(self, data, **__):
        return AnsibleCollectionConfiguration(**data)


class AnsibleRunnerConfigurationSchema(Schema):
    version = fields.Str(required=False, load_default=None)
    install = fields.Boolean(required=False, load_default=True, dump_default=True)
    index = fields.String(required=False, load_default=None, dump_default=None)

    @post_load
    def make_ansible_runner_config(self, data, **__):
        return AnsibleRunnerConfiguration(**data)


class AnsibleConfigurationSchema(BaseComponentSchema):
    name = fields.Str(
        required=True, validate=validate.OneOf(["ansible", "ansible-core"])
    )
    index = fields.String(required=False, load_default=None, dump_default=None)
    runner = fields.Nested(
        AnsibleRunnerConfigurationSchema,
        load_default=None,
        required=False,
        allow_none=True,
    )
    use_venv = fields.Boolean(
        data_key="use-venv", load_default=False, dump_default=False
    )

    @post_load
    def make_ansible_config(self, data, **__):
        return AnsibleConfiguration(**data)


class ToolchainComponentSchema(OneOfSchema):
    type_schemas = {
        "gcc-build": GccBuildConfigurationSchema,
        "clang-build": ClangBuildConfigurationSchema,
        "cppcheck-build": CppCheckBuildConfigurationSchema,
        "valgrind-build": ValgrindBuildConfigurationSchema,
        "download-only-compiler": DownloadOnlyCompilerConfigurationSchema,
        "download-only": DownloadOnlyConfigurationSchema,
        "source-build": SourceBuildSchema,
        "cmake-build": CmakeBuildConfigurationSchema,
        "jdk": JdkConfigurationSchema,
        "maven": MavenConfigurationSchema,
        "ansible": AnsibleConfigurationSchema,
        "ansible-collection": AnsibleCollectionConfigurationSchema,
    }

    def get_obj_type(self, obj):
        if isinstance(obj, GccBuildConfiguration):
            return "gcc-build"
        if isinstance(obj, ClangBuildConfiguration):
            return "clang-build"
        if isinstance(obj, SourceBuildConfiguration):
            return "source-build"
        if isinstance(obj, CppCheckBuildConfiguration):
            return "cppcheck-build"
        if isinstance(obj, ValgrindBuildConfiguration):
            return "valgrind-build"
        if isinstance(obj, DownloadOnlyCompilerConfiguration):
            return "download-only-compiler"
        if isinstance(obj, DownloadOnlyConfiguration):
            return "download-only"
        if isinstance(obj, CmakeBuildConfiguration):
            return "cmake-build"
        if isinstance(obj, JdkConfiguration):
            return "jdk"
        if isinstance(obj, MavenConfiguration):
            return "maven"
        if isinstance(obj, AnsibleConfiguration):
            return "ansible"
        if isinstance(obj, AnsibleCollectionConfiguration):
            return "ansible-collection"

        raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


class ToolchainMetadataConfigurationSchema(Schema):
    components = fields.Dict(
        keys=fields.Str(), values=fields.Nested(ToolchainComponentSchema)
    )
    packages = fields.List(
        fields.Nested(PackageInstallationConfigurationSchema), load_default=[]
    )
    global_variables = fields.Dict(
        data_key="global-variables",
        keys=fields.Str(),
        values=fields.Str(),
        load_default={},
    )

    @post_load
    def make_toolchain_config(self, data, **__):
        return ToolchainMetadataConfiguration(**data)
