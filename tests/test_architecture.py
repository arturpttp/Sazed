"""Dependency direction and core purity, checked by parsing the source."""

import ast
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "sazed"

ALLOWED: dict[str, set[str]] = {
    "core": {"sazed.core"},
    "nlu": {"sazed.core", "sazed.nlu"},
    "skills": {"sazed.core", "sazed.skills"},
    "adapters": {"sazed.core", "sazed.nlu", "sazed.skills", "sazed.adapters"},
    "runtime": {"sazed.core", "sazed.nlu", "sazed.skills", "sazed.adapters", "sazed.runtime"},
    "interfaces": {"sazed.runtime", "sazed.interfaces"},
}
STDLIB_ONLY = {"core"}
PURE = {"core", "nlu"}
IMPURE_ATTRIBUTES = {"now", "today", "utcnow", "getenv", "environ"}
IMPURE_NAMES = {"open", "input", "print"}


def _imports(tree: ast.AST) -> list[str]:
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.append("." * node.level + (node.module or ""))
    return found


def _is_allowed(module: str, allowed: set[str]) -> bool:
    return any(module == a or module.startswith(a + ".") for a in allowed)


@pytest.mark.parametrize("package", sorted(ALLOWED))
def test_package_imports_only_what_it_may(package: str) -> None:
    violations: list[str] = []
    for file in sorted((SRC / package).rglob("*.py")):
        for module in _imports(ast.parse(file.read_text(encoding="utf-8"))):
            top = module.split(".")[0]
            if module.startswith("."):
                violations.append(f"{file.name}: relative import {module}")
            elif top == "sazed":
                if not _is_allowed(module, ALLOWED[package]):
                    violations.append(f"{file.name}: {module}")
            elif package in STDLIB_ONLY and top not in sys.stdlib_module_names:
                violations.append(f"{file.name}: third-party {module}")
    assert violations == []


@pytest.mark.parametrize("package", sorted(PURE))
def test_pure_packages_do_not_touch_clock_env_or_io(package: str) -> None:
    violations: list[str] = []
    for file in sorted((SRC / package).rglob("*.py")):
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Attribute) and node.attr in IMPURE_ATTRIBUTES:
                violations.append(f"{file.name}:{node.lineno} .{node.attr}")
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in IMPURE_NAMES
            ):
                violations.append(f"{file.name}:{node.lineno} {node.func.id}()")
    assert violations == []


def test_every_package_has_a_rule() -> None:
    packages = {p.name for p in SRC.iterdir() if (p / "__init__.py").exists()}
    assert packages == set(ALLOWED)
