# Backend instructions

Use `uv` for every Python operation. Django models and serializers define behavior; drf-spectacular is the OpenAPI source. PostgreSQL is the only supported database. Add migrations with `make migrations`, review them, and test with PostgreSQL. Keep browser session/CSRF and mobile JWT boundaries separate. Run `uv run ruff check .`, `uv run mypy config apps`, and `uv run pytest` before completion.
