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


MODEL_FIELDS = {"ForeignKey", "OneToOneField", "ManyToManyField"}


def _module_of(dotted: str) -> str | None:
    parts = dotted.split(".")
    return parts[1] if len(parts) >= 2 and parts[0] == "apps" else None


def _string_arg(node: ast.Call, position: int, keyword: str) -> str | None:
    if len(node.args) > position and isinstance(node.args[position], ast.Constant):
        value = node.args[position].value
    else:
        value = next(
            (
                k.value.value
                for k in node.keywords
                if k.arg == keyword and isinstance(k.value, ast.Constant)
            ),
            None,
        )
    return value if isinstance(value, str) else None


def _call_name(node: ast.Call) -> str:
    func = node.func
    return func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")


def imported_modules(path: Path, apps_dir: Path = APPS_DIR) -> set[str]:
    """Modules referenced by imports, dynamic imports and "<app_label>.<Model>" strings."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    package = ["apps", *path.parent.relative_to(apps_dir).parts]
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(m for a in node.names if (m := _module_of(a.name)))
        elif isinstance(node, ast.ImportFrom):
            base = package[: len(package) - node.level + 1] if node.level else []
            absolute = ".".join([*base, *([node.module] if node.module else [])])
            if absolute == "apps":  # from apps import cms
                found.update(alias.name for alias in node.names)
            elif module := _module_of(absolute):
                found.add(module)
        elif isinstance(node, ast.Call):
            name = _call_name(node)
            if name == "import_module" and (target := _string_arg(node, 0, "name")):
                found.update(m for m in [_module_of(target)] if m)
            elif name in MODEL_FIELDS and (target := _string_arg(node, 0, "to")):
                if "." in target:  # "app_label.Model"; bare names are same-module
                    found.add(target.split(".")[0])
            elif name == "get_model" and (target := _string_arg(node, 0, "app_label")):
                found.add(target.split(".")[0])
    # String references to Django/third-party labels (auth.Group, contenttypes...) are not ours.
    return {module for module in found if module in ALLOWED_DEPENDENCIES}


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


@pytest.mark.parametrize(
    "source",
    [
        "from apps.cms.models import Page\n",
        "import apps.cms.services\n",
        "from apps import cms\n",
        "from ..cms.models import Page\n",
        "from ..cms import models\n",
        "import importlib\nimportlib.import_module('apps.cms.models')\n",
        "from django.db import models\nx = models.ForeignKey('cms.Page', on_delete=None)\n",
        "from django.db import models\nx = models.ManyToManyField(to='cms.Page')\n",
        "from django.apps import apps as registry\nregistry.get_model('cms', 'Page')\n",
        "from django.apps import apps as registry\nregistry.get_model('cms.Page')\n",
    ],
)
def test_detects_forbidden_dependency_forms(tmp_path: Path, source: str):
    package = tmp_path / "apps" / "media"
    package.mkdir(parents=True)
    sample = package / "views.py"
    sample.write_text(source)
    assert "cms" in imported_modules(sample, apps_dir=tmp_path / "apps")


def test_ignores_same_module_and_user_model_references(tmp_path: Path):
    package = tmp_path / "apps" / "media"
    package.mkdir(parents=True)
    sample = package / "models.py"
    sample.write_text(
        "from django.conf import settings\nfrom django.db import models\n"
        "from .storage import backend\n"
        "a = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)\n"
        "b = models.ForeignKey('self', on_delete=models.CASCADE)\n"
        "c = models.ForeignKey('MediaAsset', on_delete=models.CASCADE)\n"
    )
    assert imported_modules(sample, apps_dir=tmp_path / "apps") == {"media"}
