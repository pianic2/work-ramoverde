---
name: testing
description: Select focused tests and repository quality gates for behavior changes.
---

# Testing

- **Trigger:** A behavior changes, regression is investigated, or a release gate is requested.
- **Inputs:** Changed paths, user-visible behavior, CI commands.
- **Steps:** Run the narrowest meaningful test first; then the required package and cross-workspace gates; preserve failure output and separate environment blockers from code failures.
- **Validation:** Backend PostgreSQL tests, Vitest, mobile render tests and Metro export, type checks, API drift as affected.
- **Expected output:** Exact commands and pass/fail/not-run status with reason.
