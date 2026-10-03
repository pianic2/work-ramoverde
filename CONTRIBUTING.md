# Contributing

Read `AGENTS.md` and the nearest scoped file first. Use one scoped branch and keep diffs focused. Python uses uv; JavaScript uses pnpm. Model changes need reviewed migrations and PostgreSQL tests. API changes regenerate OpenAPI and the client. Mobile UI must reuse the personal component library's public API.

Before opening a pull request, run `make lint`, `make typecheck`, `make test`, `make api-check`, `docker compose config`, and `git diff --check` as applicable. Document real environment limitations rather than skipping a check silently. Never commit `.env`, credentials, build output, or handwritten generated files.
