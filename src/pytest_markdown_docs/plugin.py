import ast
import inspect
from pathlib import Path
import traceback
import types
import pytest
import typing

from _pytest._code import ExceptionInfo
from _pytest.config.argparsing import Parser
from _pytest.pathlib import import_path

from pytest_markdown_docs import hooks
from _pytest.fixtures import FixtureRequest

MARKER_NAME = "markdown-docs"


class MarkdownInlinePythonItem(pytest.Item):
    def __init__(
        self,
        name: str,
        parent: typing.Union["MarkdownDocstringCodeModule", "MarkdownTextFile"],
        code: str,
        usefixtures: typing.List[str],
        fspath: Path,
        start_line: int,
        fake_line_numbers: bool,
    ) -> None:
        super().__init__(name, parent)
        self.add_marker(MARKER_NAME)
        self.code = code
        self.user_properties.append(("code", code))
        self.fspath = fspath
        self.start_line = start_line
        self.fake_line_numbers = fake_line_numbers

        self.usefixtures = usefixtures
        self.add_marker(pytest.mark.usefixtures(*usefixtures))

    def setup(self):
        def func() -> None:
            pass

        self.funcargs = {}
        self._fixtureinfo = self.session._fixturemanager.getfixtureinfo(
            node=self, func=func, cls=None, funcargs=False
        )
        self.fixture_request = FixtureRequest(self, _ispytest=True)
        self.fixture_request._fillfixtures()

    def runtest(self):
        global_sets = self.parent.config.hook.pytest_markdown_docs_globals()

        mod = types.ModuleType("fence")  # dummy module
        all_globals = mod.__dict__
        for global_set in global_sets:
            all_globals.update(global_set)

        for fixture_name in self.usefixtures:
            fixture_value = self.fixture_request.getfixturevalue(fixture_name)
            all_globals[fixture_name] = fixture_value

        try:
            tree = ast.parse(self.code)
        except SyntaxError:
            return

        try:
            # if we don't compile the code, it seems we gate name lookup errors
            # for functions etc. when doing cross-calls across inline functions
            compiled = compile(tree, self.name, "exec", dont_inherit=True)
        except SyntaxError:
            return

        exec(compiled, all_globals)

    def repr_failure(
        self,
        excinfo: ExceptionInfo[BaseException],
        style=None,
    ):
        rawlines = self.code.split("\n")

        # custom formatted traceback to translate line numbers and markdown files
        traceback_lines = []
        stack_summary = traceback.StackSummary.extract(traceback.walk_tb(excinfo.tb))
        start_capture = False

        start_line = 0 if self.fake_line_numbers else self.start_line

        for frame_summary in stack_summary:
            if frame_summary.filename == self.name:
                lineno = (frame_summary.lineno or 0) + start_line
                start_capture = (
                    True  # start capturing frames the first time we enter user code
                )
                line = rawlines[frame_summary.lineno - 1] if frame_summary.lineno else ""
            else:
                lineno = frame_summary.lineno or 0
                line = frame_summary.line or ""

            if start_capture:
                linespec = f"line {lineno}"
                if self.fake_line_numbers:
                    linespec = f"code block line {lineno}*"

                traceback_lines.append(
                    f"""  File "{frame_summary.filename}", {linespec}, in {frame_summary.name}"""
                )
                traceback_lines.append(f"    {line.lstrip()}")

        maxnum = len(str(len(rawlines) + start_line + 1))
        numbered_code = "\n".join(
            [
                f"{i:>{maxnum}}   {line}"
                for i, line in enumerate(rawlines, start_line + 1)
            ]
        )

        pretty_traceback = "\n".join(traceback_lines)
        note = ""
        if self.fake_line_numbers:
            note = ", *-denoted line numbers refer to code block"
        pt = f"""Traceback (most recent call last{note}):
{pretty_traceback}
{excinfo.exconly()}"""

        return f"""Error in code block:
```
{numbered_code}
```
{pt}
"""

    def reportinfo(self):
        return self.name, 0, f"docstring for {self.name}"


def extract_code_blocks(markdown_string: str) -> typing.Generator[tuple[str, list[str], int], None, None]:
    import markdown_it

    mi = markdown_it.MarkdownIt(config="commonmark")
    tokens = mi.parse(markdown_string)

    prev = ""
    for block in tokens:
        if block.type != "fence" or not block.map:
            continue

        startline = block.map[0] + 1  # skip the info line when counting
        code_info = block.info.split()

        lang = code_info[0] if code_info else None

        if lang in ("py", "python", "python3") and not "notest" in code_info:
            code_block = block.content

            if "continuation" in code_info:
                code_block = prev + code_block
                startline = (
                    -1
                )  # this disables proper line numbers, TODO: adjust line numbers *per snippet*

            fixture_names = [
                f[len("fixture:") :] for f in code_info if f.startswith("fixture:")
            ]
            yield code_block, fixture_names, startline
            prev = code_block


def find_object_tests_recursive(
    module_name: str, object_name: str, object: typing.Any
) -> typing.Generator[tuple[str, list[str], int], None, None]:
    docstr = inspect.getdoc(object)

    if docstr:
        yield from extract_code_blocks(docstr)

    for member_name, member in inspect.getmembers(object):
        if member_name.startswith("_"):
            continue

        if (
            inspect.isclass(member)
            or inspect.isfunction(member)
            or inspect.ismethod(member)
        ) and member.__module__ == module_name:
            yield from find_object_tests_recursive(module_name, member_name, member)


class MarkdownDocstringCodeModule(pytest.Module):
    def collect(self):
        module = import_path(self.fspath)
        for test_code, fixture_names, start_line in find_object_tests_recursive(
            module.__name__, module.__name__, module
        ):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=str(self.fspath),
                code=test_code,
                usefixtures=fixture_names,
                fspath=self.fspath,
                start_line=start_line,
                fake_line_numbers=True,  # TODO: figure out where docstrings are in file to offset line numbers properly
            )


class MarkdownTextFile(pytest.File):
    def collect(self):
        markdown_content = self.fspath.read_text("utf8")

        for code_block, fixture_names, start_line in extract_code_blocks(
            markdown_content
        ):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=str(self.fspath),
                code=code_block,
                usefixtures=fixture_names,
                fspath=self.fspath,
                start_line=start_line,
                fake_line_numbers=start_line == -1,
            )


def pytest_collect_file(
    path,
    parent,
):
    if parent.config.option.markdowndocs:
        if path.ext == ".py":
            return MarkdownDocstringCodeModule.from_parent(parent, fspath=path)
        elif path.ext in (".md", ".mdx", ".svx"):
            return MarkdownTextFile.from_parent(parent, fspath=path)

    return None


def pytest_configure(config):
    config.addinivalue_line(
        "markers", f"{MARKER_NAME}: filter for pytest-markdown-docs generated tests"
    )


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("collect")
    group.addoption(
        "--markdown-docs",
        action="store_true",
        default=False,
        help="run ",
        dest="markdowndocs",
    )


def pytest_addhooks(pluginmanager):
    pluginmanager.add_hookspecs(hooks)
