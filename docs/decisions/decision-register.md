# RamoVerde — decision register

Decisions taken by the Product Owner during delivery that the repository depends on. Company facts stay governed by Confluence `WRM-CLIENT-SOT`; this page records technical/legal choices and **open values that are deliberately left empty**, with the exact place to fill them in.

| ID | Decision | Value | Status | Date | Where it is used |
| --- | --- | --- | --- | --- | --- |
| RV-T01 | Copyright holder of the RamoVerde code | *(empty)* | DA DEFINIRE | 2026-10-03 | `LICENSE`, token `{{RAMOVERDE_COPYRIGHT_HOLDER}}` |
| RV-T02 | Mobile bundle identifier (iOS `bundleIdentifier`, Android `package`) | `com.ramoverde.staff` | CONFERMATO | 2026-10-03 | `apps/mobile/app.json` |
| RV-T03 | `main` protected by GitHub ruleset "Main Protection" (PR required, no force push/deletion, required status checks) | required checks: `backend`, `clients`, `contract`, `smoke`, `docker` | CONFERMATO (check list to be filled in the ruleset) | 2026-10-03 | GitHub repository settings |

## Filling an open value

RV-T01 — when the PO names the holder:

1. Replace the token in `LICENSE` (the only occurrence): `grep -rn "{{RAMOVERDE_COPYRIGHT_HOLDER}}" .` must return nothing afterwards.
2. Update the RV-T01 row (value, status `CONFERMATO`, date, source of the decision).
3. Keep the template line: the MIT license of `pianic2/template-fullstack` requires retaining its copyright notice.

Never guess an open value; leave the token in place until the decision is recorded here.
