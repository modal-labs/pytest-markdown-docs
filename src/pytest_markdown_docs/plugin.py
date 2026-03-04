import inspect
import types
import pathlib

import pytest
import typing
from enum import Enum

from _pytest._code import ExceptionInfo
from _pytest.config.argparsing import Parser
from _pytest.pathlib import import_path
import logging

from pytest_markdown_docs import hooks
from pytest_markdown_docs.definitions import FenceTestDefinition, ObjectTestDefinition
from pytest_markdown_docs._runners import get_runner

if pytest.version_tuple >= (8, 0, 0):
    from _pytest.fixtures import TopRequest
else:
    # pytest 7 compatible
    from _pytest.fixtures import FixtureRequest as TopRequest  # type: ignore


if typing.TYPE_CHECKING:
    from markdown_it.token import Token
    from markdown_it import MarkdownIt

logger = logging.getLogger("pytest-markdown-docs")

MARKER_NAME = "markdown-docs"


class FenceSyntax(Enum):
    default = "default"
    superfences = "superfences"


def get_docstring_start_line(obj) -> typing.Optional[int]:
    # Get the source lines and the starting line number of the object
    try:
        source_lines, start_line = inspect.getsourcelines(obj)
    except OSError:
        return None

    # Find the line in the source code that starts with triple quotes (""" or ''')
    for idx, line in enumerate(source_lines):
        line = line.strip()
        if line.startswith(('"""', "'''")):
            return start_line + idx  # Return the starting line number

    return None  # Docstring not found in source


def _get_asyncio_runner(fixture_request):
    """Try to fetch pytest-asyncio's event loop runner for shared-loop execution."""
    try:
        return fixture_request.getfixturevalue("_function_scoped_runner")
    except Exception:
        return None


class MarkdownInlinePythonItem(pytest.Item):
    def __init__(
        self,
        name: str,
        parent: typing.Union["MarkdownDocstringCodeModule", "MarkdownTextFile"],
        test_definition: FenceTestDefinition,
    ) -> None:
        super().__init__(name, parent)
        self.add_marker(MARKER_NAME)
        self.code = test_definition.source
        self.obj = None
        self.test_definition = test_definition
        self.user_properties.append(("code", test_definition.source))
        self.start_line = test_definition.start_line
        self.fixturenames = test_definition.fixture_names
        self.nofuncargs = True
        self.runner_name = test_definition.runner_name

    def setup(self):
        def func() -> None:
            pass

        self.funcargs = {}
        self._fixtureinfo = self.session._fixturemanager.getfixtureinfo(
            node=self, func=func, cls=None
        )
        self.fixture_request = TopRequest(self, _ispytest=True)
        self.fixture_request._fillfixtures()
        self.runner = get_runner(self.runner_name)

    def runtest(self):
        global_sets = self.parent.config.hook.pytest_markdown_docs_globals()

        mod = types.ModuleType("fence")  # dummy module
        all_globals = mod.__dict__
        for global_set in global_sets:
            all_globals.update(global_set)

        # make sure to evaluate fixtures
        # this will insert named fixtures into self.funcargs
        for fixture_name in self._fixtureinfo.names_closure:
            self.fixture_request.getfixturevalue(fixture_name)

        # Since these are not actual functions with arguments, the only
        # arguments that should appear in self.funcargs are the filled fixtures
        for argname, value in self.funcargs.items():
            all_globals[argname] = value

        # Retry logic
        max_retries = self.test_definition.max_retries
        max_attempts = max_retries + 1  # +1 for initial attempt

        last_exception = None
        for attempt in range(max_attempts):
            try:
                # this ensures that pytest's stdout/stderr capture works during the test:
                capman = self.config.pluginmanager.getplugin("capturemanager")
                asyncio_runner = _get_asyncio_runner(self.fixture_request)
                with capman.global_and_fixture_disabled():
                    try:
                        self.runner.runtest(
                            self.test_definition,
                            all_globals,
                            asyncio_runner=asyncio_runner,
                        )
                    except TypeError:
                        # Custom runner doesn't accept asyncio_runner kwarg
                        self.runner.runtest(self.test_definition, all_globals)

                # Success - test passed
                if attempt > 0:
                    # Record retry count for reporting
                    self.user_properties.append(("retries", str(attempt)))
                return

            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    # Not the last attempt, will retry
                    continue
                else:
                    # Last attempt failed, re-raise
                    raise

        # Safety fallback (should not reach here)
        if last_exception:
            raise last_exception

    def repr_failure(
        self,
        excinfo: ExceptionInfo[BaseException],
        style=None,
    ) -> str:
        return self.runner.repr_failure(self.test_definition, excinfo, style)

    def reportinfo(self):
        return self.path, self.start_line, self.name


def get_prefixed_strings(
    seq: typing.Collection[str], prefix: str
) -> typing.Sequence[str]:
    # return strings matching a prefix, with the prefix stripped
    return tuple(s[len(prefix) :] for s in seq if s.startswith(prefix))


def extract_fence_tests(
    markdown_it_parser: "MarkdownIt",
    markdown_string: str,
    start_line_offset: int,
    source_path: pathlib.Path,
    markdown_type: str = "md",
    fence_syntax: FenceSyntax = FenceSyntax.default,
) -> typing.Generator[FenceTestDefinition, None, None]:
    tokens = markdown_it_parser.parse(markdown_string)

    prev = ""
    for i, block in enumerate(tokens):
        if block.type != "fence" or not block.map:
            continue

        if fence_syntax == FenceSyntax.superfences:
            code_info = parse_superfences_block_info(block.info)
        else:
            code_info = block.info.split()

        lang = code_info[0] if code_info else None
        code_options = set(code_info) - {lang}

        if markdown_type == "mdx":
            # In MDX, comments are enclosed within a paragraph block and must be
            # placed directly above the corresponding code fence. The token
            # sequence is as follows:
            #   i-3: paragraph_open
            #   i-2: comment
            #   i-1: paragraph_close
            #   i: code fence
            #
            # Therefore, to retrieve the MDX comment associated with the current
            # code fence (at index `i`), we need to access the token at `i - 2`.
            if i >= 2 and is_mdx_comment(tokens[i - 2]):
                code_options |= extract_options_from_mdx_comment(tokens[i - 2].content)

        if lang in ("py", "python", "python3") and "notest" not in code_options:
            start_line = (
                start_line_offset + block.map[0] + 1
            )  # actual code starts on +1 from the "info" line
            if "continuation" not in code_options:
                prev = ""

            add_blank_lines = start_line - prev.count("\n")
            code_block = prev + ("\n" * add_blank_lines) + block.content

            fixture_names = get_prefixed_strings(code_options, "fixture:")
            runner_names = get_prefixed_strings(code_options, "runner:")
            if len(runner_names) == 0:
                runner_name = None
            elif len(runner_names) > 1:
                raise Exception(
                    f"Multiple runners are not supported, use a single one instead: {runner_names}"
                )
            else:
                runner_name = runner_names[0]

            retry_counts = get_prefixed_strings(code_options, "retry:")
            if len(retry_counts) == 0:
                max_retries = 0
            elif len(retry_counts) > 1:
                raise Exception(
                    f"Multiple retry counts are not supported, use a single one instead: {retry_counts}"
                )
            else:
                try:
                    max_retries = int(retry_counts[0])
                    if max_retries < 0:
                        raise ValueError("Retry count must be non-negative")
                except ValueError as e:
                    raise Exception(
                        f"Invalid retry count '{retry_counts[0]}': must be a non-negative integer"
                    ) from e

            yield FenceTestDefinition(
                code_block,
                fixture_names,
                start_line,
                source_path=source_path,
                runner_name=runner_name,
                max_retries=max_retries,
            )
            prev = code_block


def parse_superfences_block_info(block_info: str) -> typing.List[str]:
    """Parse PyMdown Superfences block info syntax.

    The default `python continuation` format is not compatible with Material for Mkdocs.
    But, PyMdown Superfences has a special brace format to add options to code fence blocks: `{.<lang> <option1> <option2>}`.

    This function also works if the default syntax is used to allow for mixed usage.
    """
    block_info = block_info.strip()

    if not block_info.startswith("{"):
        # default syntax
        return block_info.split()

    block_info = block_info.strip("{}")
    code_info = block_info.split()
    # Lang may not be the first but is always the first element that starts with a dot.
    # (https://facelessuser.github.io/pymdown-extensions/extensions/superfences/#injecting-classes-ids-and-attributes)
    dot_lang = next(
        (info_part for info_part in code_info if info_part.startswith(".")), None
    )
    if dot_lang:
        code_info.remove(dot_lang)
        lang = dot_lang[1:]
        code_info.insert(0, lang)
    return code_info


def is_mdx_comment(block: "Token") -> bool:
    return (
        block.type == "inline"
        and block.content.strip().startswith("{/*")
        and block.content.strip().endswith("*/}")
        and "pmd-metadata:" in block.content
    )


def extract_options_from_mdx_comment(comment: str) -> typing.Set[str]:
    comment = (
        comment.strip()
        .replace("{/*", "")
        .replace("*/}", "")
        .replace("pmd-metadata:", "")
    )
    return set(option.strip() for option in comment.split(" ") if option)


def _preprocess_async_fixtures_if_available(collector: pytest.Collector) -> None:
    """
    If pytest-asyncio is installed, trigger its async fixture preprocessing.

    pytest-asyncio preprocesses async fixtures during collection, but only for
    pytest.Module and pytest.Class collectors. We need to trigger this manually
    for our markdown collectors so that async fixtures work correctly.
    """
    try:
        from pytest_asyncio.plugin import (  # type: ignore
            _preprocess_async_fixtures,
            _HOLDER,
        )

        _preprocess_async_fixtures(collector, _HOLDER)
    except ImportError:
        # pytest-asyncio is not installed, or using a newer version that
        # doesn't require these imports
        pass


class MarkdownDocstringCodeModule(pytest.Module):
    def collect(self):
        # Trigger pytest-asyncio's async fixture preprocessing if available
        # (needed for pytest-asyncio 0.23.x; 1.x uses pytest_fixture_setup hook instead)
        _preprocess_async_fixtures_if_available(self)

        if pytest.version_tuple >= (8, 1, 0):
            # consider_namespace_packages is a required keyword argument in pytest 8.1.0
            module = import_path(
                self.path, root=self.config.rootpath, consider_namespace_packages=True
            )
        else:
            # but unsupported before pytest 8.1...
            module = import_path(self.path, root=self.config.rootpath)

        for object_test in self.find_object_tests_recursive(
            module.__name__, module, set(), set()
        ):
            fence_test = object_test.fence_test
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=f"{object_test.object_name}[CodeFence#{object_test.intra_object_index + 1}][line:{fence_test.start_line}]",
                test_definition=fence_test,
            )

    def find_object_tests_recursive(
        self,
        module_name: str,
        object: typing.Any,
        _visited_objects: typing.Set[int],
        _found_tests: typing.Set[typing.Tuple[str, int]],
    ) -> typing.Generator[ObjectTestDefinition, None, None]:
        if id(object) in _visited_objects:
            return
        _visited_objects.add(id(object))
        docstr = inspect.getdoc(object)

        for member_name, member in inspect.getmembers(object):
            if (
                inspect.isclass(member)
                or inspect.isfunction(member)
                or inspect.ismethod(member)
            ) and member.__module__ == module_name:
                yield from self.find_object_tests_recursive(
                    module_name, member, _visited_objects, _found_tests
                )

        if docstr:
            docstring_offset = get_docstring_start_line(object)
            if docstring_offset is None:
                logger.warning(
                    f"Could not find line number offset for docstring: {docstr}"
                )
            else:
                obj_name = (
                    getattr(object, "__qualname__", None)
                    or getattr(object, "__name__", None)
                    or "<Unnamed obj>"
                )
                fence_syntax = FenceSyntax(self.config.option.markdowndocs_syntax)
                markdown_it_parser = self.config.hook.pytest_markdown_docs_markdown_it()

                for i, fence_test in enumerate(
                    extract_fence_tests(
                        markdown_it_parser,
                        docstr,
                        docstring_offset,
                        source_path=self.path,
                        fence_syntax=fence_syntax,
                    )
                ):
                    found_test = ObjectTestDefinition(i, obj_name, fence_test)
                    found_test_location = (
                        module_name,
                        found_test.fence_test.start_line,
                    )
                    if found_test_location not in _found_tests:
                        _found_tests.add(found_test_location)
                        yield found_test


class MarkdownTextFile(pytest.File):
    def collect(self):
        # Trigger pytest-asyncio's async fixture preprocessing if available
        # (needed for pytest-asyncio 0.23.x; 1.x uses pytest_fixture_setup hook instead)
        _preprocess_async_fixtures_if_available(self)

        markdown_content = self.path.read_text("utf8")
        fence_syntax = FenceSyntax(self.config.option.markdowndocs_syntax)

        markdown_it_parser = self.config.hook.pytest_markdown_docs_markdown_it()

        for i, fence_test in enumerate(
            extract_fence_tests(
                markdown_it_parser,
                markdown_content,
                source_path=self.path,
                start_line_offset=0,
                markdown_type=self.path.suffix.replace(".", ""),
                fence_syntax=fence_syntax,
            )
        ):
            yield MarkdownInlinePythonItem.from_parent(
                self,
                name=f"[CodeFence#{i + 1}][line:{fence_test.start_line}]",
                test_definition=fence_test,
            )


def pytest_collect_file(
    file_path,
    parent,
):
    if parent.config.option.markdowndocs:
        pathlib_path = pathlib.Path(str(file_path))  # pytest 7/8 compat
        if pathlib_path.suffix == ".py":
            return MarkdownDocstringCodeModule.from_parent(parent, path=pathlib_path)
        elif pathlib_path.suffix in (".md", ".mdx", ".svx"):
            return MarkdownTextFile.from_parent(parent, path=pathlib_path)

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
    group.addoption(
        "--markdown-docs-syntax",
        action="store",
        choices=[choice.value for choice in FenceSyntax],
        default="default",
        help="Choose an alternative fences syntax",
        dest="markdowndocs_syntax",
    )


def pytest_addhooks(pluginmanager):
    pluginmanager.add_hookspecs(hooks)


@pytest.hookimpl
def pytest_markdown_docs_markdown_it() -> "MarkdownIt":
    from markdown_it import MarkdownIt

    return MarkdownIt(config="commonmark")
