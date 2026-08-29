from keel.cli import main as cli_main


def test_dunder_main_exports_cli() -> None:
    import keel.__main__ as package_main

    assert package_main.main is cli_main
