#include <gtest/gtest.h>
#include "quant/evidence/evidence_pipeline.h"

using namespace quant::evidence;

TEST(EvidencePipelineTest, EnforcesLayerOrder) {
  EvidenceRecord record{};
  record.branch = Branch::GeometricNull;
  record.quantity = Quantity::Probability;
  record.validation = ValidationStatus::StatisticalCheckPassed;

  auto state = EvidencePipeline::begin(1);
  EXPECT_FALSE(EvidencePipeline::accept_evidence(state, &record, 1));

  EXPECT_TRUE(EvidencePipeline::accept_integrity(state));
  EXPECT_TRUE(EvidencePipeline::accept_evidence(state, &record, 1));
  EXPECT_TRUE(EvidencePipeline::accept_mathematical_verification(state, &record, 1));
  EXPECT_TRUE(EvidencePipeline::accept_statistical_validation(state, &record, 1));
  EXPECT_TRUE(EvidencePipeline::accept_calibration(state));
  EXPECT_FALSE(EvidencePipeline::probability_synthesis_allowed(state));
}

TEST(EvidencePipelineTest, RejectsUnvalidatedEvidence) {
  EvidenceRecord records[2]{};
  records[0].validation = ValidationStatus::MathematicalCheckPassed;
  records[1].validation = ValidationStatus::NotValidated;

  auto state = EvidencePipeline::begin(2);
  ASSERT_TRUE(EvidencePipeline::accept_integrity(state));
  ASSERT_TRUE(EvidencePipeline::accept_evidence(state, records, 2));
  EXPECT_FALSE(EvidencePipeline::accept_mathematical_verification(state, records, 2));
}

TEST(EvidencePipelineTest, RejectsStatisticallyUnvalidatedEvidence) {
  EvidenceRecord record{};
  record.validation = ValidationStatus::MathematicalCheckPassed;

  auto state = EvidencePipeline::begin(1);
  ASSERT_TRUE(EvidencePipeline::accept_integrity(state));
  ASSERT_TRUE(EvidencePipeline::accept_evidence(state, &record, 1));
  ASSERT_TRUE(EvidencePipeline::accept_mathematical_verification(state, &record, 1));
  EXPECT_FALSE(EvidencePipeline::accept_statistical_validation(state, &record, 1));
}

TEST(EvidencePipelineTest, OOSValidationCanAdvanceToCalibration) {
  EvidenceRecord record{};
  record.validation = ValidationStatus::OOSValidated;

  auto state = EvidencePipeline::begin(1);
  ASSERT_TRUE(EvidencePipeline::accept_integrity(state));
  ASSERT_TRUE(EvidencePipeline::accept_evidence(state, &record, 1));
  ASSERT_TRUE(EvidencePipeline::accept_mathematical_verification(state, &record, 1));
  ASSERT_TRUE(EvidencePipeline::accept_statistical_validation(state, &record, 1));
  EXPECT_TRUE(EvidencePipeline::accept_calibration(state));
}

TEST(EvidencePipelineTest, EvidenceCannotBeAcceptedTwice) {
  EvidenceRecord record{};
  record.validation = ValidationStatus::StatisticalCheckPassed;

  auto state = EvidencePipeline::begin(1);
  ASSERT_TRUE(EvidencePipeline::accept_integrity(state));
  ASSERT_TRUE(EvidencePipeline::accept_evidence(state, &record, 1));
  EXPECT_FALSE(EvidencePipeline::accept_evidence(state, &record, 1));
}


TEST(EvidencePipelineTest, BranchPlanSeparatesImplementedAndMissingLayers) {
  std::size_t count = 0;
  const auto* plan = EvidencePipeline::branch_plan(count);
  ASSERT_NE(plan, nullptr);
  ASSERT_EQ(count, 12u);

  std::size_t implemented = 0;
  for (std::size_t i = 0; i < count; ++i) {
    EXPECT_NE(plan[i].independence_group, 0u);
    EXPECT_TRUE(plan[i].parallel_safe);
    implemented += plan[i].implemented ? 1u : 0u;
  }

  EXPECT_EQ(implemented, 9u);
  EXPECT_FALSE(plan[3].implemented);   // empirical frequency
  EXPECT_FALSE(plan[10].implemented);  // market structure
  EXPECT_FALSE(plan[11].implemented);  // statistical model
}
