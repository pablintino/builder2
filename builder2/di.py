import dataclasses
from typing import Dict

from dependency_injector import containers, providers

from builder2.certificate_manager import CertificateManager
from builder2.command_line import CommandRunner
from builder2.conan_manager import ConanManager
from builder2.cryptographic_provider import CryptographicProvider
from builder2.environment_builder import EnvironmentBuilder
from builder2.file_manager import FileManager
from builder2.models.metadata_models import BaseComponentConfiguration
from builder2.package_manager import PackageManager
from builder2.tools import (
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
    CompilersSupport,
    JavaTools,
)


@dataclasses.dataclass
class Dispatcher:
    installers: Dict[BaseComponentConfiguration, ToolInstaller]


class Container(containers.DeclarativeContainer):
    config = providers.Configuration(strict=True)

    file_manager = providers.Singleton(FileManager)

    command_runner = providers.Singleton(CommandRunner)

    compilers_support = providers.Singleton(
        CompilersSupport, file_manager, command_runner
    )

    certificate_manager = providers.Singleton(
        CertificateManager, file_manager, command_runner
    )

    cryptographic_provider = providers.Singleton(CryptographicProvider, file_manager)

    package_manager = providers.Singleton(PackageManager, command_runner)

    conan_manager = providers.Singleton(ConanManager, file_manager, command_runner)

    java_tools = providers.Singleton(JavaTools, file_manager, command_runner)

    environment_builder = providers.Singleton(EnvironmentBuilder)

    maven_installer_factory = providers.Factory(
        MavenInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    jdk_installer_factory = providers.Factory(
        JdkInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        java_tools=java_tools,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    gcc_sources_installer_factory = providers.Factory(
        GccSourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        compilers_support=compilers_support,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    cmake_sources_installer_factory = providers.Factory(
        CMakeSourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    cppcheck_sources_installer_factory = providers.Factory(
        CppCheckSourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    download_only_sources_installer_factory = providers.Factory(
        DownloadOnlySourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    download_only_compiler_installer_factory = providers.Factory(
        DownloadOnlyCompilerInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        compilers_support=compilers_support,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    valgrind_sources_installer_factory = providers.Factory(
        ValgrindSourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    clang_sources_installer_factory = providers.Factory(
        ClangSourcesInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        compilers_support=compilers_support,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    tool_source_installer_factory = providers.Factory(
        ToolSourceInstaller,
        file_manager=file_manager,
        cryptographic_provider=cryptographic_provider,
        command_runner=command_runner,
        package_manager=package_manager,
        core_count=config.core_count,
        time_multiplier=config.timout_mult,
    )

    tool_installers = providers.Aggregate(
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
