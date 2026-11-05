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
    max_retries: int = 0
    # All options on the fence (everything after the language in the info
    # string, plus any mdx-comment metadata), including ones the plugin itself
    # consumes, e.g. `fixture:foo` and `continuation`. Lets custom runners
    # define their own options without requiring a pytest fixture per flag.
    options: typing.FrozenSet[str] = frozenset()


@dataclass(frozen=True)
class ObjectTestDefinition:
    intra_object_index: int
    object_name: str
    fence_test: FenceTestDefinition
