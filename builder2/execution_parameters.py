from dataclasses import dataclass


@dataclass
class ExecutionParameters:
    core_count: int
    file_name: str
    time_multiplier: float
    target_dir: str
