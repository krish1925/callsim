check:
	uv run ruff check
	uv run ruff format --check
	uv run mypy --strict callsim/
	uv run pytest -q
