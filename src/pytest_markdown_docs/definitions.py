import pathlib
import typing
from dataclasses import dataclass


@dataclass(frozen=True)
class FenceTestDefinition:
    source: str
    fixture_names: typing.Sequence[str]
    start_line: int
    source_path: pathlib.Path
    runner_name: typing.Optional[str]


@dataclass(frozen=True)
class ObjectTestDefinition:
    intra_object_index: int
    object_name: str
    fence_test: FenceTestDefinition
