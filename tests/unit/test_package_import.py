import importlib


def test_package_top_level_import_does_not_require_removed_modules() -> None:
    package = importlib.import_module("aegis_os")

    assert package.__version__ == "0.1.0"
    assert package.__author__ == "AegisOS Engineering"
