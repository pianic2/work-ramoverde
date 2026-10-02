---
name: repo-docs
description: Use when auditing, reorganizing or standardizing a repository's Markdown documentation and docs/ information architecture while preserving its content and evidence.
---

# Repository Documentation

Analyze and normalize repository documentation into a coherent, navigable structure. Preserve accurate content, decisions and attribution. This skill governs documentation under `docs/`; it does not redesign the root README landing page.

## Core workflow

Use this sequence:

```text
discover → classify → deduplicate → reorganize → cross-link → validate
```

Do not create every possible file or directory. First inventory and read the existing documents. Create or move only material that has a clear documentation responsibility.

## Discover before editing

Inspect the full documentation tree, root Markdown files, `.github/` guidance, generated documentation markers, links and referenced assets. Read all source documents completely before moving, merging, summarizing or deleting them. Record their unique facts, examples, commands, history, decisions and attribution.

Do not force project-specific material into a generic category when it has a real distinct purpose. Do not edit generated documentation when its source of truth is available; find the generator, source and build command, then document or link the generated output.

## Canonical taxonomy

Use this as a semantic guide, not a required file list:

```text
docs/
├── README.md
├── getting-started/
├── architecture/
├── development/
├── operations/
└── reference/
```

Create only directories and documents that contain useful information. Prefer a few documents with clear responsibilities over many nearly empty files.

| Category | Put here |
| --- | --- |
| `getting-started/` | Prerequisites, installation, local setup, configuration, environment variables and first run |
| `architecture/` | System design, components, boundaries, data models, diagrams and technical decisions / ADRs |
| `development/` | Developer workflow, local tooling, testing, linting, formatting, quality gates and release development procedure |
| `operations/` | Deployment, runtime operations, production procedures, runbooks, monitoring, recovery and troubleshooting |
| `reference/` | API, CLI, protocols, schemas, configuration reference and integration contracts |

Keep real specialty areas such as `security/`, `hardware/`, `protocols/`, `research/` or `product/` when their content does not naturally fit the standard categories.

## Documentation index

When `docs/` contains significant documentation, create or update `docs/README.md` as a short navigation index. Group links by the categories that actually exist. Do not duplicate document content or list empty categories. Link to canonical pages and preserve useful project-specific groupings.

For example, include only applicable groups:

```md
# Documentation

## Getting Started
- [Setup](getting-started/setup.md)

## Development
- [Testing](development/testing.md)

## Reference
- [API](reference/api.md)
```

## Preserve and reorganize

Before merging or moving files:

1. Identify each source's unique information and its canonical destination.
2. Preserve technical detail, examples, history-sensitive notes, decisions and attribution; do not turn facts into vague summaries.
3. Merge only when responsibilities overlap. Keep one complete canonical version and replace true duplicates with links.
4. Update every reference affected by moves or merges.
5. Use `git mv` for tracked file moves when appropriate so the change clearly records the reorganization.

Apply progressive disclosure:

```text
root README → docs/README.md → topic guide → detailed reference
```

Keep the root README a landing page. When useful, add a short Documentation link to `docs/README.md` or a directly relevant guide; do not copy detailed documentation into it. The README's presentation remains the responsibility of README-specific guidance.

## Keep standard files in place

Do not automatically move or duplicate root or `.github/` files such as `README.md`, `LICENSE`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md` or `.github/` guidance. Link to them from `docs/README.md` when useful.

## Evidence and naming

Reorganize or clarify supported information; do not invent architectures, operations procedures, commands, APIs, deployments or quality gates. New documentation may be derived only when repository evidence is sufficient. Verify commands against scripts/configuration and claims against source or authoritative project docs.

Use lowercase kebab-case for new ordinary Markdown filenames (for example `setup.md`, `architecture-overview.md` and `troubleshooting.md`). Preserve standard exceptions such as `README.md`, `ADR-0001-title.md` and names required by project conventions or external standards.

## Links and assets

After every move or rename, update Markdown links in the root README and all affected documents. Check relative links, referenced assets and local anchors where possible. Preserve asset locations unless moving them is necessary; if moved, update every reference. Do not leave broken relative paths.

## Validation

Before finishing:

1. Show the final `docs/` tree.
2. Confirm each document has a clear responsibility and no obvious duplicate remains.
3. Confirm important source content, decisions and attribution were preserved.
4. Check relative links, anchors and referenced assets.
5. Run repository-provided documentation lint when present; do not invent validation commands.
6. Review all moves, deletions and merged-content diffs.
7. Run `git diff --check`.
