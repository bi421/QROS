PYTHON ?= python

.PHONY: fast core saas all lint type

# L0: smallest developer feedback loop.
fast:
	$(PYTHON) -m pytest researchos/experiments/phase52_rebuild/tests/test_context_execution.py -q

# L1: affected scientific subsystem.
core:
	$(PYTHON) -m pytest researchos/experiments/phase52_rebuild/tests -q

# L1: SaaS subsystem.
saas:
	$(PYTHON) -m pytest researchos/saas/tests -q

# L2/L3: explicit full validation; never use this as the default edit loop.
all:
	$(PYTHON) -m ruff check researchos
	$(PYTHON) -m mypy --strict researchos
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check researchos

type:
	$(PYTHON) -m mypy --strict researchos
