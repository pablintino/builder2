import dataclasses
import typing

from marshmallow import Schema, fields, post_load
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
    group: str = None
    version: str = None
    required_packages: list = None


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
        fields.String, data_key="post-installation", load_default=[]
    )


class PipPackageInstallationSchema(BasePackageInstallationSchema):
    index = fields.String(required=False, load_default=None, dump_default=None)

    @post_load
    def make_pip_config(self, data, **__):
        return PipPackageInstallationConfiguration(**data)


class AptPackageInstallationSchema(BasePackageInstallationSchema):
    @post_load
    def make_atp_config(self, data, **__):
        return AptPackageInstallationConfiguration(**data)


class PackageInstallationConfigurationSchema(OneOfSchema):
    type_schemas = {
        "pip": PipPackageInstallationSchema,
        "apt": AptPackageInstallationSchema,
    }

    def get_obj_type(self, obj):
        if isinstance(obj, PipPackageInstallationConfiguration):
            return "pip"
        if isinstance(obj, AptPackageInstallationConfiguration):
            return "apt"

        raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


class BaseComponentSchema(Schema):
    name = fields.Str(required=True)
    url = fields.Str(required=True)
    default = fields.Boolean(required=False, load_default=False)
    add_to_path = fields.Boolean(
        data_key="add-to-path", required=False, load_default=False
    )
    expected_hash = fields.Str(
        data_key="expected-hash", required=False, load_default=None
    )
    group = fields.Str(required=False, load_default=None)
    required_packages = fields.List(
        fields.Nested(PackageInstallationConfigurationSchema),
        data_key="required-packages",
        load_default=[],
    )
    version = fields.Str(required=False, load_default=None)


class SourceBuildSchema(BaseComponentSchema):
    pass


class CompilerBuildSchema(BaseComponentSchema):
    conan_profile = fields.Boolean(
        data_key="conan-profile", required=False, load_default=False
    )
    config_opts = fields.List(
        fields.String, data_key="config-opts", required=False, load_default=[]
    )


class GccComponentSchema(CompilerBuildSchema):
    languages = fields.List(fields.String, required=True)
    suffix_version = fields.Boolean(
        data_key="suffix-version", required=False, load_default=False
    )

    @post_load
    def make_gcc_config(self, data, **__):
        return GccBuildConfiguration(**data)


class ClangComponentSchema(CompilerBuildSchema):
    modules = fields.List(fields.String, required=True)
    runtimes = fields.List(fields.String, required=False, load_default=[])

    @post_load
    def make_clang_config(self, data, **__):
        return ClangBuildConfiguration(**data)


class CppCheckComponentSchema(BaseComponentSchema):
    compile_rules = fields.Boolean(
        data_key="compile-rules", required=False, load_default=True
    )

    @post_load
    def make_cppcheck_config(self, data, **__):
        return CppCheckBuildConfiguration(**data)


class ValgrindComponentSchema(BaseComponentSchema):
    @post_load
    def make_valgrind_config(self, data, **__):
        return ValgrindBuildConfiguration(**data)


class DownloadOnlyCompilerComponentSchema(BaseComponentSchema):
    @post_load
    def make_download_only_compiler_config(self, data, **__):
        return DownloadOnlyCompilerConfiguration(**data)


class DownloadOnlyComponentSchema(BaseComponentSchema):
    @post_load
    def make_download_only_config(self, data, **__):
        return DownloadOnlyConfiguration(**data)


class CmakeBuildComponentSchema(BaseComponentSchema):
    @post_load
    def make_cmake_config(self, data, **__):
        return CmakeBuildConfiguration(**data)


class JdkComponentSchema(BaseComponentSchema):
    @post_load
    def make_jdk_config(self, data, **__):
        return JdkConfiguration(**data)


class MavenComponentSchema(BaseComponentSchema):
    @post_load
    def make_maven_config(self, data, **__):
        return MavenConfiguration(**data)


class ToolchainComponentSchema(OneOfSchema):
    type_schemas = {
        "gcc-build": GccComponentSchema,
        "clang-build": ClangComponentSchema,
        "cppcheck-build": CppCheckComponentSchema,
        "valgrind-build": ValgrindComponentSchema,
        "download-only-compiler": DownloadOnlyCompilerComponentSchema,
        "download-only": DownloadOnlyComponentSchema,
        "source-build": SourceBuildSchema,
        "cmake-build": CmakeBuildComponentSchema,
        "jdk": JdkComponentSchema,
        "maven": MavenComponentSchema,
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

        raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


class ToolchainMetadataSchema(Schema):
    components = fields.Dict(
        keys=fields.Str(), values=fields.Nested(ToolchainComponentSchema)
    )
    packages = fields.List(fields.Nested(PackageInstallationConfigurationSchema), load_default=[])
    global_variables = fields.Dict(
        data_key="global-variables",
        keys=fields.Str(),
        values=fields.Str(),
        load_default={},
    )

    @post_load
    def make_toolchain_config(self, data, **__):
        return ToolchainMetadataConfiguration(**data)
