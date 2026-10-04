#include "quant/evidence/evidence_pipeline.h"

namespace quant::evidence {
namespace {

bool statistically_validated(ValidationStatus status) noexcept {
  return status == ValidationStatus::StatisticalCheckPassed ||
         status == ValidationStatus::OOSValidated;
}

}  // namespace

const EvidencePipeline::BranchDescriptor* EvidencePipeline::branch_plan(
    std::size_t& count) noexcept {
  static constexpr BranchDescriptor kPlan[] = {
      {Branch::CandleGeometry, 1, true, true},
      {Branch::GeometricNull, 1, true, true},
      {Branch::FirstPassage, 1, true, true},
      {Branch::EmpiricalFrequency, 2, false, true},
      {Branch::Bayesian, 3, true, true},
      {Branch::MonteCarlo, 4, true, true},
      {Branch::Diffusion, 4, true, true},
      {Branch::OrnsteinUhlenbeck, 4, true, true},
      {Branch::MarketDynamics, 5, true, true},
      {Branch::ShannonEntropy, 6, true, true},
      {Branch::MarketStructure, 7, false, true},
      {Branch::StatisticalModel, 2, false, true},
  };
  count = sizeof(kPlan) / sizeof(kPlan[0]);
  return kPlan;
}

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
  if (!state.data_integrity_passed ||
      state.completed_through != Stage::IndependentEvidence ||
      !records || count == 0)
    return false;

  std::size_t plan_count = 0;
  const auto* plan = branch_plan(plan_count);
  for (std::size_t i = 0; i < count; ++i) {
    const auto* descriptor = static_cast<const BranchDescriptor*>(nullptr);
    for (std::size_t j = 0; j < plan_count; ++j) {
      if (plan[j].branch == records[i].branch) {
        descriptor = &plan[j];
        break;
      }
    }
    if (!descriptor || !descriptor->implemented ||
        descriptor->independence_group !=
            independence_group(records[i].branch) ||
        records[i].model_version == 0 || records[i].data_version == 0)
      return false;

    for (std::size_t j = 0; j < i; ++j) {
      if (records[j].branch == records[i].branch)
        return false;
    }
  }

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
    if (records[i].validation != ValidationStatus::MathematicalCheckPassed &&
        records[i].validation != ValidationStatus::StatisticalCheckPassed &&
        records[i].validation != ValidationStatus::OOSValidated)
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
    if (!statistically_validated(records[i].validation))
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
  (void)state;
  return false;
}

}  // namespace quant::evidence
