#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def version(command: list[str]) -> str:
    try:
        return (
            subprocess.check_output(command, text=True, stderr=subprocess.STDOUT)
            .strip()
            .splitlines()[0]
        )
    except (OSError, subprocess.CalledProcessError):
        return "not installed"


def main() -> int:
    checks = {
        "git": version(["git", "--version"]),
        "Docker Compose": version(["docker", "compose", "version", "--short"]),
        "Node": version(["node", "--version"]),
        "pnpm": version(["corepack", "pnpm", "--version"]),
        "Python 3.13": (
            f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        ),
        "uv": version(["uv", "--version"]),
    }
    for tool, value in checks.items():
        print(f"{tool:16} {value}")
    missing = [tool for tool, value in checks.items() if value == "not installed"]
    if sys.version_info[:2] != (3, 13):
        missing.append("Python 3.13")
    if not shutil.which("docker"):
        print("Docker is required for local PostgreSQL, Compose and production-image checks.")

    package_file = (
        ROOT / "apps/mobile/node_modules/@personal-library/react-native-components/package.json"
    )
    if not package_file.exists():
        package_file = ROOT / "node_modules/@personal-library/react-native-components/package.json"
    if package_file.exists():
        package = json.loads(package_file.read_text())
        peers = package.get("peerDependencies", {})
        react_peer = peers.get("react")
        react_native_peer = peers.get("react-native")
        print(f"Mobile library   {package['version']} (React {react_peer}, RN {react_native_peer})")
    else:
        print("Mobile library   not installed yet; run make setup")
    if missing:
        print(f"Missing or unsupported prerequisites: {', '.join(missing)}")
    return int(bool(missing))


if __name__ == "__main__":
    raise SystemExit(main())
