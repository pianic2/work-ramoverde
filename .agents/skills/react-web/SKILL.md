---
name: react-web
description: Build and test accessible React web routes using the generated API client.
---

# React web

- **Trigger:** A task changes the React/Vite application.
- **Inputs:** User flow, `apps/web/AGENTS.md`, API operation in generated client.
- **Steps:** Use semantic DOM, React Router and TanStack Query; use the generated client; keep server state in queries; validate public environment configuration; avoid native dependencies.
- **Validation:** Vitest and Testing Library, strict typecheck, ESLint, production Vite build; Playwright smoke for route-level changes.
- **Expected output:** Accessible UI behavior with tests and exact check results.
