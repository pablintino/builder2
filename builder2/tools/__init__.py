import builder2.exceptions
import builder2.models.cli_models
import builder2.tools.tool_installers
from builder2.package_manager import PackageManager
from builder2.python_manager import PythonManager
from builder2.models.metadata_models import (
    BaseComponentConfiguration,
    AnsibleConfiguration,
    AnsibleCollectionConfiguration,
    DownloadOnlyConfiguration,
    CmakeBuildConfiguration,
    GccBuildConfiguration,
    CppCheckBuildConfiguration,
    SourceBuildConfiguration,
    ValgrindBuildConfiguration,
    DownloadOnlyCompilerConfiguration,
    ClangBuildConfiguration,
    JdkConfiguration,
    MavenConfiguration,
)


def build_tool_installer(
    tool_key: str,
    target_path: str,
    config: BaseComponentConfiguration,
    cli_config: builder2.models.cli_models.CliInstallArgs,
    package_manager: PackageManager,
    python_manager: PythonManager,
):
    ctr = {
        AnsibleConfiguration: builder2.tools.tool_installers.AnsibleInstaller,
        AnsibleCollectionConfiguration: builder2.tools.tool_installers.AnsibleCollectionInstaller,
        GccBuildConfiguration: builder2.tools.tool_installers.GccSourcesInstaller,
        CmakeBuildConfiguration: builder2.tools.tool_installers.CMakeSourcesInstaller,
        DownloadOnlyConfiguration: builder2.tools.tool_installers.DownloadOnlySourcesInstaller,
        CppCheckBuildConfiguration: builder2.tools.tool_installers.CppCheckSourcesInstaller,
        SourceBuildConfiguration: builder2.tools.tool_installers.ToolSourceInstaller,
        ClangBuildConfiguration: builder2.tools.tool_installers.ClangSourcesInstaller,
        ValgrindBuildConfiguration: builder2.tools.tool_installers.ValgrindSourcesInstaller,
        DownloadOnlyCompilerConfiguration: builder2.tools.tool_installers.DownloadOnlyCompilerInstaller,
        JdkConfiguration: builder2.tools.tool_installers.JdkInstaller,
        MavenConfiguration: builder2.tools.tool_installers.MavenInstaller,
    }.get(config.__class__, None)
    if not ctr:
        raise builder2.exceptions.BuilderException(
            f"Unsupported tool installer requested {config.__class__.__name__}"
        )
    return ctr(
        tool_key,
        target_path,
        config,
        cli_config,
        package_manager=package_manager,
        python_manager=python_manager,
    )
