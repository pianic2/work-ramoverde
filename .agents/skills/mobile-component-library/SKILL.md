---
name: mobile-component-library
description: Choose and validate native UI from the canonical personal React Native component library.
---

# Personal React Native component library

- **Trigger:** Any native screen, component, theme, token, or UI dependency change.
- **Inputs:** UI need, installed package metadata, peer ranges, root exports and consumer documentation.
- **Steps:** Inspect `package.json`, exported types and docs; verify React/RN/Expo peer compatibility; use documented root exports; compose existing components; add a thin app adapter only for domain behavior; if a generic capability is missing, implement the minimum fallback and record a library improvement candidate. Never deep-import, copy, vendor, patch, or duplicate a generic primitive.
- **Validation:** Confirm package resolution and peers; import and render representative components through the root entrypoint; run TypeScript and Expo Metro export.
- **Expected output:** Exact component and provider choices, compatibility evidence, render/bundle results, and any genuinely missing library capability.
