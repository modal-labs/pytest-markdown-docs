def error_before():
    raise Exception("foo")


def func():
    """
    ```python
    import docstring_error_before
    docstring_error_before.error_before()
    ```
    """
