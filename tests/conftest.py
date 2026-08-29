import pytest

TEST_LAYERS = ("unit", "integration", "system")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        parts = set(item.path.parts)
        for layer in TEST_LAYERS:
            if layer in parts:
                item.add_marker(getattr(pytest.mark, layer))
                break
