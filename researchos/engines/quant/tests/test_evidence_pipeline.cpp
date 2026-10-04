#include <gtest/gtest.h>
#include "quant/evidence/evidence_pipeline.h"

using namespace quant::evidence;

TEST(EvidencePipelineTest, EnforcesLayerOrder) {
  EvidenceRecord record{};
  record.branch = Branch::GeometricNull;
  record.quantity = Quantity::Probability;
  record.validation = ValidationStatus::MathematicalCheckPassed;

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
