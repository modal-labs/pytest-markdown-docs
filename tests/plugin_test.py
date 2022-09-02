import re
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
        \"\"\"
        ```python
        assert a + " world" == "hello world"
        ```
        \"\"\"
    """,
    )

    # run all tests with pytest
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=1)


def test_traceback(testdir):
    testdir.makefile(
        ".md",
        """
        \"\"\"
        yada yada yada

        ```python
        def foo():
            raise Exception("doh")

        def bar():
            foo()

        foo()
        ```
        \"\"\"
    """,
    )
    result = testdir.runpytest("--markdown-docs")
    result.assert_outcomes(passed=0, failed=1)

    expected_output_pattern = r"""
Error in code block:
```
 5   def foo\(\):
 6       raise Exception\("doh"\)
 7
 8   def bar\(\):
 9       foo\(\)
10
11   foo\(\)
12
```
Traceback \(most recent call last\):
  File ".*/test_traceback.md", line 11, in <module>
    foo\(\)
  File ".*/test_traceback.md", line 6, in foo
    raise Exception\("doh"\)
Exception: doh
""".strip()
    pytest_output = "\n".join(l.rstrip() for l in result.outlines).strip()
    assert re.search(expected_output_pattern, pytest_output) is not None


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
        \"\"\"
        ```python
        import pytest_markdown_docs
        assert pytest_markdown_docs.bump == 1
        ```
        \"\"\"
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
