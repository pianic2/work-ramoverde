# RamoVerde — Definition of Ready and Definition of Done

Applies to every Jira issue `WR-*` and every pull request, whether the work is done by a person or an agent. Agents optimise for **value delivered and quality perceived by the stakeholder**, not for the number of tickets closed.

Sources, in order of precedence: Confluence `WRM-CLIENT-SOT` → `UserStory` → `Stack` → Jira issue → repository. If two sources disagree, the higher one wins and the conflict is reported, never silently resolved.

## Definition of Ready (before starting)

An issue is Ready only when every line below is true. If one is missing, the agent asks or records the gap on the issue; it does not start by guessing.

| # | Criterion | What "yes" looks like |
| --- | --- | --- |
| R1 | **Value** | One sentence says who benefits and how (the issue's `VALUE` section). |
| R2 | **Sources of truth** | The relevant SOT/UserStory/Stack sections are linked; Design 09 is linked if the issue changes anything visible. |
| R3 | **Testable acceptance criteria** | Each criterion can be shown passing or failing with a test, a command or a screenshot. |
| R4 | **UX intent** (UI issues) | Who uses the screen, on which device, the primary action, empty/error/loading states, Italian copy source. |
| R5 | **Unknown business data** | Any value marked `DA DEFINIRE` in the SOT is modelled as `null`/`TBD` and shown as such — never invented (email, domain, socials, hours, prices, testimonials, claims…). |
| R6 | **Skill plan** | Skills to load are named (e.g. `superpowers:test-driven-development`, `superpowers:requesting-code-review`; visual work: a design-taste review against Design 09). |
| R7 | **Scope and dependencies** | Out-of-scope is stated; blocking issues are linked; module ownership is clear (`docs/architecture/domain-modules.md`). |
| R8 | **Evidence plan** | The `EVIDENCE REQUIRED` list says which outputs will prove Done. |
| R9 | **Risk class** | Security/auth/data-model/migration work is flagged so it gets a plan and a security review before coding. |

## Definition of Done (before closing)

An issue is Done only when **all** applicable criteria hold. "It compiles" or "tests pass" alone is not Done. Partial acceptance criteria = not Done: keep the issue open or split it explicitly.

| # | Criterion | Check |
| --- | --- | --- |
| D1 | **Correct** | Every acceptance criterion is demonstrated; behaviour matches SOT/UserStory/Stack. |
| D2 | **Valuable** | The change delivers the stated value; nothing speculative was added "for later". |
| D3 | **Simple** | No premature abstraction, no new dependency or service without a stated need (Stack §31 exclusions respected). The smallest design that meets the criteria. |
| D4 | **Aesthetic quality** (visible work) | Consistent with Design 09 and the design system tokens; reviewed on mobile and desktop widths; no placeholder lorem/template copy. |
| D5 | **Accessible** (UI) | Semantic HTML / native roles, labels, keyboard and focus order, contrast AA, reduced motion respected; automated checks plus a manual pass. |
| D6 | **Secure** | Authorization enforced in the backend, input validated, no secrets/PII in code, logs or errors, OWASP-relevant cases tested; auth/security changes get a dedicated security review. |
| D7 | **Performant** | No N+1 queries on list endpoints, paginated lists, sensible bundle size; measured when in doubt. |
| D8 | **Tested** | Failing test first for behaviour (TDD); negative/authorization tests for protected features; PostgreSQL for backend tests. |
| D9 | **Gates green** | `make lint typecheck test api-check smoke` locally and CI green; `makemigrations --check` clean; generated files only via `make api-schema api-client`. |
| D10 | **Fresh evidence** | The Jira comment contains real command output from this change (not from memory), commit SHA, files changed, and screenshots for UI. |
| D11 | **Independent review** | Someone other than the author (human or a separate reviewer agent) reviewed the diff against this DoD. |
| D12 | **Remediation** | Every review finding is fixed or explicitly accepted with a reason and, if deferred, a linked follow-up issue. |
| D13 | **Documentation** | Architecture/ownership docs updated when boundaries, contracts or operational steps change. |
| D14 | **Stakeholder-ready** | It could be shown to RamoVerde today without explanations or apologies. If it needs "ignore this part", it is not Done. |

## Jira closing comment template

```text
Done summary: <what changed and why, 2-4 lines>
Acceptance criteria: <AC → evidence, one line each>
Main files: <paths>
Gates: <commands + PASS/FAIL tails>
Commits: <SHA(s)> on <branch>
Review: <reviewer, findings, remediation>
Residual risks / follow-ups: <links or "none">
```

## Agent working rules

- Read `AGENTS.md`, the nearest scoped `AGENTS.md`, this page and the issue's sources before writing code.
- Simple and reversible → do it; security, data model and auth → plan, test-first, review.
- One owner per file set when agents work in parallel; generated files are regenerated, never hand-merged.
- Never close an issue with partial acceptance criteria; never create duplicate tickets; out-of-scope work becomes a linked issue, not silent scope growth.
