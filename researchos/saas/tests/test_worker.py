from uuid import uuid4
import pytest
from researchos.research_core.contracts import ResearchArtifact, ResearchResult
from researchos.saas.contracts import ResearchJob, ResearchJobStatus
from researchos.saas.store import InMemoryResearchJobStore
from researchos.saas.worker import ResearchWorker
class StubExecutor:
    def __init__(self,result=None,error=None): self.result,self.error,self.calls=result,error,0
    def execute(self,job_id):
        self.calls+=1
        if self.error:
            raise self.error
        assert self.result is not None
        return self.result
def _job(workspace_id):
    return ResearchJob(id=uuid4(),workspace_id=workspace_id,dataset_version_id=uuid4(),workflow_id="xauusd_m1_frozen_research_v1",status=ResearchJobStatus.QUEUED)
def _result(status="SUCCEEDED"):
    return ResearchResult(status=status,source_dataset_sha256="0"*64,artifacts=(ResearchArtifact("artifact-1","evidence","1"*64),) if status=="SUCCEEDED" else ())
def test_worker_moves_queued_job_to_succeeded():
    ws=uuid4(); store=InMemoryResearchJobStore()
    job=store.create(_job(ws))
    ex=StubExecutor(_result())
    result=ResearchWorker(store,ex).run_once(ws,job.id)
    assert result.status=="SUCCEEDED"
    assert ex.calls==1
    assert store.get(ws,job.id).status==ResearchJobStatus.SUCCEEDED
def test_worker_marks_job_failed_when_executor_raises():
    ws=uuid4(); store=InMemoryResearchJobStore()
    job=store.create(_job(ws))
    ex=StubExecutor(error=RuntimeError("scientific failure"))
    with pytest.raises(RuntimeError,match="scientific failure"): ResearchWorker(store,ex).run_once(ws,job.id)
    assert store.get(ws,job.id).status==ResearchJobStatus.FAILED
def test_worker_cannot_run_job_from_another_workspace():
    store=InMemoryResearchJobStore()
    owner,other=uuid4(),uuid4()
    job=store.create(_job(owner))
    with pytest.raises(KeyError): ResearchWorker(store,StubExecutor(_result())).run_once(other,job.id)
def test_worker_cannot_double_claim_active_job():
    ws=uuid4(); store=InMemoryResearchJobStore()
    job=store.create(_job(ws)); first=store.claim(ws,job.id,"worker-a",900)
    with pytest.raises(RuntimeError,match="already claimed"): store.claim(ws,job.id,"worker-b",900)
    store.finish(ws,job.id,first.token,ResearchJobStatus.SUCCEEDED)
def test_stale_lease_token_cannot_finish_job():
    ws=uuid4(); store=InMemoryResearchJobStore()
    job=store.create(_job(ws))
    lease=store.claim(ws,job.id,"worker-a",900)
    with pytest.raises(RuntimeError,match="stale or invalid worker lease"): store.finish(ws,job.id,uuid4(),ResearchJobStatus.SUCCEEDED)
