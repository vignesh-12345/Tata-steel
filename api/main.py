"""
MINERVA FastAPI Backend
REST API for all agent functions.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.orchestrator import get_orchestrator
from database.db_manager import (
    get_latest_readings, get_health_trend, get_sensor_history,
    get_maintenance_history, get_all_latest_health, log_feedback,
    get_failure_events, get_spares, build_equipment_context,
    get_anomalous_sensors,
)
from config import EQUIPMENT_REGISTRY

app = FastAPI(
    title="MINERVA API",
    description="Maintenance Intelligence with Neural Engines for Reasoning, Vigilance, and Action",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response models ───────────────────────────────────────────────────

class QueryRequest(BaseModel):
    query: str
    equip_id: Optional[str] = None

class FeedbackRequest(BaseModel):
    equip_id: str
    query: str
    recommendation: str
    feedback_type: str  # "correct" | "incorrect" | "partial"
    comment: str = ""
    was_correct: bool


# ── Endpoints ─────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    return {
        "system": "MINERVA",
        "status": "operational",
        "description": "Maintenance Intelligence for Steel Plant Operations",
        "endpoints": ["/query", "/equipment/{id}/analysis", "/plant/status", "/plant/risk-ranking"],
    }


@app.post("/query")
def query(req: QueryRequest):
    """Main natural language query endpoint."""
    orch = get_orchestrator()
    return orch.process_query(req.query, req.equip_id)


@app.get("/equipment/{equip_id}/analysis")
def full_analysis(equip_id: str):
    """Run full analysis pipeline for one equipment."""
    if equip_id not in EQUIPMENT_REGISTRY:
        raise HTTPException(404, f"Equipment {equip_id} not found")
    orch = get_orchestrator()
    return orch.get_full_analysis(equip_id)


@app.get("/equipment/{equip_id}/sensors")
def latest_sensors(equip_id: str):
    return get_latest_readings(equip_id)


@app.get("/equipment/{equip_id}/health-trend")
def health_trend(equip_id: str, days: int = Query(30, ge=1, le=90)):
    df = get_health_trend(equip_id, days)
    return df.to_dict(orient="records")


@app.get("/equipment/{equip_id}/sensor-history/{sensor}")
def sensor_history(equip_id: str, sensor: str, days: int = Query(30, ge=1, le=90)):
    df = get_sensor_history(equip_id, sensor, days)
    return df.to_dict(orient="records")


@app.get("/equipment/{equip_id}/maintenance")
def maintenance_history(equip_id: str):
    return get_maintenance_history(equip_id)


@app.get("/equipment/{equip_id}/genome")
def equipment_genome(equip_id: str):
    orch = get_orchestrator()
    return orch.get_genome(equip_id)


@app.get("/equipment/{equip_id}/failure-events")
def failure_events(equip_id: str):
    return get_failure_events(equip_id)


@app.get("/equipment/{equip_id}/spares")
def spares(equip_id: str):
    return get_spares(equip_id)


@app.get("/plant/status")
def plant_status():
    """Health overview of all equipment."""
    health_data = get_all_latest_health()
    return {
        "equipment_health": health_data,
        "summary": {
            "critical": sum(1 for h in health_data if h.get("health_score", 100) < 40),
            "warning": sum(1 for h in health_data if 40 <= h.get("health_score", 100) < 70),
            "normal": sum(1 for h in health_data if h.get("health_score", 100) >= 70),
        },
    }


@app.get("/plant/risk-ranking")
def risk_ranking():
    """All equipment ranked by current risk score."""
    orch = get_orchestrator()
    return orch.get_plant_risk_ranking()


@app.get("/plant/maintenance-plan")
def maintenance_plan():
    """Optimized plant-wide maintenance plan."""
    orch = get_orchestrator()
    result = orch.process_query("Generate maintenance plan for all equipment")
    return result.get("maintenance_plan", [])


@app.post("/feedback")
def submit_feedback(req: FeedbackRequest):
    """Engineer feedback loop – improves future recommendations."""
    log_feedback(
        equip_id=req.equip_id,
        query=req.query,
        recommendation=req.recommendation,
        feedback_type=req.feedback_type,
        comment=req.comment,
        was_correct=req.was_correct,
    )
    return {"status": "recorded", "message": "Feedback logged. Thank you for improving MINERVA."}


@app.get("/equipment")
def list_equipment():
    return [
        {"equip_id": eid, **info}
        for eid, info in EQUIPMENT_REGISTRY.items()
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
