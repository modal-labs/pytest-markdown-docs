def func():
    """
    ```python
    import docstring_error_after
    docstring_error_after.error_after()
    ```
    """


def error_after():
    raise Exception("bar")
