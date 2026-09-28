import importlib


def test_package_init_imports_without_orchestrator_dependency() -> None:
    module = importlib.import_module("aegis_os")

    assert module.__version__ == "0.1.0"
    assert module.__author__ == "AegisOS Engineering"
    assert set(module.__all__) == {"__version__", "__author__"}
