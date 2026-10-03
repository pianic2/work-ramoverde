---
name: expo-mobile
description: Implement Expo Router application behavior and validate package resolution, native storage, and Metro export.
---

# Expo mobile

- **Trigger:** A task changes `apps/mobile` or Expo dependencies.
- **Inputs:** Platform behavior, app instructions, Expo SDK compatibility metadata.
- **Steps:** Follow Expo monorepo conventions; import shared API types/client; keep secrets in SecureStore; inspect the personal component library before UI work; avoid simulator requirements in generic CI.
- **Validation:** `expo-doctor`, strict TypeScript, render tests, `expo export --platform web`, and peer graph check.
- **Expected output:** Platform-scoped change with compatibility evidence and documented environment limitations.
