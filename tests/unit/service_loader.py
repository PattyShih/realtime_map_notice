import importlib.util
from pathlib import Path
from types import ModuleType


def load_service_module(service_name: str) -> ModuleType:
    app_path = Path("backend") / service_name / "app" / "main.py"
    module_name = f"tests.loaded_{service_name.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(module_name, app_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load service module: {service_name}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
