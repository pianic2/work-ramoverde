#!/usr/bin/env python3
"""Generate a deterministic, self-contained SVG stack background for a README."""

from __future__ import annotations

import argparse
import math
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


DEFAULT_OUTPUT = Path("docs/assets/readme-background.svg")
SIMPLE_ICONS_URL = "https://cdn.simpleicons.org/{slug}"
SVG_NS = "http://www.w3.org/2000/svg"
ALIASES = {
    "python": "python",
    "django": "django",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "java": "openjdk",
    "spring": "spring",
    "springboot": "springboot",
    "spring-boot": "springboot",
    "react": "react",
    "react-native": "react",
    "expo": "expo",
    "typescript": "typescript",
    "javascript": "javascript",
    "node": "nodedotjs",
    "nodejs": "nodedotjs",
    "docker": "docker",
    "php": "php",
    "laravel": "laravel",
    "mysql": "mysql",
    "redis": "redis",
    "vite": "vite",
    "wagtail": "wagtail",
    "github-actions": "githubactions",
}


@dataclass(frozen=True)
class Icon:
    slug: str
    view_box: tuple[float, float, float, float]
    paths: tuple[tuple[str, str, str], ...]


def parse_color(value: str) -> str:
    """Accept simple CSS color literals while rejecting markup or URL injection."""
    color = value.strip()
    if re.fullmatch(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", color):
        return color
    if re.fullmatch(r"[a-zA-Z]{1,24}", color):
        return color
    if re.fullmatch(r"(?:rgb|rgba|hsl|hsla)\([0-9.% ,/+\-]+\)", color):
        return color
    raise argparse.ArgumentTypeError(f"invalid CSS color literal: {value!r}")


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def nonnegative_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def bounded_float(low: float, high: float):
    def parse(value: str) -> float:
        try:
            parsed = float(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"must be a number from {low} to {high}") from exc
        if not low <= parsed <= high:
            raise argparse.ArgumentTypeError(f"must be a number from {low} to {high}")
        return parsed

    return parse


def finite_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a finite number") from exc
    if not math.isfinite(parsed):
        raise argparse.ArgumentTypeError("must be a finite number")
    return parsed


def one_line_text(value: str) -> str:
    text = value.strip()
    if not text:
        raise argparse.ArgumentTypeError("must not be empty")
    if "\n" in text or "\r" in text:
        raise argparse.ArgumentTypeError("must be a single line")
    return text


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def download_icon(slug: str, timeout: float = 15.0) -> Icon:
    request = urllib.request.Request(
        SIMPLE_ICONS_URL.format(slug=slug),
        headers={"User-Agent": "repo-readme-background-generator/1.0"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        source = response.read()

    root = ET.fromstring(source)
    view_box_value = root.attrib.get("viewBox")
    if not view_box_value:
        raise ValueError("SVG has no viewBox")
    view_box_parts = [float(part) for part in re.split(r"[ ,]+", view_box_value.strip())]
    if len(view_box_parts) != 4 or view_box_parts[2] <= 0 or view_box_parts[3] <= 0:
        raise ValueError("SVG has an invalid viewBox")

    paths = []
    for element in root.iter():
        if local_name(element.tag) != "path" or not element.attrib.get("d"):
            continue
        paths.append(
            (
                element.attrib["d"],
                element.attrib.get("fill-rule", "nonzero"),
                element.attrib.get("clip-rule", "nonzero"),
            )
        )
    if not paths:
        raise ValueError("SVG contains no path data")

    return Icon(slug, tuple(view_box_parts), tuple(paths))


def resolve_icons(stack: str, strict: bool) -> list[Icon]:
    names = [item.strip().lower() for item in stack.split(",") if item.strip()]
    if not names:
        raise ValueError("--stack must list at least one technology")

    slugs = []
    for name in names:
        slug = ALIASES.get(name)
        if slug is None:
            print(f"warning: no Simple Icons alias for {name!r}; skipping", file=sys.stderr)
            if strict:
                raise ValueError(f"unsupported technology alias: {name}")
            continue
        if slug not in slugs:
            slugs.append(slug)

    icons = []
    for slug in slugs:
        try:
            icons.append(download_icon(slug))
        except (urllib.error.URLError, TimeoutError, ET.ParseError, ValueError, OSError) as exc:
            print(f"warning: could not load Simple Icon {slug!r}: {exc}", file=sys.stderr)
            if strict:
                raise ValueError(f"missing or invalid Simple Icon: {slug}") from exc

    if not icons:
        raise ValueError("no stack icons could be loaded; no background was written")
    return icons


def svg_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def build_svg(
    icons: list[Icon],
    *,
    title: str,
    subtitle: str | None,
    width: int,
    height: int,
    angle: float,
    rows: int,
    icon_size: int,
    gap: int,
    opacity: float,
    background: str,
    foreground: str,
    accent: str,
    accent_2: str,
) -> str:
    colors = [foreground, accent, accent_2]
    radians = math.radians(angle)
    rotated_width = abs(math.cos(radians)) * width + abs(math.sin(radians)) * height
    tile = icon_size + gap
    count = max(1, math.ceil(rotated_width / tile) + 2)
    row_offset = tile / 2
    pattern_height = (rows - 1) * tile + icon_size
    row_top = (height - pattern_height) / 2
    rotate = f"rotate({angle:g} {width / 2:g} {height / 2:g})"
    title_size = min(76, height * 0.28, width / max(6, len(title) * 0.62))
    title_size = max(16, title_size)
    subtitle_size = min(22, height * 0.08, width / max(8, len(subtitle or "") * 0.58))
    subtitle_size = max(13, subtitle_size)
    title_y = height / 2 - (subtitle_size * 0.48 if subtitle else 0)
    subtitle_y = height / 2 + title_size * 0.62

    definitions = []
    for index, icon in enumerate(icons):
        x, y, view_width, view_height = icon.view_box
        scale = icon_size / max(view_width, view_height)
        scaled_width = view_width * scale
        scaled_height = view_height * scale
        inner_x = (icon_size - scaled_width) / 2 - x * scale
        inner_y = (icon_size - scaled_height) / 2 - y * scale
        paths = "".join(
            f'<path d="{svg_escape(path)}" fill-rule="{svg_escape(fill_rule)}" '
            f'clip-rule="{svg_escape(clip_rule)}"/>'
            for path, fill_rule, clip_rule in icon.paths
        )
        definitions.append(
            f'<g id="stack-icon-{index}" transform="translate({inner_x:g} {inner_y:g}) '
            f'scale({scale:g})">{paths}</g>'
        )

    symbols = []
    for row in range(rows):
        y = row_top + row * tile
        stagger = row * row_offset
        for column in range(count):
            x = (width - count * tile) / 2 + column * tile + stagger
            icon_index = (column + row) % len(icons)
            color = colors[(row + column) % len(colors)]
            symbols.append(
                f'<use href="#stack-icon-{icon_index}" x="{x:g}" y="{y:g}" '
                f'width="{icon_size}" height="{icon_size}" fill="{svg_escape(color)}"/>'
            )

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="{SVG_NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{svg_escape(title + (': ' + subtitle if subtitle else ''))}">
  <title>{svg_escape(title + (': ' + subtitle if subtitle else ''))}</title>
  <defs>
    <linearGradient id="background-wash" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{svg_escape(accent_2)}" stop-opacity="0"/>
      <stop offset="100%" stop-color="{svg_escape(accent_2)}" stop-opacity="0.12"/>
    </linearGradient>
    <radialGradient id="subtle-glow">
      <stop offset="0%" stop-color="{svg_escape(accent)}" stop-opacity="0.16"/>
      <stop offset="100%" stop-color="{svg_escape(accent)}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="title-scrim" cx="50%" cy="50%" r="66%">
      <stop offset="0%" stop-color="{svg_escape(background)}" stop-opacity="0.62"/>
      <stop offset="58%" stop-color="{svg_escape(background)}" stop-opacity="0.32"/>
      <stop offset="100%" stop-color="{svg_escape(background)}" stop-opacity="0"/>
    </radialGradient>
    {''.join(definitions)}
  </defs>
  <rect width="100%" height="100%" fill="{svg_escape(background)}"/>
  <rect width="100%" height="100%" fill="url(#background-wash)"/>
  <ellipse cx="{width * 0.72:g}" cy="{height * 0.2:g}" rx="{width * 0.34:g}" ry="{height * 0.85:g}" fill="url(#subtle-glow)"/>
  <g transform="{rotate}" opacity="{opacity:g}">
    {''.join(symbols)}
  </g>
  <rect width="100%" height="100%" fill="url(#title-scrim)"/>
  <text x="{width / 2:g}" y="{title_y:g}" text-anchor="middle" dominant-baseline="middle"
        font-family="Arial, Helvetica, sans-serif" font-size="{title_size:g}" font-weight="700"
        letter-spacing="1.2" fill="{svg_escape(foreground)}" stroke="{svg_escape(background)}"
        stroke-width="1.5" paint-order="stroke">{svg_escape(title)}</text>
  {f'<text x="{width / 2:g}" y="{subtitle_y:g}" text-anchor="middle" dominant-baseline="middle" font-family="Arial, Helvetica, sans-serif" font-size="{subtitle_size:g}" font-weight="400" letter-spacing="0.25" fill="{svg_escape(foreground)}" stroke="{svg_escape(background)}" stroke-width="0.8" paint-order="stroke">{svg_escape(subtitle)}</text>' if subtitle else ''}
</svg>
'''


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Download Simple Icons and generate a self-contained titled README background SVG."
    )
    parser.add_argument("--title", required=True, type=one_line_text, help="Evidence-based project name shown over the stack pattern")
    parser.add_argument("--subtitle", type=one_line_text, help="Optional short, evidence-based one-line description")
    parser.add_argument("--stack", required=True, help="Comma-separated primary technology names")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help=f"SVG output path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--background", type=parse_color, default="#17202b", help="Background color")
    parser.add_argument("--foreground", type=parse_color, default="#f4f1e8", help="Primary icon color")
    parser.add_argument("--accent", type=parse_color, default="#78b6a5", help="Accent color")
    parser.add_argument("--accent-2", type=parse_color, default="#d9a86c", help="Secondary accent color")
    parser.add_argument("--width", type=positive_int, default=1200, help="SVG width (default: 1200)")
    parser.add_argument("--height", type=positive_int, default=360, help="SVG height (default: 360)")
    parser.add_argument("--angle", type=finite_float, default=-12, help="Pattern rotation angle in degrees (default: -12)")
    parser.add_argument("--rows", type=positive_int, default=4, help="Number of icon rows (default: 4)")
    parser.add_argument("--icon-size", type=positive_int, default=58, help="Icon tile size (default: 58)")
    parser.add_argument("--gap", type=nonnegative_int, default=38, help="Gap between icon tiles (default: 38)")
    parser.add_argument("--opacity", type=bounded_float(0, 1), default=0.16, help="Icon opacity from 0 to 1 (default: 0.16)")
    parser.add_argument("--strict", action="store_true", help="Fail if any technology alias or icon is unavailable")
    return parser


def main() -> int:
    parser = make_parser()
    args = parser.parse_args()
    try:
        icons = resolve_icons(args.stack, args.strict)
        output = build_svg(
            icons,
            title=args.title,
            subtitle=args.subtitle,
            width=args.width,
            height=args.height,
            angle=args.angle,
            rows=args.rows,
            icon_size=args.icon_size,
            gap=args.gap,
            opacity=args.opacity,
            background=args.background,
            foreground=args.foreground,
            accent=args.accent,
            accent_2=args.accent_2,
        )
        ET.fromstring(output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    except (OSError, ValueError, ET.ParseError, urllib.error.URLError) as exc:
        parser.error(str(exc))

    print(f"Generated {args.output} with {len(icons)} embedded stack icons")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
