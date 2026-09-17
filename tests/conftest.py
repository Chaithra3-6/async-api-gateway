import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: needs Redis and MongoDB running (provided by docker-compose or CI).",
    )
