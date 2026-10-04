#include "quant/evidence/evidence_pipeline.h"

namespace quant::evidence {

PipelineState EvidencePipeline::begin(std::size_t evidence_capacity) noexcept {
  PipelineState state{};
  state.evidence_count = 0;
  if (evidence_capacity == 0)
    state.completed_through = Stage::DataIntegrity;
  return state;
}

bool EvidencePipeline::accept_integrity(PipelineState& state) noexcept {
  if (state.completed_through != Stage::RawMarketData &&
      state.completed_through != Stage::DataIntegrity)
    return false;
  state.data_integrity_passed = true;
  state.completed_through = Stage::IndependentEvidence;
  return true;
}

bool EvidencePipeline::accept_evidence(
    PipelineState& state, const EvidenceRecord* records,
    std::size_t count) noexcept {
  if (!state.data_integrity_passed || !records || count == 0)
    return false;
  state.evidence_count = count;
  state.completed_through = Stage::MathematicalVerification;
  return true;
}

bool EvidencePipeline::accept_mathematical_verification(
    PipelineState& state, const EvidenceRecord* records,
    std::size_t count) noexcept {
  if (state.completed_through != Stage::MathematicalVerification ||
      !records || count != state.evidence_count)
    return false;

  for (std::size_t i = 0; i < count; ++i) {
    if (records[i].validation != ValidationStatus::MathematicalCheckPassed)
      return false;
  }
  state.mathematical_verification_passed = true;
  state.completed_through = Stage::StatisticalValidation;
  return true;
}

bool EvidencePipeline::accept_statistical_validation(
    PipelineState& state, const EvidenceRecord* records,
    std::size_t count) noexcept {
  if (!state.mathematical_verification_passed ||
      state.completed_through != Stage::StatisticalValidation ||
      !records || count != state.evidence_count)
    return false;

  for (std::size_t i = 0; i < count; ++i) {
    if (records[i].validation == ValidationStatus::Rejected ||
        records[i].validation == ValidationStatus::NotValidated)
      return false;
  }
  state.statistical_validation_passed = true;
  state.completed_through = Stage::EvidenceIntegration;
  return true;
}

bool EvidencePipeline::accept_calibration(PipelineState& state) noexcept {
  if (!state.statistical_validation_passed ||
      state.completed_through != Stage::EvidenceIntegration)
    return false;
  state.calibration_passed = true;
  state.completed_through = Stage::Calibration;
  return true;
}

bool EvidencePipeline::probability_synthesis_allowed(
    const PipelineState& state) noexcept {
  // Intentionally false until a dependency-aware, OOS-calibrated synthesizer
  // is implemented. This prevents individual evidence branches from being
  // silently averaged into a probability.
  (void)state;
  return false;
}

}  // namespace quant::evidence
