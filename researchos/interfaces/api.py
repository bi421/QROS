from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from researchos.pipeline import ResearchPipeline
from researchos.storage.repository import ResearchRepository

app = FastAPI(title="ResearchOS API", version="1.0.0", description="Research Infrastructure API")
repo = ResearchRepository()
pipeline = ResearchPipeline(repo)


class CycleRequest(BaseModel):
    topic: str


@app.post("/cycles/run")
def run_cycle(req: CycleRequest) -> dict[str, object]:
    try:
        research = pipeline.start_research(question=req.topic)
        return {"status": "success", "research_id": research.id, "topic": req.topic, "data": research.to_dict()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str) -> object:
    cycle_data = repo.load_cycle(cycle_id)
    if not cycle_data:
        raise HTTPException(status_code=404, detail="Research cycle not found")
    return cycle_data


@app.get("/audit/verify")
def verify_audit() -> dict[str, object]:
    is_valid = repo.verify_audit_chain()
    return {"audit_chain_valid": is_valid, "status": "SECURE" if is_valid else "COMPROMISED"}
