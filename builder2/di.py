import dataclasses
from typing import Dict

from dependency_injector import containers, providers

from builder2.models.metadata_models import BaseComponentConfiguration
from builder2.package_manager import PackageManager
from builder2.python_manager import PythonManager
from builder2.tools import (
    AnsibleInstaller,
    AnsibleCollectionInstaller,
    JdkInstaller,
    ToolInstaller,
    MavenInstaller,
    DownloadOnlyCompilerInstaller,
    ValgrindSourcesInstaller,
    ClangSourcesInstaller,
    ToolSourceInstaller,
    CppCheckSourcesInstaller,
    DownloadOnlySourcesInstaller,
    CMakeSourcesInstaller,
    GccSourcesInstaller,
)


@dataclasses.dataclass
class Dispatcher:
    installers: Dict[BaseComponentConfiguration, ToolInstaller]


class Container(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    python_manager = providers.Singleton(
        PythonManager,
        target_path=config.target_dir,
    )

    package_manager = providers.Singleton(PackageManager, python_manager)

    maven_installer_factory = providers.Factory(
        MavenInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    jdk_installer_factory = providers.Factory(
        JdkInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    gcc_sources_installer_factory = providers.Factory(
        GccSourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    cmake_sources_installer_factory = providers.Factory(
        CMakeSourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    cppcheck_sources_installer_factory = providers.Factory(
        CppCheckSourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    download_only_sources_installer_factory = providers.Factory(
        DownloadOnlySourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    download_only_compiler_installer_factory = providers.Factory(
        DownloadOnlyCompilerInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    valgrind_sources_installer_factory = providers.Factory(
        ValgrindSourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    clang_sources_installer_factory = providers.Factory(
        ClangSourcesInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    tool_source_installer_factory = providers.Factory(
        ToolSourceInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    ansible_installer_factory = providers.Factory(
        AnsibleInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    ansible_collection_installer_factory = providers.Factory(
        AnsibleCollectionInstaller,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
        python_manager=python_manager,
    )

    tool_installers = providers.Aggregate(
        AnsibleConfiguration=ansible_installer_factory,
        AnsibleCollectionConfiguration=ansible_collection_installer_factory,
        GccBuildConfiguration=gcc_sources_installer_factory,
        CmakeBuildConfiguration=cmake_sources_installer_factory,
        DownloadOnlyConfiguration=download_only_sources_installer_factory,
        CppCheckBuildConfiguration=cppcheck_sources_installer_factory,
        SourceBuildConfiguration=tool_source_installer_factory,
        ClangBuildConfiguration=clang_sources_installer_factory,
        ValgrindBuildConfiguration=valgrind_sources_installer_factory,
        DownloadOnlyCompilerConfiguration=download_only_compiler_installer_factory,
        JdkConfiguration=jdk_installer_factory,
        MavenConfiguration=maven_installer_factory,
    )


container_instance = Container()
