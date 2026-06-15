"""
MINERVA Orchestrator
The central reasoning hub. Classifies queries, coordinates agents,
and assembles the final structured response.
"""
import json
import uuid
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE, EQUIPMENT_REGISTRY

# ── DEMO mode general QA responses ───────────────────────────────────────────
DEMO_QA = {
    "default": {
        "answer": (
            "MINERVA has analyzed the plant data. "
            "Currently, RM-2 (Rolling Mill 2) is the highest-priority concern with critical bearing vibration at 7.3 mm/s. "
            "CB-2 and BF-1 are in warning state. HYD-1, COMP-1, OHC-1, and CCM-1 are operating normally. "
            "Use the sidebar to select a specific equipment for detailed diagnosis."
        ),
        "sources": ["Plant health dashboard", "Real-time sensor data"],
    }
}


class MINERVAOrchestrator:
    """
    Central orchestrator that:
    1. Classifies query intent
    2. Gathers equipment context from DB
    3. Routes to appropriate specialist agents
    4. Assembles and returns structured output
    """

    def __init__(self):
        from database.db_manager import build_equipment_context, get_all_latest_health
        from knowledge_base.vector_store import query_knowledge_base
        from ml_engine.engine import AnomalyDetector, RULPredictor, RiskScorer, EquipmentGenome
        from agents.adversarial_council import run_adversarial_council
        from agents.archaeologist import run_archaeology

        self._build_context = build_equipment_context
        self._get_all_health = get_all_latest_health
        self._query_kb = query_knowledge_base
        self._council = run_adversarial_council
        self._archaeologist = run_archaeology

        self.rul_predictor = RULPredictor()
        self.risk_scorer = RiskScorer()
        # Genome fitted lazily on first use
        self._genome: EquipmentGenome | None = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def process_query(self, query: str, equip_id: str = None) -> dict:
        """Main entry point. Returns full structured response."""
        session_id = str(uuid.uuid4())[:8]

        # Auto-detect equipment from query if not supplied
        if not equip_id:
            equip_id = self._detect_equipment(query)

        intent = self._classify_intent(query)

        if equip_id and equip_id in EQUIPMENT_REGISTRY:
            context = self._build_context(equip_id)
        else:
            context = {}

        result = {"session_id": session_id, "intent": intent,
                  "equip_id": equip_id, "query": query, "timestamp": datetime.now().isoformat()}

        if intent == "diagnosis" and equip_id:
            result.update(self._full_diagnosis(equip_id, context, query))
        elif intent == "prediction" and equip_id:
            result.update(self._failure_horizon(equip_id, context))
        elif intent == "planning":
            result.update(self._maintenance_plan())
        elif intent == "reporting" and equip_id:
            result.update(self._generate_report(equip_id, context))
        elif intent == "fleet_status":
            result.update(self._fleet_status())
        else:
            result.update(self._general_qa(query, equip_id, context))

        # Log session
        try:
            from database.db_manager import log_agent_session
            log_agent_session(
                session_id=session_id, equip_id=equip_id or "PLANT",
                query=query,
                hypothesis=json.dumps(result.get("council", {}).get("hypothesis", {}))[:500],
                skeptic=json.dumps(result.get("council", {}).get("skeptic", {}))[:500],
                verdict=json.dumps(result.get("council", {}).get("verdict", {}))[:500],
                archaeology=json.dumps(result.get("archaeology", {}))[:500],
                risk_score=float(result.get("risk", {}).get("risk_score", 0)),
                rul_days=float(result.get("rul", {}).get("estimated_rul_days", 0)),
                actions=json.dumps(result.get("council", {}).get("verdict", {}).get("immediate_actions", []))[:300],
            )
        except Exception:
            pass

        return result

    def get_full_analysis(self, equip_id: str) -> dict:
        """Run complete analysis: council + archaeology + RUL + risk."""
        if equip_id not in EQUIPMENT_REGISTRY:
            return {"error": f"Unknown equipment: {equip_id}"}
        context = self._build_context(equip_id)
        return self._full_diagnosis(equip_id, context, f"Full analysis of {equip_id}")

    def get_plant_risk_ranking(self) -> list[dict]:
        """Return all equipment ranked by risk score."""
        results = []
        for equip_id in EQUIPMENT_REGISTRY:
            try:
                context = self._build_context(equip_id)
                rul = self.rul_predictor.estimate_rul(equip_id, context)
                risk = self.risk_scorer.compute_risk_score(equip_id, context, rul)
                results.append({
                    "equip_id": equip_id,
                    "equip_name": EQUIPMENT_REGISTRY[equip_id]["name"],
                    "health": context.get("current_health", 80),
                    "risk_score": risk["risk_score"],
                    "priority": risk["priority"],
                    "urgency": risk["urgency"],
                    "rul_days": rul["estimated_rul_days"],
                    "anomalous_count": len(context.get("anomalous_sensors", [])),
                })
            except Exception as e:
                results.append({"equip_id": equip_id, "error": str(e), "risk_score": 0})

        results.sort(key=lambda x: x.get("risk_score", 0), reverse=True)
        return results

    def get_genome(self, equip_id: str) -> dict:
        """Return Equipment Genome data for visualization."""
        if self._genome is None:
            self._fit_genome()
        if self._genome is None:
            return {"error": "Genome not available"}
        return {
            "genome": self._genome.get_genome(equip_id),
            "similar_equipment": self._genome.find_similar_equipment(equip_id, top_k=3),
            "degradation_direction": self._genome.compute_degradation_direction(equip_id),
        }

    # ── Private helpers ────────────────────────────────────────────────────────

    def _full_diagnosis(self, equip_id: str, context: dict, query: str) -> dict:
        """Run council + archaeology + RUL + risk."""
        equip_type = context.get("equip_type", "")
        kb_results = self._query_kb(query, equip_type=equip_type, n_results=4)
        council = self._council(equip_id, context, kb_results)
        archaeology = self._archaeologist(equip_id, context)
        rul = self.rul_predictor.estimate_rul(equip_id, context)
        risk = self.risk_scorer.compute_risk_score(equip_id, context, rul)
        spares = context.get("spares_info", {})

        return {
            "council": council,
            "archaeology": archaeology,
            "rul": rul,
            "risk": risk,
            "spares": spares,
            "context_summary": {
                "health": context.get("current_health"),
                "anomalous_sensors": len(context.get("anomalous_sensors", [])),
                "maintenance_events": len(context.get("maintenance_history", [])),
                "kb_documents_used": len(kb_results),
            },
            "kb_results": kb_results,
        }

    def _failure_horizon(self, equip_id: str, context: dict) -> dict:
        rul = self.rul_predictor.estimate_rul(equip_id, context)
        risk = self.risk_scorer.compute_risk_score(equip_id, context, rul)
        return {"rul": rul, "risk": risk}

    def _maintenance_plan(self) -> dict:
        ranking = self.get_plant_risk_ranking()
        plan = []
        for item in ranking:
            if item.get("risk_score", 0) > 20:
                plan.append({
                    "equip_id": item["equip_id"],
                    "equip_name": item["equip_name"],
                    "priority": item.get("priority", "LOW"),
                    "urgency": item.get("urgency", ""),
                    "rul_days": item.get("rul_days", 90),
                    "risk_score": item.get("risk_score", 0),
                })
        return {"maintenance_plan": plan, "generated_at": datetime.now().isoformat()}

    def _generate_report(self, equip_id: str, context: dict) -> dict:
        """Generate a structured maintenance report."""
        rul = self.rul_predictor.estimate_rul(equip_id, context)
        risk = self.risk_scorer.compute_risk_score(equip_id, context, rul)
        equip_name = context.get("equip_name", equip_id)
        health = context.get("current_health", 80)
        anomalous = context.get("anomalous_sensors", [])
        history = context.get("maintenance_history", [])
        spares = context.get("spares_info", {})

        report = {
            "report_id": f"RPT-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "generated_at": datetime.now().isoformat(),
            "equipment": {"id": equip_id, "name": equip_name},
            "summary": {
                "health_score": health,
                "risk_level": risk["priority"],
                "risk_score": risk["risk_score"],
                "estimated_rul_days": rul["estimated_rul_days"],
                "anomalous_sensors": len(anomalous),
            },
            "sensor_alerts": anomalous,
            "rul_analysis": rul,
            "risk_analysis": risk,
            "maintenance_history_summary": history[:3],
            "spare_parts_status": spares,
            "recommended_actions": risk["urgency"],
        }
        return {"report": report}

    def _fleet_status(self) -> dict:
        health_data = self._get_all_health()
        return {
            "fleet_status": health_data,
            "risk_ranking": self.get_plant_risk_ranking(),
            "summary": {
                "critical_count": sum(1 for h in health_data if h.get("health_score", 100) < 40),
                "warning_count": sum(1 for h in health_data if 40 <= h.get("health_score", 100) < 70),
                "normal_count": sum(1 for h in health_data if h.get("health_score", 100) >= 70),
            },
        }

    def _general_qa(self, query: str, equip_id: str, context: dict) -> dict:
        """Answer general maintenance queries using KB + LLM."""
        kb_results = self._query_kb(query, n_results=3)

        if DEMO_MODE or not ANTHROPIC_API_KEY:
            return {
                "answer": DEMO_QA["default"]["answer"],
                "sources": DEMO_QA["default"]["sources"],
                "kb_results": kb_results,
            }

        import anthropic
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        kb_text = "\n---\n".join(r.get("content", "")[:300] for r in kb_results[:3])
        ctx_str = json.dumps({
            "equipment": equip_id,
            "health": context.get("current_health"),
            "anomalous": context.get("anomalous_sensors", [])[:3],
        }, indent=2) if context else "{}"

        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=600,
            messages=[{"role": "user", "content": (
                f"You are MINERVA, a steel plant maintenance AI. "
                f"Equipment context: {ctx_str}\n"
                f"Knowledge base: {kb_text}\n"
                f"Question: {query}\n"
                f"Provide a concise, expert maintenance answer citing the knowledge base where relevant."
            )}],
        )
        return {
            "answer": response.content[0].text,
            "sources": [r["id"] for r in kb_results],
            "kb_results": kb_results,
        }

    def _classify_intent(self, query: str) -> str:
        q = query.lower()
        if any(w in q for w in ["what's wrong", "what is wrong", "diagnose", "fault", "issue",
                                  "problem", "why", "cause", "failure", "broken", "anomaly",
                                  "alert", "alarm", "abnormal", "vibration", "temperature",
                                  "bearing", "analyse", "analyze", "inspect", "check"]):
            return "diagnosis"
        if any(w in q for w in ["when", "predict", "rul", "remaining", "horizon", "fail",
                                  "probability", "how long", "days left", "life"]):
            return "prediction"
        if any(w in q for w in ["plan", "schedule", "priority", "maintenance plan",
                                  "which equipment", "next maintenance", "upcoming"]):
            return "planning"
        if any(w in q for w in ["report", "summary", "generate report"]):
            return "reporting"
        if any(w in q for w in ["status", "overview", "all equipment", "plant",
                                  "fleet", "dashboard", "health"]):
            return "fleet_status"
        # If an equipment ID is mentioned with no other clear intent, assume diagnosis
        q_upper = query.upper()
        for eid in EQUIPMENT_REGISTRY:
            if eid in q_upper:
                return "diagnosis"
        return "general_qa"

    def _detect_equipment(self, query: str) -> str | None:
        q = query.upper()
        for eid in EQUIPMENT_REGISTRY:
            if eid in q:
                return eid
        # Fuzzy match on equipment names
        q_lower = query.lower()
        name_map = {info["name"].lower(): eid for eid, info in EQUIPMENT_REGISTRY.items()}
        for name, eid in name_map.items():
            if any(word in q_lower for word in name.split() if len(word) > 3):
                return eid
        return None

    def _fit_genome(self):
        """Lazy-fit equipment genome."""
        try:
            import pandas as pd
            import sqlite3
            from config import DB_PATH
            from ml_engine.engine import EquipmentGenome
            conn = sqlite3.connect(DB_PATH)
            df = pd.read_sql_query("SELECT * FROM sensor_readings", conn)
            conn.close()
            self._genome = EquipmentGenome()
            self._genome.fit(df)
        except Exception as e:
            print(f"Genome fitting failed: {e}")
            self._genome = None


# Singleton instance
_orchestrator = None

def get_orchestrator() -> MINERVAOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MINERVAOrchestrator()
    return _orchestrator
