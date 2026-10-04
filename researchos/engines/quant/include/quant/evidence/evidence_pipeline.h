#ifndef QROS_QUANT_EVIDENCE_PIPELINE_H
#define QROS_QUANT_EVIDENCE_PIPELINE_H

#include <cstddef>
#include <cstdint>
#include "quant/evidence/evidence_contract.h"

namespace quant::evidence {

enum class Stage : std::uint8_t {
  RawMarketData,
  DataIntegrity,
  IndependentEvidence,
  MathematicalVerification,
  StatisticalValidation,
  EvidenceIntegration,
  Calibration,
  ProbabilitySynthesis,
};

struct PipelineState final {
  Stage completed_through{Stage::RawMarketData};
  bool data_integrity_passed{false};
  bool mathematical_verification_passed{false};
  bool statistical_validation_passed{false};
  bool calibration_passed{false};
  bool probability_synthesis_enabled{false};
  std::size_t evidence_count{0};
};

class EvidencePipeline final {
public:
  struct BranchDescriptor final {
    Branch branch{};
    std::uint32_t independence_group{0};
    bool implemented{false};
    bool parallel_safe{false};
  };

  static PipelineState begin(std::size_t evidence_capacity) noexcept;

  // Static registry: independent branches may be executed concurrently,
  // but their outputs remain separate until the validation gates.
  static const BranchDescriptor* branch_plan(std::size_t& count) noexcept;

  static bool accept_integrity(PipelineState& state) noexcept;

  static bool accept_mathematical_verification(
      PipelineState& state,
      const EvidenceRecord* records,
      std::size_t count) noexcept;

  static bool accept_statistical_validation(
      PipelineState& state,
      const EvidenceRecord* records,
      std::size_t count) noexcept;

  static bool accept_calibration(PipelineState& state) noexcept;

  // Evidence integration is intentionally a collection step only.
  // It MUST NOT average or otherwise synthesize probabilities.
  static bool accept_evidence(
      PipelineState& state,
      const EvidenceRecord* records,
      std::size_t count) noexcept;

  // Final probability synthesis is deliberately disabled in this layer.
  static bool probability_synthesis_allowed(
      const PipelineState& state) noexcept;
};

}  // namespace quant::evidence

#endif
