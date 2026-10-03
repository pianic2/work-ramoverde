---
name: repo-readme
description: Use when creating, rewriting or improving a GitHub repository README that should be a concise visual-first landing page grounded in repository evidence.
---

# Repository README

Create or improve only the target repository's root `README.md` as a concise GitHub landing page. Inspect the repository first and derive every technical claim, project name, stack choice and visual color from evidence.

## Evidence first

Inspect the current README, manifests and lockfiles, source tree, scripts, CI workflows, deployment configuration, API specifications, docs, assets, license and relevant Git metadata. Preserve useful content unless evidence shows it is obsolete or incorrect.

Never invent features, project names, versions, commands, integrations, CI or release status, deployments, coverage, architecture, URLs, colors or support claims. Verify commands against project configuration, status badges against authoritative sources, and every referenced path against the repository. Do not imply tests pass or a service is deployed without current evidence.

## Generate the titled stack background

Use the bundled script for the opening visual. The agent researches; the script draws:

```text
AGENT → identify project title, primary stack and any real palette
SCRIPT → embed Simple Icons and generate the titled SVG background
```

Do not manually draw, edit after generation or replace the generated SVG with an equivalent visual. Adjust title, colors, pattern density, angle, spacing or size by rerunning the script.

### Identify title, stack and palette

- **Title:** Prefer the documented product name, then project/package metadata, then the repository name. Never invent a commercial name.
- **Stack:** Select about 3–8 primary technologies from manifests, lockfiles, framework configuration, source, infrastructure and authoritative docs. Exclude transitive dependencies and minor utilities. Use aliases supported by `scripts/generate_readme_background.py`.
- **Palette:** Inspect CSS variables, design tokens, framework/theme configuration, component libraries, brand assets, an existing authoritative logo and design-system docs. Pass only verified `--background`, `--foreground`, `--accent` and `--accent-2` values. Do not guess missing colors; omitted options use the script's deterministic fallback values. Choose a verified foreground with strong contrast against the background.
- **Subtitle:** Pass `--subtitle` only for a short, useful description supported by the repository; keep it to one line.

### Run the generator

Run the standard-library script from the target repository root. Its default output is `docs/assets/readme-background.svg`:

```bash
python3 /path/to/repo-readme/scripts/generate_readme_background.py \
  --title "Project Name" \
  --subtitle "Short verified description" \
  --stack python,django,postgresql,docker \
  --output docs/assets/readme-background.svg
```

Omit `--subtitle` when no useful verified line exists. The script downloads Simple Icons SVGs, embeds their paths, and produces a self-contained pattern of repeated, staggered diagonal rows. Its restrained opacity, central scrim and high-contrast title keep the project name dominant without an opaque title box. The title uses a system-safe SVG font stack; no remote fonts are loaded.

If one alias or icon is unavailable, the script warns and continues with available icons. Use `--strict` to fail on any missing alias or icon. If none can be loaded, it fails without writing an empty background. Never leave external icon URLs in the result. The SVG contains no labels or architecture; do not add boxes, arrows, pipelines, terminals, database cylinders, robots or generic AI motifs.

Do not automatically create a logo. Reuse an existing authoritative logo when useful. Create a new logo only when the user explicitly requests one.

## Header and badge row

The README begins with the generated visual, followed immediately by one centered badge/button row, then the one-line description, optional preview and Quick Start. Do not repeat the project title as another large visible heading.

Use the image as the semantic page heading so the project remains accessible without duplicating it visually:

```html
<h1 align="center">
  <img
    src="docs/assets/readme-background.svg"
    alt="Project Name — Short verified description"
    width="100%"
  />
</h1>
```

The `alt` text names the project and may include the subtitle. Keep the SVG's own accessible title aligned with those values.

Directly below it, include **3–5** badges or useful link buttons, targeting **4** when repository evidence supports them. Use one consistent style, preferably `for-the-badge`; do not mix styles.

1. **Stack:** Always include one concise badge for the primary stack, such as `Django + PostgreSQL`. Do not list every dependency.
2. **License:** Include a license badge linked to the actual license file or authoritative source when a license exists. Otherwise use another verified project status or useful link.
3. **Quality / CI:** When workflows or quality checks exist, use a dynamic badge tied to the real workflow or provider. Never use a static “passing” claim without current authoritative evidence.
4. **Useful link:** Link to the most relevant existing Docs, API/OpenAPI, MCP, Demo, Package, Deployment, Release or Website. If none exists, use a useful in-page destination such as Quick Start or Project Structure.
5. **Optional fifth:** Add another verified status or useful destination only when it adds distinct value.

Use concise, factual labels and real targets. Do not invent a license, status, package, deployment or destination to reach the count. When status badges are sparse, fill the row with useful buttons to sections that exist, such as Quick Start, API or Project Structure. These are navigation links, not status claims. Use three to five real items whenever available destinations permit; if fewer than three useful items exist, do not fabricate one.

After the row, add one evidence-based sentence describing the project. An available representative screenshot or output may follow; omit decorative or fabricated previews. Quick Start comes immediately after the optional preview.

## README structure

Follow this order, omitting sections without evidence or value:

1. Generated background with semantic project title
2. Badge / useful-link row
3. One-line description
4. Optional visual preview
5. Quick Start
6. Architecture
7. Development
8. Testing
9. API / Interfaces
10. Deployment
11. Project Structure
12. Contributing
13. License

Keep Quick Start near the top and use the repository's actual commands. Prefer concise command blocks, tables, images, Mermaid diagrams and links over long prose. Keep architecture out of the background. Include only verified components and relationships; omit low-value or unsupported sections. Link to deeper docs rather than repeating them. Do not add an Overview or empty sections.

Add a table of contents only when a long README needs it for navigation. Remove marketing filler, repeated explanations, giant tables and decorative markup.

## Final review

Before finishing, verify the project title, stack, colors, commands, badges, diagrams and links against evidence; ensure the generated background is self-contained and referenced at its real repository path; confirm the title is legible, the badge row is consistent and useful, Quick Start is easy to reach, and no unsupported or repetitive content remains.
