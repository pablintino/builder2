import dataclasses

from marshmallow import Schema, fields, post_load
from marshmallow_oneofschema import OneOfSchema


# Note: "Hacky" solution here to avoid using kw_only=True in dataclasses that makes python > 3.10 mandatory
#       As classes are filled by marshmallow mandatory fields are warrantied by marshmallow instead of
#       python dataclasses. This way Python 3.7> can be used
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
    components: list = None
    system_packages: list = None


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
        fields.String, data_key="required-packages", load_default=[]
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
    def make_gcc_config(self, data, **kwargs):
        return GccBuildConfiguration(**data)


class ClangComponentSchema(CompilerBuildSchema):
    modules = fields.List(fields.String, required=True)
    runtimes = fields.List(fields.String, required=False, load_default=[])

    @post_load
    def make_clang_config(self, data, **kwargs):
        return ClangBuildConfiguration(**data)


class CppCheckComponentSchema(BaseComponentSchema):
    compile_rules = fields.Boolean(
        data_key="compile-rules", required=False, load_default=True
    )

    @post_load
    def make_cppcheck_config(self, data, **kwargs):
        return CppCheckBuildConfiguration(**data)


class ValgrindComponentSchema(BaseComponentSchema):
    @post_load
    def make_valgrind_config(self, data, **kwargs):
        return ValgrindBuildConfiguration(**data)


class DownloadOnlyCompilerComponentSchema(BaseComponentSchema):
    @post_load
    def make_download_only_compiler_config(self, data, **kwargs):
        return DownloadOnlyCompilerConfiguration(**data)


class DownloadOnlyComponentSchema(BaseComponentSchema):
    @post_load
    def make_download_only_config(self, data, **kwargs):
        return DownloadOnlyConfiguration(**data)


class CmakeBuildComponentSchema(BaseComponentSchema):
    @post_load
    def make_cmake_config(self, data, **kwargs):
        return CmakeBuildConfiguration(**data)


class JdkComponentSchema(BaseComponentSchema):
    @post_load
    def make_jdk_config(self, data, **kwargs):
        return JdkConfiguration(**data)


class MavenComponentSchema(BaseComponentSchema):
    @post_load
    def make_maven_config(self, data, **kwargs):
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
        elif isinstance(obj, ClangBuildConfiguration):
            return "clang-build"
        elif isinstance(obj, SourceBuildConfiguration):
            return "source-build"
        elif isinstance(obj, CppCheckBuildConfiguration):
            return "cppcheck-build"
        elif isinstance(obj, ValgrindBuildConfiguration):
            return "valgrind-build"
        elif isinstance(obj, DownloadOnlyCompilerConfiguration):
            return "download-only-compiler"
        elif isinstance(obj, DownloadOnlyConfiguration):
            return "download-only"
        elif isinstance(obj, CmakeBuildConfiguration):
            return "cmake-build"
        elif isinstance(obj, JdkConfiguration):
            return "jdk"
        elif isinstance(obj, MavenConfiguration):
            return "maven"
        else:
            raise Exception("Unknown object type: {}".format(obj.__class__.__name__))


class ToolchainMetadataSchema(Schema):
    components = fields.Dict(
        keys=fields.Str(), values=fields.Nested(ToolchainComponentSchema)
    )
    system_packages = fields.List(
        fields.String, data_key="system-packages", load_default=[]
    )

    @post_load
    def make_toolchain_config(self, data, **kwargs):
        return ToolchainMetadataConfiguration(**data)
