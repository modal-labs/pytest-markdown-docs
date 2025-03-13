import re

from _pytest.pytester import LineMatcher

import pytest_markdown_docs  # hack: used for storing a side effect in one of the tests


def test_docstring_markdown(testdir):
    testdir.makeconftest(
        """
        def pytest_markdown_docs_globals():
            return {"a": "hello"}
    """
    )
    testdir.makepyfile(
        """
        def simple():
            \"\"\"
            ```python
            import pytest_markdown_docs
            pytest_markdown_docs.side_effect = "hello"
            ```

            ```
            not a python block
            ```
            \"\"\"


        class Parent:
            def using_global(self):
                \"\"\"
                ```python
                assert a + " world" == "hello world"
                ```
                \"\"\"

        def failing():
            \"\"\"
            ```python
            assert False
            ```
            \"\"\"

        def error():
            \"\"\"
            ```python
            raise Exception("oops")
            ```
            \"\"\"
    """
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=2, failed=2)
    assert (
        getattr(pytest_markdown_docs, "side_effect", None) == "hello"
    )  # hack to make sure the test actually does something


def test_markdown_text_file(testdir):
    testdir.makeconftest(
        """
        def pytest_markdown_docs_globals():
            return {"a": "hello"}
    """
    )

    testdir.makefile(
        ".md",
        """
        ```python
        assert a + " world" == "hello world"
        ```

        ```python
        assert False
        ```

        ```python
        **@ # this is a syntax error
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1, failed=2)


def test_continuation(testdir):
    testdir.makefile(
        ".md",
        """
        ```python
        b = "hello"
        ```

        ```python continuation
        assert b + " world" == "hello world"
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=2)


def test_traceback(testdir):
    testdir.makefile(
        ".md",
        """
        yada yada yada

        ```python
        def foo():
            raise Exception("doh")

        def bar():
            foo()

        foo()
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=0, failed=1)

    # we check the traceback vs a regex pattern since the file paths can change
    expected_output_pattern = r"""
Error in code block:
     ```
 4   def foo\(\):
 5       raise Exception\("doh"\)
 6
 7   def bar\(\):
 8       foo\(\)
 9
10   foo\(\)
     ```
Traceback \(most recent call last\):
  File ".*/test_traceback.md", line 10, in <module>
    foo\(\)
  File ".*/test_traceback.md", line 5, in foo
    raise Exception\("doh"\)
Exception: doh
""".strip()
    pytest_output = "\n".join(line.rstrip() for line in result.outlines).strip()
    assert re.search(expected_output_pattern, pytest_output) is not None, (
        "Output traceback doesn't match expected value"
    )


def test_autouse_fixtures(testdir):
    testdir.makeconftest(
        """
import pytest

@pytest.fixture(autouse=True)
def initialize():
    import pytest_markdown_docs
    pytest_markdown_docs.bump = getattr(pytest_markdown_docs, "bump", 0) + 1
    yield
    pytest_markdown_docs.bump -= 1
"""
    )

    testdir.makefile(
        ".md",
        """
        ```python
        import pytest_markdown_docs
        assert pytest_markdown_docs.bump == 1
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1)


def test_specific_fixtures(testdir):
    testdir.makeconftest(
        """
import pytest

@pytest.fixture()
def initialize_specific():
    import pytest_markdown_docs
    pytest_markdown_docs.bump = getattr(pytest_markdown_docs, "bump", 0) + 1
    yield "foobar"
    pytest_markdown_docs.bump -= 1
"""
    )

    testdir.makefile(
        ".md",
        """
        \"\"\"
        ```python fixture:initialize_specific
        import pytest_markdown_docs
        assert pytest_markdown_docs.bump == 1
        assert initialize_specific == "foobar"
        ```
        \"\"\"
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1)


def test_non_existing_fixture_error(testdir):
    testdir.makeconftest(
        """
import pytest

@pytest.fixture()
def foo():
    pass
"""
    )

    testdir.makefile(
        ".md",
        """
        \"\"\"
        ```python fixture:bar
        ```
        \"\"\"
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    assert "fixture 'bar' not found" in result.stdout.str()
    result.assert_outcomes(errors=1)


def test_fixture_overriding_global(testdir):
    testdir.makeconftest(
        """
import pytest

def pytest_markdown_docs_globals():
    return {
        "some_global": "foo"
    }

@pytest.fixture()
def some_global():
    return "bar"
"""
    )

    testdir.makefile(
        ".md",
        """
        \"\"\"
        ```python
        assert some_global == "foo"
        ```

        ```python fixture:some_global
        assert some_global == "bar"
        ```
        \"\"\"
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=2)


def test_continuation_mdx_comment(testdir):
    testdir.makefile(
        ".mdx",
        """
        ```python
        b = "hello"
        ```
        {/* pmd-metadata: continuation */}
        ```python
        assert b + " world" == "hello world"
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=2)


def test_specific_fixture_mdx_comment(testdir):
    testdir.makeconftest(
        """
import pytest
@pytest.fixture()
def initialize_specific():
    import pytest_markdown_docs
    pytest_markdown_docs.bump = getattr(pytest_markdown_docs, "bump", 0) + 1
    yield "foobar"
    pytest_markdown_docs.bump -= 1
"""
    )

    testdir.makefile(
        ".mdx",
        """
        {/* pmd-metadata: fixture:initialize_specific */}
        ```python
        import pytest_markdown_docs
        assert pytest_markdown_docs.bump == 1
        assert initialize_specific == "foobar"
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1)


def test_multiple_fixtures_mdx_comment(testdir):
    testdir.makeconftest(
        """
import pytest
@pytest.fixture()
def initialize_specific():
    import pytest_markdown_docs
    pytest_markdown_docs.bump = getattr(pytest_markdown_docs, "bump", 0) + 1
    yield "foobar"
    pytest_markdown_docs.bump -= 1

@pytest.fixture
def another_fixture():
    return "hello"
"""
    )

    testdir.makefile(
        ".mdx",
        """
        {/* pmd-metadata: fixture:initialize_specific fixture:another_fixture */}
        ```python
        import pytest_markdown_docs
        assert pytest_markdown_docs.bump == 1
        assert initialize_specific == "foobar"
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1)


def test_notest_mdx_comment(testdir):
    testdir.makefile(
        ".mdx",
        """
        {/* pmd-metadata: notest */}
        ```python
        assert True
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=0)


def test_superfences_format_markdown(testdir):
    testdir.makefile(
        ".md",
        """
        ```python
        b = "hello"
        ```

        ```{.python continuation}
        assert b + " world" == "hello world"
        ```

        # the lang may not be the first element
        ```{other_option .python .other-class continuation}
        assert b + " world" == "hello world"
        ```
    """,
    )
    result = testdir.runpytest("--markdown-docs", "--markdown-docs-syntax=superfences")
    result.assert_outcomes(passed=3)


def test_superfences_format_docstring(testdir):
    testdir.makepyfile(
        """
        def simple():
            \"\"\"
            ```python
            b = "hello"
            ```

            ```{.python continuation}
            assert b + " world" == "hello world"
            ```
            \"\"\"
        """
    )
    result = testdir.runpytest("--markdown-docs", "--markdown-docs-syntax=superfences")
    result.assert_outcomes(passed=2)


def test_error_origin_after_docstring_traceback(testdir, support_dir):
    sample_file = support_dir / "docstring_error_after.py"
    testdir.makepyfile(**{sample_file.stem: sample_file.read_text()})
    result = testdir.runpytest("-v", "--markdown-docs")

    data: LineMatcher = result.stdout
    data.re_match_lines(
        [
            r"Traceback \(most recent call last\):",
            r'\s*File ".*/docstring_error_after.py", line 5, in <module>',
            r"\s*docstring_error_after.error_after\(\)",
            r'\s*File ".*/docstring_error_after.py", line 11, in error_after',
            r'\s*raise Exception\("bar"\)',
            r"\s*Exception: bar",
        ],
        consecutive=True,
    )


def test_error_origin_before_docstring_traceback(testdir, support_dir):
    sample_file = support_dir / "docstring_error_before.py"
    testdir.makepyfile(**{sample_file.stem: sample_file.read_text()})
    result = testdir.runpytest("-v", "--markdown-docs")

    data: LineMatcher = result.stdout
    data.re_match_lines(
        [
            r"Traceback \(most recent call last\):",
            r'\s*File ".*/docstring_error_before.py", line 9, in <module>',
            r"\s*docstring_error_before.error_before\(\)",
            r'\s*File ".*/docstring_error_before.py", line 2, in error_before',
            r'\s*raise Exception\("foo"\)',
            r"\s*Exception: foo",
        ],
        consecutive=True,
    )


def test_custom_runner(testdir):
    testdir.makeconftest(
        """
        import pytest_markdown_docs._runners
        
        @pytest_markdown_docs._runners.register_runner()
        class LinesAreAllFoo(pytest_markdown_docs._runners.DefaultRunner):
            def runtest(self, test, args):
                lines = test.source.strip().split("\\n")
                for line in lines:
                    assert line == "foo"
    """
    )
    testdir.makefile(
        ".md",
        """
        ```python runner:LinesAreAllFoo
        foo
        foo
        ```
        
        ```python runner:LinesAreAllFoo
        foo
        bar
        ```
    """,
    )

    result = testdir.runpytest("-v", "--markdown-docs")
    result.assert_outcomes(passed=1, failed=1)
    result.stdout.re_match_lines(
        [
            r".*\[CodeFence#1\]\[line:1\].*PASSED.*",
            r".*\[CodeFence#2\]\[line:6\].*FAILED.*",
        ],
        consecutive=True,
    )
