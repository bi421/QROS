"""
ResearchEngine — Python reference implementation of the certified analytical surface.

Phase 5.1 — Certified Analytical Compute Surface (WP-1).

This module provides the Python reference backend (``PythonResearchBackend``)
and the facade (``ResearchEngine``) for the analytical compute surface.  It
composes the existing deterministic analytical engines (technical, probability,
portfolio, historical, fundamental, econometrics, validation) behind the
certification boundary.

Design principles:
    - Python is the scientific source of truth.  Every operation delegates to
      the existing deterministic submodule computation — NO new algorithms are
      invented here.
    - Every operation validates inputs and returns a hashed ``ResearchResult``
      (deterministic ``input_hash`` / ``result_hash`` via ``backend_hash``).
    - ``PythonResearchBackend`` subclasses BOTH ``ResearchComputationInterface``
      and the frozen ``QuantComputationInterface`` so it remains registerable
      with the existing ``BackendRouter`` (which requires the quant interface).
    - No trading logic, no broker integration, no ML, no signal generation.

This is a certification/trust layer only — it computes no trading decisions.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from researchos.quant_engine.backend_hash import canonicalize
from researchos.quant_engine.capabilities import BackendCapabilities, default_capabilities
from researchos.quant_engine.interface import QuantComputationInterface
from researchos.quant_engine.models import (
    CalculationVersion,
    SimulationRequest,
    SimulationResult,
)
from researchos.quant_engine.research_interface import (
    RESEARCH_OPERATIONS,
    RESEARCH_SURFACE_VERSION,
    ResearchComputationInterface,
    ResearchResult,
    build_research_result,
)

# NOTE: the 7 core QuantComputationInterface ops are inherited from
# QuantComputationInterface.  PythonResearchBackend implements them by
# delegating to PythonQuantBackend (the frozen reference), so the research
# backend is a fully-qualified router-registerable candidate.

CALCULATION_V1 = CalculationVersion.CALCULATION_V1


class PythonResearchBackend(ResearchComputationInterface, QuantComputationInterface):
    """
    Python reference backend for the certified research analytical surface.

    All analytical operations delegate to the existing deterministic submodule
    functions and wrap outputs in a hashed ``ResearchResult``.
    """

    # ── identity / certification ────────────────────────────────────────

    def get_version(self) -> str:
        return "python_research_1.0.0"

    def capabilities(self) -> BackendCapabilities:
        base = default_capabilities(self)
        return BackendCapabilities(
            backend_name="PythonResearchBackend",
            version=self.get_version(),
            supported_operations=base.supported_operations,
            deterministic=base.deterministic,
            stateless=base.stateless,
            no_timestamps=base.no_timestamps,
            no_randomness=base.no_randomness,
            explicit_typing=base.explicit_typing,
        )

    # ── 7 core QuantComputationInterface ops (delegate to frozen reference) ──

    def calculate_returns(
        self,
        prices: list[float],
        return_type: str = "percentage",
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> list[float]:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_returns(prices, return_type, calculation_version)

    def calculate_volatility(
        self,
        returns: list[float],
        method: str = "standard_deviation",
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> float:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_volatility(returns, method, calculation_version)

    def calculate_drawdown(
        self,
        equity_curve: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_drawdown(equity_curve, calculation_version)

    def calculate_statistics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_statistics(returns, calculation_version)

    def run_simulation(
        self,
        request: SimulationRequest,
        dataset: Any,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> SimulationResult:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().run_simulation(request, dataset, calculation_version)

    def calculate_metrics(
        self,
        returns: list[float],
        equity_curve: list[float],
        risk_free_rate: float = 0.0,
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, float]:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_metrics(returns, equity_curve, risk_free_rate, calculation_version)

    def calculate_performance_analytics(
        self,
        returns: list[float],
        calculation_version: CalculationVersion = CALCULATION_V1,
    ) -> dict[str, Any]:
        from researchos.quant_engine.backend import PythonQuantBackend

        return PythonQuantBackend().calculate_performance_analytics(returns, calculation_version)

    # ── Research analytical ops (delegate to existing deterministic submodules) ──

    def research_technical(self, bars: Any, specs: Sequence[Any], **params: Any) -> ResearchResult:
        from researchos.quant_engine.technical.engine import TechnicalAnalysisEngine

        engine = TechnicalAnalysisEngine()
        batch = engine.compute_batch(bars, list(specs))
        return self._wrap("research_technical", "technical", batch.to_dict(), params, "PythonResearchBackend")

    def research_probabilistic_fit(self, samples: Sequence[float], distribution: str, **params: Any) -> ResearchResult:
        from researchos.quant_engine.probability.statistics import (
            fit_log_normal,
            fit_normal,
            fit_student_t,
            kernel_density_estimate,
        )

        if distribution == "normal":
            fit = fit_normal(list(samples))
        elif distribution == "log_normal":
            fit = fit_log_normal(list(samples))
        elif distribution == "student_t":
            fit = fit_student_t(list(samples), float(params.get("df", 5.0)))
        elif distribution == "kde":
            x = float(params.get("x", 0.0))
            return self._wrap(
                "research_probabilistic_fit",
                "probability",
                {"kde": kernel_density_estimate(list(samples), x, params.get("bandwidth"))},
                dict(params, distribution=distribution),
                "PythonResearchBackend",
            )
        else:
            raise ValueError(f"Unknown distribution '{distribution}'")
        return self._wrap(
            "research_probabilistic_fit",
            "probability",
            fit.to_dict(),
            dict(params, distribution=distribution),
            "PythonResearchBackend",
        )

    def research_probabilistic_hypothesis(self, samples: Sequence[float], test: str, **params: Any) -> ResearchResult:
        from researchos.quant_engine.probability.statistics import (
            one_sample_t_test,
            z_test,
        )

        if test == "t" or test == "one_sample_t":
            result = one_sample_t_test(
                list(samples),
                float(params.get("mu0", 0.0)),
                float(params.get("significance_level", 0.05)),
            )
        elif test == "z":
            result = z_test(
                float(params.get("sample_mean", _mean(list(samples)))),
                float(params.get("population_mean", 0.0)),
                float(params.get("std_dev", 1.0)),
                int(params.get("n", len(list(samples)))),
                float(params.get("significance_level", 0.05)),
            )
        else:
            raise ValueError(f"Unknown hypothesis test '{test}'")
        return self._wrap(
            "research_probabilistic_hypothesis",
            "probability",
            result.to_dict(),
            dict(params, test=test),
            "PythonResearchBackend",
        )

    def research_portfolio_metrics(
        self,
        portfolio: Any,
        benchmark_returns: Sequence[float] | None = None,
        **params: Any,
    ) -> ResearchResult:
        from researchos.quant_engine.portfolio.analytics import compute_portfolio_metrics

        periods = int(params.get("periods_per_year", 252))
        metrics = compute_portfolio_metrics(portfolio, benchmark_returns, periods)
        return self._wrap(
            "research_portfolio_metrics",
            "portfolio",
            metrics.to_dict(),
            dict(params, periods_per_year=periods),
            "PythonResearchBackend",
        )

    def research_historical(self, returns: Sequence[float], metric: str, **params: Any) -> ResearchResult:
        from researchos.quant_engine.historical.analytics import (
            drawdown_statistics,
            extract_features,
            pattern_frequencies,
            session_statistics,
            state_transition_table,
            volatility_clustering,
        )
        from researchos.quant_engine.historical.contracts import ReturnSeries

        series = ReturnSeries(returns=list(returns))
        if metric == "features":
            output = extract_features(series).to_dict()
        elif metric == "drawdown":
            output = drawdown_statistics(series).to_dict()
        elif metric == "session":
            output = session_statistics(series)
        elif metric == "volatility_clustering":
            output = volatility_clustering(series, int(params.get("window", 20)))
        elif metric == "patterns":
            output = pattern_frequencies(
                series,
                int(params.get("window", 5)),
                float(params.get("up_threshold", 0.0)),
            )
        elif metric == "state_transitions":
            output = state_transition_table(series, int(params.get("lookback", 20))).to_dict()
        else:
            raise ValueError(f"Unknown historical metric '{metric}'")
        return self._wrap(
            "research_historical",
            "historical",
            output,
            dict(params, metric=metric),
            "PythonResearchBackend",
        )

    def research_fundamental(self, analytics: str, inputs: Any, **params: Any) -> ResearchResult:
        from researchos.quant_engine.fundamental.analytics import (
            fit_macro_factor_model,
            keyword_sentiment,
            macro_series_statistics,
            normalize_news_text,
            yield_curve_metrics,
        )

        output: Any
        if analytics == "macro_statistics":
            output = macro_series_statistics(list(inputs))
        elif analytics == "yield_curve":
            maturities = list(inputs.get("maturities", []))
            yields = list(inputs.get("yields", []))
            output = yield_curve_metrics(maturities, yields)
        elif analytics == "macro_factor":
            model = fit_macro_factor_model(list(inputs["target"]), dict(inputs["features"]))
            output = model.to_dict()
        elif analytics == "news_normalize":
            output = {"normalized_text": normalize_news_text(str(inputs))}
        elif analytics == "keyword_sentiment":
            output = {"sentiment": keyword_sentiment(str(inputs))}
        else:
            raise ValueError(f"Unknown fundamental analytics '{analytics}'")
        return self._wrap(
            "research_fundamental",
            "fundamental",
            output,
            dict(params, analytics=analytics),
            "PythonResearchBackend",
        )

    def research_econometric_analysis(self, values: Sequence[float], model: str, **params: Any) -> ResearchResult:
        from researchos.quant_engine.econometrics.core import (
            adf_test,
            compute_acf,
            fit_ar,
            fit_arima,
            fit_arma,
            fit_garch,
            fit_ma,
            kpss_test,
        )

        if model == "acf":
            output = compute_acf(list(values), int(params.get("max_lag", 20))).to_dict()
        elif model == "adf":
            output = adf_test(list(values), int(params.get("max_lag", 1))).to_dict()
        elif model == "kpss":
            output = kpss_test(list(values)).to_dict()
        elif model == "ar":
            output = fit_ar(list(values), int(params.get("p_order", 1))).to_dict()
        elif model == "ma":
            output = fit_ma(list(values), int(params.get("q_order", 1))).to_dict()
        elif model == "arma":
            output = fit_arma(
                list(values),
                int(params.get("p_order", 1)),
                int(params.get("q_order", 1)),
            ).to_dict()
        elif model == "arima":
            output = fit_arima(
                list(values),
                int(params.get("p", 1)),
                int(params.get("d", 1)),
                int(params.get("q", 1)),
            ).to_dict()
        elif model == "garch":
            output = fit_garch(
                list(values),
                int(params.get("p", 1)),
                int(params.get("q", 1)),
            ).to_dict()
        else:
            raise ValueError(f"Unknown econometric model '{model}'")
        return self._wrap(
            "research_econometric_analysis",
            "econometrics",
            output,
            dict(params, model=model),
            "PythonResearchBackend",
        )

    def research_validation(
        self,
        dataset: Any,
        train_size: int,
        validation_size: int,
        step_size: int,
        **params: Any,
    ) -> ResearchResult:
        from researchos.quant_engine.validation.walk_forward import WalkForwardValidator

        validator = WalkForwardValidator(
            train_size=int(train_size),
            validation_size=int(validation_size),
            step_size=int(step_size),
            test_size=int(params["test_size"]) if "test_size" in params else None,
        )
        report = validator.generate_report(dataset)
        return self._wrap(
            "research_validation",
            "validation",
            report,
            dict(
                params,
                train_size=int(train_size),
                validation_size=int(validation_size),
                step_size=int(step_size),
            ),
            "PythonResearchBackend",
        )

    # ── internal ────────────────────────────────────────────────────────

    def _wrap(
        self,
        operation: str,
        domain: str,
        output: Any,
        parameters: Any,
        backend: str,
    ) -> ResearchResult:
        return build_research_result(
            operation=operation,
            domain=domain,
            output=canonicalize(output),
            parameters=canonicalize(parameters),
            backend=backend,
            version=self.get_version(),
            methodology_version=RESEARCH_SURFACE_VERSION,
        )


def _mean(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


class ResearchEngine:
    """
    Facade over the certified research analytical surface.

    ``ResearchEngine`` wraps a research backend (Python reference by default)
    and exposes the analytical operations as ergonomic methods.  It is a thin
    pass-through: it performs no computation of its own, only marshalling.
    """

    def __init__(self, backend: ResearchComputationInterface | None = None) -> None:
        self._backend = backend or PythonResearchBackend()

    @property
    def backend(self) -> ResearchComputationInterface:
        """The active research backend."""
        return self._backend

    def get_version(self) -> str:
        return self._backend.get_version()

    def capabilities(self) -> BackendCapabilities:
        return self._backend.capabilities()

    # ── analytical operations ───────────────────────────────────────────

    def technical(self, bars: Any, specs: Sequence[Any], **params: Any) -> ResearchResult:
        return self._backend.research_technical(bars, specs, **params)

    def probabilistic_fit(self, samples: Sequence[float], distribution: str, **params: Any) -> ResearchResult:
        return self._backend.research_probabilistic_fit(samples, distribution, **params)

    def probabilistic_hypothesis(self, samples: Sequence[float], test: str, **params: Any) -> ResearchResult:
        return self._backend.research_probabilistic_hypothesis(samples, test, **params)

    def portfolio_metrics(
        self,
        portfolio: Any,
        benchmark_returns: Sequence[float] | None = None,
        **params: Any,
    ) -> ResearchResult:
        return self._backend.research_portfolio_metrics(portfolio, benchmark_returns, **params)

    def historical(self, returns: Sequence[float], metric: str, **params: Any) -> ResearchResult:
        return self._backend.research_historical(returns, metric, **params)

    def fundamental(self, analytics: str, inputs: Any, **params: Any) -> ResearchResult:
        return self._backend.research_fundamental(analytics, inputs, **params)

    def econometric_analysis(self, values: Sequence[float], model: str, **params: Any) -> ResearchResult:
        return self._backend.research_econometric_analysis(values, model, **params)

    def validation(self, dataset: Any, train_size: int, validation_size: int, step_size: int, **params: Any) -> ResearchResult:
        return self._backend.research_validation(dataset, train_size, validation_size, step_size, **params)


def research_capabilities(backend: Any) -> BackendCapabilities:
    """Build the advertised capability declaration for a research backend."""
    base = default_capabilities(backend)
    return BackendCapabilities(
        backend_name=type(backend).__name__,
        version=str(getattr(backend, "get_version", lambda: type(backend).__name__)()),
        supported_operations=tuple(RESEARCH_OPERATIONS) + tuple(base.supported_operations),
        deterministic=base.deterministic,
        stateless=base.stateless,
        no_timestamps=base.no_timestamps,
        no_randomness=base.no_randomness,
        explicit_typing=base.explicit_typing,
    )


__all__ = [
    "RESEARCH_OPERATIONS",
    "RESEARCH_SURFACE_VERSION",
    "PythonResearchBackend",
    "ResearchEngine",
    "research_capabilities",
]
