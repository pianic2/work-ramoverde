"""Enforce docs/architecture/domain-modules.md: modules import only allowed dependencies."""

import ast
from pathlib import Path

import pytest

APPS_DIR = Path(__file__).resolve().parents[1] / "apps"
KERNEL = {"core", "audit", "accounts", "notifications"}

# importer -> modules it may import (besides itself). Keep in sync with the docs page.
ALLOWED_DEPENDENCIES: dict[str, set[str]] = {
    "core": set(),
    "audit": {"core"},
    "notifications": {"core"},
    "accounts": {"core", "audit", "notifications"},
    "media": KERNEL,
    "services": KERNEL | {"media"},
    "certifications": KERNEL | {"media"},
    "projects": KERNEL | {"services", "media"},
    "customers": KERNEL,
    "conversations": KERNEL | {"customers", "media"},
    "leads": KERNEL | {"conversations", "customers", "services", "media"},
    "inspections": KERNEL | {"leads", "customers", "services", "media"},
    "cms": KERNEL | {"projects", "services", "certifications", "media"},
}


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        for name in names:
            parts = name.split(".")
            if len(parts) >= 2 and parts[0] == "apps":
                found.add(parts[1])
    return found


def module_dirs() -> list[Path]:
    return sorted(p for p in APPS_DIR.iterdir() if (p / "__init__.py").exists())


def test_every_module_is_declared():
    undeclared = {p.name for p in module_dirs()} - ALLOWED_DEPENDENCIES.keys()
    assert not undeclared, f"Declare {undeclared} in docs/architecture/domain-modules.md"


@pytest.mark.parametrize("module_dir", module_dirs(), ids=lambda p: p.name)
def test_module_imports_respect_boundaries(module_dir: Path):
    allowed = ALLOWED_DEPENDENCIES[module_dir.name] | {module_dir.name}
    violations = [
        f"{path.relative_to(APPS_DIR)} imports apps.{target}"
        for path in sorted(module_dir.rglob("*.py"))
        for target in imported_modules(path) - allowed
    ]
    assert not violations, "\n".join(violations)


def test_allowed_graph_is_acyclic():
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(node: str, trail: tuple[str, ...]) -> None:
        if node in done:
            return
        assert node not in visiting, f"cycle: {' -> '.join((*trail, node))}"
        visiting.add(node)
        for dep in ALLOWED_DEPENDENCIES[node] - {node}:
            visit(dep, (*trail, node))
        visiting.discard(node)
        done.add(node)

    for module in ALLOWED_DEPENDENCIES:
        visit(module, ())


def test_detects_forbidden_import(tmp_path: Path):
    sample = tmp_path / "views.py"
    sample.write_text("from apps.cms.models import Page\nimport apps.leads.services\n")
    assert imported_modules(sample) == {"cms", "leads"}
