from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


@pytest.fixture()
def support_dir():
    return Path(__file__).parent / "support"
