# Contributing to ResearchOS

Thank you for your interest in contributing to ResearchOS! This guide explains how to contribute code, documentation, and features.

---

## Core Principles

ResearchOS is built on three core principles. **All contributions must align with these:**

1. **Determinism** — Every computation must be deterministic and reproducible
2. **Explainability** — Every conclusion must have complete reasoning and evidence
3. **Scientific Rigor** — Every hypothesis must be falsifiable and testable

**Non-Negotiable Rule:** ResearchOS never executes trades or sends orders to exchanges. Architecture guards enforce this.

---

## Evidence-First Development

Before creating a new module, script, engine, or report, search the repository first. Reuse or extend an existing canonical implementation whenever possible. New parallel implementations require an explicit architecture decision.

Before reporting that work is complete, run:

```bash
researchos-health
```

If the command was not run, the status is **UNVERIFIED**. AI-generated summaries are proposals, not evidence.

Do not create one-off files such as `FORENSIC_AUDIT*`, `run_full_analysis*.py`, `pytest_*.txt`, `ruff_*.txt`, or scratch scripts at the repository root. Retained historical material belongs under `reports/YYYY-MM/`.

---

## Development Workflow

### 1. Set Up Your Environment

```bash
# Clone the repository
cd ResearchOS

# Create a feature branch from main
# Never create work on master.
git checkout main
git pull origin main
git checkout -b feat/your-feature-name

# Set up Python environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev,test,saas]"
```

### 2. Code Style & Conventions

**Python:**
- Follow PEP 8
- Use type hints for public APIs
- Document public functions with docstrings
- Max line length: 100 characters for code, 80 for docstrings

### 3. Testing Requirements

**MANDATORY:** All code changes require tests.

```bash
# Fast truth check before handing work to review
researchos-health

# Focused tests are useful during implementation
python -m pytest path/to/test_file.py -q
```

### 4. Scope Discipline

The repository already contains historical duplicate/legacy areas. Do not expand them. In particular, do not add another quant-engine tree or another analysis/audit script family without first checking whether the capability already exists.

Every new engine or capability must state which architecture block owns it and how it crosses the scientific core boundary.

### 5. Scientific Gate Discipline

Walk-forward validation and out-of-sample holdout are mandatory for research claims. Multiple-testing correction must be applied before an edge is accepted. Weak or inconclusive evidence must remain weak or inconclusive.

### 6. Cleanup

Run a short cleanup pass weekly. Remove or archive stale one-off artifacts; do not delete historical evidence that may be useful for audit. Preserve it under `reports/YYYY-MM/`.
