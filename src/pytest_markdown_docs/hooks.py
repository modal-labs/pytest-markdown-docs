import pytest
import typing

if typing.TYPE_CHECKING:
    from markdown_it import MarkdownIt


def pytest_markdown_docs_globals() -> typing.Dict[str, typing.Any]:
    return {}


@pytest.hookspec(firstresult=True)
def pytest_markdown_docs_runner_name_for_language(
    language: str,
) -> typing.Optional[str]:
    """Return a registered runner name for a code fence language."""


@pytest.hookspec(firstresult=True)
def pytest_markdown_docs_markdown_it() -> "MarkdownIt":
    """Configure a custom markdown_it.MarkdownIt parser."""
    return MarkdownIt()
