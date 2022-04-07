from setuptools import setup

setup(
    name="pytest_markdown",
    version="0.0.1",
    author="Modal Labs",
    packages=["pytest_markdown"],
    # the following makes a plugin available to pytest
    entry_points={"pytest11": ["pytest_markdown = pytest_markdown.plugin"]},
    # custom PyPI classifier for pytest plugins
    classifiers=["Framework :: Pytest"],
    python_requires=">=3.6",
    install_requires=["markdown-it-py~=1.1.0"],
)
