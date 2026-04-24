from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_script_module(
    script_path: Path,
    module_name: str,
    *,
    register_in_sys_modules: bool = False,
):
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load script module: {script_path}")
    module = importlib.util.module_from_spec(spec)
    if register_in_sys_modules:
        sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_repo_script(
    relative_script_path: str,
    module_name: str,
    *,
    register_in_sys_modules: bool = False,
):
    from apps.platform_runtime.tests.support.paths import repo_root

    return load_script_module(
        repo_root() / relative_script_path,
        module_name,
        register_in_sys_modules=register_in_sys_modules,
    )
