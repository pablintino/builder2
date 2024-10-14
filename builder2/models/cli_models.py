from dataclasses import dataclass


@dataclass(frozen=True)
class CliInstallArgs:
    core_count: int = None
    timeout_multiplier: int = None
