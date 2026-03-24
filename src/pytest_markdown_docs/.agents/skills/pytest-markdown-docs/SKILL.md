---
name: pytest-markdown-docs
description: pytest-markdown-docs best practices, fixture patterns, and adoption conventions. Use when testing Python code snippets embedded in Markdown or MDX documentation files. Covers conftest.py fixture design, fence annotations, custom runners, mock strategies, and debugging common snippet test failures.
---

# pytest-markdown-docs

pytest plugin that collects Python code fences from `.md`, `.mdx`, and `.svx` files (and Python docstrings) and runs each as an isolated pytest test.

## How Snippets Are Collected

All Python fences (` ```python `) are collected and executed automatically. No annotation needed for self-contained snippets. Non-Python fences (bash, json, toml, mermaid) are ignored.

Invocation:

```shell
pytest --markdown-docs docs/
```

Do NOT add `--markdown-docs` to `[tool.pytest.ini_options] addopts`. Keep doc tests invoked separately from the main test suite.

## Fence Annotations

### In `.md` files, annotations go on the fence info line:

````markdown
```python fixture:my_var fixture:other_var
code using my_var and other_var
```
````

### In `.mdx` files, use an MDX comment immediately above the fence:

```
{/* pmd-metadata: fixture:my_var fixture:other_var */}
```

### Available annotations

- `fixture:<name>` — inject a pytest fixture as a global variable. Multiple allowed.
- `notest` — skip this fence entirely.
- `continuation` — inherit scope from the previous fence.
- `runner:<RunnerClass>` — use a custom runner instead of the default.
- `retry:<N>` — retry up to N times on failure.

Top-level `await` is supported. Bare `await`, `async for`, and `async with` execute without needing an `async def` wrapper.

## Fixture Patterns for conftest.py

Place the conftest at `docs/conftest.py`, co-located with the docs it serves.

### Naming convention

Fixture names MUST match the variable names used in snippets. If a snippet uses `store`, the fixture is `store`, not `mock_store`.

### Three tiers of fixtures

**Data fixtures** provide named objects that snippets reference directly. No underscore prefix:

```python
@pytest.fixture
def document() -> Document:
    return Document(content="Test content.", filename="doc.txt")
```

**Atomic patch fixtures** each mock ONE external dependency. Underscore-prefixed since snippets never reference them by name:

```python
@pytest.fixture
def _patch_api_client():
    with patch("mylib.clients.APIClient", return_value=MagicMock()):
        yield
```

**Page fixtures** compose atomics for a specific doc page via pytest dependency injection:

```python
@pytest.fixture
def _patch_quickstart(_patch_api_client, _patch_embedder, _patch_storage):
    mock_pipeline = AsyncMock(spec=Pipeline)
    mock_pipeline.run.return_value = 1
    with patch("mylib.pipelines.Pipeline", return_value=mock_pipeline):
        yield
```

### Enforce interfaces with `spec=`

Always use `spec=` on mocks. Without it, `AsyncMock()` silently accepts any attribute or method call. A snippet calling `store.serch()` (typo) or `store.nonexistent_method()` would pass, giving a false sense of correctness. With `spec=`, the mock only exposes methods that exist on the real class, so typos and stale API calls raise `AttributeError`:

```python
@pytest.fixture
def store() -> AsyncMock:
    mock = AsyncMock(spec=VectorStoreClient)
    mock.search.return_value = []
    return mock
```

### When to use fixture injection vs. fixing the snippet

- Snippet references a runtime object (`file`, `store`, `client`) that readers wouldn't construct themselves: **fixture injection**
- Snippet is missing a Python import (`from mylib import Pipeline`): **fix the snippet**

Guide pages that split one script across multiple blocks: add imports to each block so it's self-contained. Readers expect each block to show its imports.

## Custom Runners

Subclass `_Runner` and register via `@register_runner()` in conftest.py for snippets that need a modified execution environment.

**The `__name__` problem:** when pytest-markdown-docs executes a snippet, it runs `exec(compiled, mod.__dict__)` where `mod = types.ModuleType("fence")`. So `__name__` is `"fence"` inside the snippet, not `"__main__"`. Any snippet with an `if __name__ == "__main__":` guard defines `main()` but never calls it. The test passes vacuously, only imports are exercised.

Fix with a custom runner that sets `__name__ = "__main__"` before execution:

```python
from pytest_markdown_docs._runners import DefaultRunner, _Runner, register_runner

@register_runner()
class AsMainRunner(_Runner):
    def runtest(self, test, args):
        args["__name__"] = "__main__"
        DefaultRunner().runtest(test, args)

    def repr_failure(self, test, excinfo, style=None):
        return DefaultRunner().repr_failure(test, excinfo, style)
```

Annotate the fence:

```
{/* pmd-metadata: runner:AsMainRunner fixture:_patch_quickstart */}
```

## Common Failures

**`NameError: name 'X' is not defined`** — snippet uses a variable not in scope. Add a data fixture providing that variable and annotate the fence with `fixture:X`.

**`fixture 'X' not found`** — fixture missing from `docs/conftest.py` or misspelled. Name must match exactly.

**`ModuleNotFoundError` at collection** — optional dependency not installed. Install all extras before running doc tests.

**`ImportError` inside snippet** — the snippet itself is missing an import. Fix it in the doc file.
