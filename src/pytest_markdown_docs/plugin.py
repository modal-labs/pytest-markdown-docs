import inspect
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
        usefixtures: typing.List[str] = [],
    ) -> None:
        super().__init__(name, parent)
        self.add_marker(MARKER_NAME)
        self.code = code
        self.user_properties.append(("code", code))

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
        all_globals = {}
        for global_set in global_sets:
            all_globals.update(global_set)

        for fixture_name in self.usefixtures:
            fixture_value = self.fixture_request.getfixturevalue(fixture_name)
            all_globals[fixture_name] = fixture_value


        exec(self.code, all_globals)

    def repr_failure(
        self,
        excinfo: ExceptionInfo[BaseException],
        style=None,
    ):
        return f"Error in code block:\n```\n{self.code}\n```\n{excinfo.getrepr(style=style)}"

    def reportinfo(self):
        return self.name, 0, f"docstring for {self.name}"


def extract_code_blocks(markdown_string: str):
    import markdown_it

    mi = markdown_it.MarkdownIt(config="commonmark")
    tokens = mi.parse(markdown_string)

    prev = ""
    for block in tokens:
        if block.type != "fence":
            continue

        code_info = block.info.split()
        lang = code_info[0] if code_info else None
        if lang in ("py", "python", "python3") and not "notest" in code_info:
            code_block = block.content
            if "continuation" in code_info:
                code_block = prev + code_block

            fixture_names = [f[len("fixture:"):] for f in code_info if f.startswith("fixture:")]
            yield code_block, fixture_names
            prev = code_block


def find_object_tests_recursive(module_name: str, object_name: str, object: typing.Any):
    docstr = inspect.getdoc(object)

    if docstr:
        for snippet_ix, (code_block, fixture_names) in enumerate(extract_code_blocks(docstr)):
            yield f"{object_name} Code fence #{snippet_ix}", code_block, fixture_names

    for member_name, member in inspect.getmembers(object):
        if member_name.startswith("_"):
            continue

        if (
            inspect.isclass(member) or inspect.isfunction(member) or inspect.ismethod(member)
        ) and member.__module__ == module_name:
            yield from find_object_tests_recursive(module_name, member_name, member)


class MarkdownDocstringCodeModule(pytest.Module):
    def collect(self):
        module = import_path(self.fspath)
        for test_name, test_code, fixture_names in find_object_tests_recursive(module.__name__, module.__name__, module):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=test_name,
                code=test_code,
                usefixtures=fixture_names,
            )


class MarkdownTextFile(pytest.File):
    def collect(self):
        markdown_content = self.fspath.read_text("utf8")

        for snippet_ix, (code_block, fixture_names) in enumerate(extract_code_blocks(markdown_content)):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=f"Code fence #{snippet_ix}",
                code=code_block,
                usefixtures=fixture_names,
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
    config.addinivalue_line("markers", f"{MARKER_NAME}: filter for pytest-markdown-docs generated tests")


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
