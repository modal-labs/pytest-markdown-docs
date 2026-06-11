import abc
import ast
import inspect
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
    def runtest(self, test: FenceTestDefinition, args, *, asyncio_runner=None):
        try:
            compiled = compile(
                test.source,
                filename=test.source_path,
                mode="exec",
                flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT,
                dont_inherit=True,
            )
        except SyntaxError:
            raise

        if compiled.co_flags & inspect.CO_COROUTINE:
            if asyncio_runner is None:
                raise RuntimeError(
                    "Top-level async code in markdown code blocks is not natively supported.\n"
                    "You need pytest-asyncio>=1.1.0 to run async code blocks:\n"
                    "  pip install 'pytest-asyncio>=1.1.0'"
                )
            coro = eval(compiled, args)
            asyncio_runner.run(coro)
        else:
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
