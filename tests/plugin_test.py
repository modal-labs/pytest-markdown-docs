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


def test_autouse_fixtures(testdir):
    testdir.makeconftest("""
import pytest

@pytest.fixture(autouse=True)
def initialize(request):
    import pytest_markdown_docs
    pytest_markdown_docs.bump = getattr(pytest_markdown_docs, "bump", 0) + 1
    yield
    pytest_markdown_docs.bump -= 1
""")

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
