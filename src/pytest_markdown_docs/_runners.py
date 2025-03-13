import abc
import ast
import traceback
import typing
from abc import abstractmethod

import pytest

from pytest_markdown_docs.definitions import FenceTestDefinition

_default_runner: typing.Optional["_Runner"] = None
_registered_runners = {}


class _Runner(metaclass=abc.ABCMeta):
    @abstractmethod
    def runtest(self, test: FenceTestDefinition, args: dict[str, typing.Any]): ...

    @abstractmethod
    def repr_failure(
        self,
        test: FenceTestDefinition,
        excinfo: pytest.ExceptionInfo[BaseException],
        style=None,
    ): ...


RUNNER_TYPE = typing.TypeVar("RUNNER_TYPE", bound=type[_Runner])


def register_runner(*, default: bool = False):
    """Decorator for adding custom runners

    e.g.
    @register_runner()
    def my_runner(src):
        exec(src)
    """

    def decorator(r: RUNNER_TYPE) -> RUNNER_TYPE:
        global _default_runner
        runner = r()
        _registered_runners[r.__name__] = runner
        if default:
            _default_runner = runner
        return r

    return decorator


@register_runner(default=True)
class DefaultRunner(_Runner):
    def runtest(self, test: FenceTestDefinition, args):
        try:
            tree = ast.parse(test.source, filename=test.source_path)
        except SyntaxError:
            raise

        try:
            # if we don't compile the code, it seems we get name lookup errors
            # for functions etc. when doing cross-calls across inline functions
            compiled = compile(
                tree, filename=test.source_path, mode="exec", dont_inherit=True
            )
        except SyntaxError:
            raise

        exec(compiled, args)

    def repr_failure(
        self,
        test: FenceTestDefinition,
        excinfo: pytest.ExceptionInfo[BaseException],
        style=None,
    ):
        """This renders a traceback starting at the stack from of the code fence

        Also displays a line-numbered excerpt of the code fence that ran.
        """

        rawlines = test.source.rstrip("\n").split("\n")

        # custom formatted traceback to translate line numbers and markdown files
        traceback_lines = []
        stack_summary = traceback.StackSummary.extract(traceback.walk_tb(excinfo.tb))
        start_capture = False

        start_line = test.start_line

        for frame_summary in stack_summary:
            if frame_summary.filename == str(test.source_path):
                # start capturing frames the first time we enter user code
                start_capture = True

            if start_capture:
                lineno = frame_summary.lineno
                line = frame_summary.line or ""
                linespec = f"line {lineno}"
                traceback_lines.append(
                    f"""  File "{frame_summary.filename}", {linespec}, in {frame_summary.name}"""
                )
                traceback_lines.append(f"    {line.lstrip()}")

        maxdigits = len(str(len(rawlines)))
        code_margin = "   "
        numbered_code = "\n".join(
            [
                f"{i:>{maxdigits}}{code_margin}{line}"
                for i, line in enumerate(rawlines[start_line:], start_line + 1)
            ]
        )

        pretty_traceback = "\n".join(traceback_lines)
        pt = f"""Traceback (most recent call last):
{pretty_traceback}
{excinfo.exconly()}"""

        return f"""Error in code block:
{maxdigits * " "}{code_margin}```
{numbered_code}
{maxdigits * " "}{code_margin}```
{pt}
"""


def get_runner(name: typing.Optional[str]) -> _Runner:
    if name is None:
        assert _default_runner is not None
        return _default_runner

    if name not in _registered_runners:
        raise Exception(f"No such pytest-markdown-docs runner: {name}")
    return _registered_runners[name]
