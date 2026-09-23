check:
	python -m ruff check researchos
	python -m mypy --strict researchos
	python -m pytest -k "not integration"
