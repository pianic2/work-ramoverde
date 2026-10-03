#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "apps/mobile/package.json").read_text())
expected = "0.1.0-rc.2"
actual = manifest["dependencies"].get("@personal-library/react-native-components")
if actual != expected:
    raise SystemExit(f"Expected the reviewed library release {expected}, got {actual!r}")

mobile_sources = root / "apps/mobile"
sources = "\n".join(
    path.read_text()
    for folder in (mobile_sources / "app", mobile_sources / "src", mobile_sources / "tests")
    for path in folder.rglob("*.tsx")
)
if "@personal-library/react-native-components" not in sources:
    raise SystemExit("Mobile routes must import the canonical library")
if not all(symbol in sources for symbol in ("ThemeProvider", "Column", "Text", "Button")):
    raise SystemExit(
        "Mobile app and render test must use the library provider and representative primitives"
    )
if re.search(r"@personal-library/react-native-components/(?!package\.json)[^'\"]+", sources):
    raise SystemExit("Only documented root exports may be imported")
print("Canonical mobile UI dependency and root-export usage verified.")
