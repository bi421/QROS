# ResearchOS

**Institutional-Grade Market Research Platform**

[![Health](https://github.com/bi421/ResearchOS/actions/workflows/ci.yml/badge.svg)](https://github.com/bi421/ResearchOS/actions/workflows/ci.yml)

> **Health evidence rule:** a local or AI-reported "checked" state is **UNVERIFIED** until `scripts/final_health_check.py` produces `.health/last_run.json`, or the corresponding GitHub Actions Health Evidence Gate passes and uploads that artifact.

ResearchOS is a deterministic, explainable, scientific market research platform that produces institutional-quality research for human traders. It is **NOT** an automated trading system — it never executes trades, sends orders, or makes final trading decisions.

## Key Principles

- **Determinism**: Every computation is deterministic and reproducible
- **Explainability**: Every conclusion has a complete reasoning trace
- **Scientific Rigor**: Every hypothesis is falsifiable
- **No Trading**: ResearchOS never executes trades or sends orders

## Documentation

The ResearchOS constitutional framework consists of 17 articles:

| Article | Title | Description |
|---|---|---|
| I | Vision | Mission, philosophy, core beliefs |
| II | Scope | 3 functions, boundaries, responsibility matrix |
| III | Principles | Scientific method, falsifiability, reproducibility |
| IV | Glossary | Core terms, research concepts, cognitive concepts |
| V | Architecture | Three-engine architecture, data flow, audit trail |
| VI | Roadmap | Development phases, success metrics, non-goals |
| VII | Research Methodology | 9-stage deterministic pipeline |
| VIII | Data Sources | 116 sources, 15 categories |
| IX | Market Ontology | 150+ concepts, 6 layers |
| X | Reasoning Engine | 7-stage pipeline, R1-R8 guarantees |
| XI | Scenario Engine | A/B/C construction, S1-S8 guarantees |
| XII | Validation Engine | 5-stage pipeline, V1-V8 guarantees |
| XIII | Knowledge Engine | 5 repositories, K1-K8 guarantees |
| XIV | Cognitive Growth Engine | 6 dimensions, C1-C8 guarantees |
| XV | System Architecture | 3 engines, 25 modules |
| XVI | Scientific Reasoning Framework | 10 sections |
| XVII | Object Model | 20 object types, 12 layers |

## Installation

```bash
pip install -e .
```

## Health evidence

```bash
python scripts/final_health_check.py
```

The command records the commit SHA, UTC timestamp, ruff result, pytest result, C++ configure/build result, and git status in `.health/last_run.json`. The local evidence file is ephemeral; CI uploads the same file as a workflow artifact named `researchos-health-<commit-sha>`.

## Quick Start

```python
from researchos import Research, Observation, Evidence, Hypothesis, Scenario

research = Research(
    question="What is the inflation outlook?",
    time_horizon="Monthly",
    asset="US",
)

from datetime import datetime, timezone

obs = Observation(
    source="MACRO:CPI_YOY",
    timestamp=datetime(2024, 1, 1, tzinfo=timezone.utc),
    value=3.2,
    unit="percent",
)
obs.validate()

ev = Evidence(
    observation_id=obs.id,
    hypothesis_id="hyp1",
    interpretation="Inflation is moderating",
    direction="Supporting",
)

hyp = Hypothesis(
    research_id=research.id,
    type="Primary",
    statement="Inflation will continue to moderate",
    evidence_strength=0.8,
    coherence=0.7,
    plausibility=0.9,
    falsifiability=0.6,
)

from researchos import ScenarioSet
ss = ScenarioSet(research_id=research.id)
ss.add_scenario(Scenario(hypothesis_id=hyp.id, type="Base", probability=0.5))
ss.add_scenario(Scenario(hypothesis_id=hyp.id, type="Bull", probability=0.3))
ss.add_scenario(Scenario(hypothesis_id=hyp.id, type="Bear", probability=0.2))
ss.normalize_probabilities()
research.complete()
```

## Project Structure

```
ResearchOS/
├── docs/                    # Constitutional documentation
├── researchos/              # Python package
├── examples/                # Usage examples
├── scripts/                 # Reproducible operational entry points
└── README.md
```

## Repository Hygiene

- Canonical runtime code belongs under `researchos/`.
- Reproducible operational entry points belong under `scripts/`.
- Automated tests belong under the relevant `researchos/*/tests/` package.
- Historical reports and completed audit material belong under `docs/archive/`.
- One-off exploratory, repair, manual-test, and scratch scripts must not be added to the repository root.
- Credentials and API keys must never be committed; use environment variables or local secret configuration.

## Running Tests

```bash
pytest researchos/tests/ -v
```

## License

ResearchOS is a scientific research platform. All outputs are for research purposes only.
