import pytest_markdown  # hack: used for storing a side effect in one of the tests


def test_docstring_markdown(testdir):
    testdir.makeconftest(
        """
        def pytest_markdown_globals():
            return {"a": "hello"}
    """
    )
    testdir.makepyfile(
        """
        def simple():
            \"\"\"
            ```python
            import pytest_markdown
            pytest_markdown.side_effect = "hello"
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
    result = testdir.runpytest("--markdown-python")
    result.assert_outcomes(passed=2, failed=2)
    assert (
        getattr(pytest_markdown, "side_effect", None) == "hello"
    )  # hack to make sure the test actually does something


def test_markdown_text_file(testdir):
    testdir.makeconftest(
        """
        def pytest_markdown_globals():
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
    result = testdir.runpytest("--markdown-python")
    result.assert_outcomes(passed=1)
