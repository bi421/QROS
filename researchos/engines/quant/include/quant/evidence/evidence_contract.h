#ifndef QROS_QUANT_EVIDENCE_CONTRACT_H
#define QROS_QUANT_EVIDENCE_CONTRACT_H

#include <cstddef>
#include <cstdint>

namespace quant::evidence {

enum class Branch : std::uint8_t {
  CandleGeometry,
  GeometricNull,
  FirstPassage,
  EmpiricalFrequency,
  Bayesian,
  MonteCarlo,
  Diffusion,
  OrnsteinUhlenbeck,
  MarketDynamics,
  ShannonEntropy,
  MarketStructure,
  StatisticalModel,
};

enum class Quantity : std::uint8_t {
  Feature,
  Probability,
  Density,
  Statistic,
  Score,
};

enum class ValidationStatus : std::uint8_t {
  NotValidated,
  MathematicalCheckPassed,
  StatisticalCheckPassed,
  OOSValidated,
  Rejected,
};

struct EvidenceRecord final {
  Branch branch{};
  Quantity quantity{};
  ValidationStatus validation{ValidationStatus::NotValidated};
  double value{0.0};
  double uncertainty_lower{0.0};
  double uncertainty_upper{0.0};
  double sample_size{0.0};
  std::uint64_t model_version{0};
  std::uint64_t data_version{0};
  std::uint32_t independence_group{0};
};

constexpr std::uint32_t independence_group(Branch branch) noexcept {
  switch (branch) {
    case Branch::CandleGeometry:
    case Branch::GeometricNull:
    case Branch::FirstPassage:
      return 1;
    case Branch::EmpiricalFrequency:
    case Branch::StatisticalModel:
      return 2;
    case Branch::Bayesian:
      return 3;
    case Branch::MonteCarlo:
    case Branch::Diffusion:
    case Branch::OrnsteinUhlenbeck:
      return 4;
    case Branch::MarketDynamics:
      return 5;
    case Branch::ShannonEntropy:
      return 6;
    case Branch::MarketStructure:
      return 7;
  }
  return 0;
}

}  // namespace quant::evidence

#endif
