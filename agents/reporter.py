"""
MINERVA Reporter Agent
Generates structured maintenance reports in multiple formats:
  - Incident Report (triggered by critical alert)
  - Predictive Report (scheduled, equipment-specific)
  - Daily Plant Summary (plant-wide digest)
  - Counterfactual Post-Mortem (after a failure event)
"""
import json
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE, EQUIPMENT_REGISTRY


REPORT_TEMPLATES = {
    "incident": {
        "title": "Incident / Fault Report",
        "sections": ["equipment_summary", "fault_description", "sensor_evidence",
                     "root_cause_analysis", "immediate_actions", "spare_parts",
                     "sop_references", "follow_up_plan"],
    },
    "predictive": {
        "title": "Predictive Maintenance Report",
        "sections": ["equipment_summary", "health_trend", "rul_analysis",
                     "failure_horizon", "risk_assessment", "recommended_actions",
                     "spare_procurement", "monitoring_plan"],
    },
    "daily_summary": {
        "title": "Daily Plant Maintenance Summary",
        "sections": ["plant_overview", "critical_alerts", "scheduled_actions",
                     "completed_work", "upcoming_maintenance", "spare_status"],
    },
    "post_mortem": {
        "title": "Failure Post-Mortem & Counterfactual Analysis",
        "sections": ["failure_description", "timeline", "root_cause",
                     "counterfactual_analysis", "lessons_learned", "process_changes"],
    },
}

DEMO_REPORTS = {
    "RM-2_incident": {
        "report_id": "RPT-INC-20260608-RM2",
        "report_type": "Incident / Fault Report",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "generated_by": "MINERVA AI System",
        "equipment": {"id": "RM-2", "name": "Rolling Mill 2", "type": "Rolling Mill", "criticality": "Critical"},
        "executive_summary": (
            "Rolling Mill RM-2 is exhibiting advanced bearing degradation symptoms. "
            "Vibration RMS has reached 7.3 mm/s (critical threshold: 7.0 mm/s) with bearing "
            "temperature at 89°C (warning threshold: 75°C). Adversarial diagnosis council "
            "assigns 68% probability to outer race bearing damage. Estimated RUL: 8 days. "
            "Immediate intervention required within 48 hours to prevent catastrophic failure."
        ),
        "fault_description": {
            "primary_fault": "Outer Race Bearing Damage (BPFO at 3.2 kHz)",
            "confidence": 68,
            "health_score": 28,
            "risk_level": "CRITICAL",
            "risk_score": 84.2,
        },
        "sensor_evidence": [
            {"sensor": "vibration_rms", "current": 7.3, "normal_max": 4.5, "unit": "mm/s", "status": "critical", "trend": "rising_fast"},
            {"sensor": "temperature_bearing", "current": 89, "normal_max": 75, "unit": "°C", "status": "warning", "trend": "rising"},
            {"sensor": "motor_current", "current": 156, "normal_max": 140, "unit": "A", "status": "warning", "trend": "rising"},
        ],
        "root_cause": (
            "Root cause traces to lubrication interval extension from 200h to 300h approximately "
            "42 days ago. Insufficient lubrication caused micro-pitting on the bearing outer race, "
            "generating the characteristic BPFO frequency signature at 3.2 kHz. The degradation "
            "was detectable via spectral analysis 28 days ago but was below alert thresholds."
        ),
        "immediate_actions": [
            "Issue work permit for RM-2 bearing inspection (SOP-RM-042) — within 48 hours",
            "Pre-stage bearing SKF-6312-C3 (2 units in stock)",
            "Collect oil sample for same-day metallic particle analysis",
            "During teardown: inspect coupling alignment as secondary check",
            "Assign 3-person maintenance team (estimated 6–8 hours)",
        ],
        "long_term_actions": [
            "Revert lubrication interval to 200 hours (was extended to 300h)",
            "Add BPFO spectral monitoring to weekly vibration route",
            "Schedule alignment verification 30 days post-repair",
        ],
        "spare_parts": [
            {"code": "SKF-6312-C3", "description": "Deep Groove Ball Bearing", "qty_required": 2, "qty_stock": 2, "lead_time_days": 3, "status": "Available"},
            {"code": "SKF-NJ2316", "description": "Cylindrical Roller Bearing (backup)", "qty_required": 1, "qty_stock": 0, "lead_time_days": 7, "status": "Order required"},
        ],
        "sop_references": ["SOP-RM-042: Emergency Bearing Replacement", "SOP-GEN-001: Work Order Priority Classification"],
        "knowledge_citations": ["FR-2024-031: March 2024 RM-2 bearing failure (identical pattern)", "RM-MAN-001: Bearing inspection thresholds"],
        "rul_days": 8,
        "failure_probability_7d": 52.3,
    },
}


def generate_report(equip_id: str, report_type: str = "incident",
                    context: dict = None, council_result: dict = None,
                    rul_result: dict = None, risk_result: dict = None) -> dict:
    """Generate a structured maintenance report."""
    if context is None:
        from database.db_manager import build_equipment_context
        context = build_equipment_context(equip_id)

    if rul_result is None:
        from ml_engine.engine import RULPredictor
        rul_result = RULPredictor().estimate_rul(equip_id, context)

    if risk_result is None:
        from ml_engine.engine import RiskScorer
        risk_result = RiskScorer().compute_risk_score(equip_id, context, rul_result)

    if DEMO_MODE or not ANTHROPIC_API_KEY:
        key = f"{equip_id}_{report_type}"
        if key in DEMO_REPORTS:
            return DEMO_REPORTS[key]
        return _build_structured_report(equip_id, report_type, context, council_result, rul_result, risk_result)

    return _llm_report(equip_id, report_type, context, council_result, rul_result, risk_result)


def generate_daily_summary() -> dict:
    """Generate a plant-wide daily maintenance summary."""
    from database.db_manager import get_all_latest_health, get_all_maintenance_recent
    from agents.orchestrator import get_orchestrator

    orch = get_orchestrator()
    risk_ranking = orch.get_plant_risk_ranking()
    health_data = get_all_latest_health()
    recent_maintenance = get_all_maintenance_recent(days=7)

    critical = [r for r in risk_ranking if r.get("priority") == "CRITICAL"]
    high = [r for r in risk_ranking if r.get("priority") == "HIGH"]

    avg_health = sum(h.get("health_score", 80) for h in health_data) / max(len(health_data), 1)

    return {
        "report_id": f"RPT-DAILY-{datetime.now().strftime('%Y%m%d')}",
        "report_type": "Daily Plant Maintenance Summary",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "date": datetime.now().strftime("%d %B %Y"),
        "plant_health": {
            "average_health_score": round(avg_health, 1),
            "critical_equipment": len(critical),
            "high_risk_equipment": len(high),
            "normal_equipment": len([r for r in risk_ranking if r.get("priority") in ("LOW", "MEDIUM")]),
        },
        "critical_alerts": [
            {
                "equip_id": r["equip_id"],
                "equip_name": r["equip_name"],
                "health": r.get("health", 0),
                "rul_days": r.get("rul_days", 0),
                "urgency": r.get("urgency", ""),
                "risk_score": r.get("risk_score", 0),
            }
            for r in critical[:5]
        ],
        "high_priority_actions": [
            {
                "equip_id": r["equip_id"],
                "equip_name": r["equip_name"],
                "urgency": r.get("urgency", ""),
            }
            for r in high[:3]
        ],
        "recent_maintenance": recent_maintenance[:5],
        "risk_ranking": risk_ranking[:8],
    }


def _build_structured_report(equip_id, report_type, context, council_result, rul_result, risk_result) -> dict:
    """Build a structured report from available data without LLM."""
    equip_info = EQUIPMENT_REGISTRY.get(equip_id, {})
    anomalous = context.get("anomalous_sensors", [])
    history = context.get("maintenance_history", [])
    spares = context.get("spares_info", {})
    health = context.get("current_health", 80)
    rul = rul_result.get("estimated_rul_days", 60)
    risk_score = risk_result.get("risk_score", 0)
    priority = risk_result.get("priority", "LOW")

    verdict = (council_result or {}).get("verdict", {})
    immediate_actions = verdict.get("immediate_actions", [
        f"Inspect {equip_id} within {risk_result.get('urgency', 'scheduled timeframe')}",
        "Review sensor trend data with maintenance lead",
        "Check spare parts availability",
    ])

    report = {
        "report_id": f"RPT-{report_type.upper()[:3]}-{datetime.now().strftime('%Y%m%d%H%M')}-{equip_id}",
        "report_type": REPORT_TEMPLATES.get(report_type, {}).get("title", "Maintenance Report"),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "generated_by": "MINERVA AI System (Demo Mode)",
        "equipment": {
            "id": equip_id,
            "name": equip_info.get("name", equip_id),
            "type": equip_info.get("type", ""),
            "criticality": equip_info.get("criticality", "medium").title(),
        },
        "executive_summary": (
            f"{equip_info.get('name', equip_id)} is currently at {health:.0f}% health "
            f"with {len(anomalous)} sensor(s) in abnormal state. "
            f"Estimated remaining useful life: {rul:.0f} days. "
            f"Risk level: {priority}. Risk score: {risk_score:.1f}/100."
        ),
        "health_summary": {
            "health_score": health,
            "risk_level": priority,
            "risk_score": risk_score,
            "rul_days": rul,
            "failure_probability_7d": rul_result.get("failure_probability_7d", 0),
            "failure_probability_30d": rul_result.get("failure_probability_30d", 0),
        },
        "anomalous_sensors": anomalous,
        "diagnosis": verdict.get("final_diagnosis", "Analysis pending"),
        "root_cause": (council_result or {}).get("archaeology", {}).get("root_cause_summary", "Sensor data analysis required"),
        "immediate_actions": immediate_actions,
        "long_term_actions": verdict.get("long_term_actions", []),
        "spare_parts_status": spares,
        "sop_references": verdict.get("sop_references", ["SOP-GEN-001"]),
        "knowledge_citations": verdict.get("knowledge_base_citations", []),
        "maintenance_history_summary": history[:3],
        "rul_analysis": rul_result,
        "risk_analysis": risk_result,
    }
    return report


def _llm_report(equip_id, report_type, context, council_result, rul_result, risk_result) -> dict:
    """LLM-enhanced report generation."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    base = _build_structured_report(equip_id, report_type, context, council_result, rul_result, risk_result)

    prompt = f"""You are MINERVA, an industrial AI maintenance expert.
Generate a professional {base['report_type']} for {base['equipment']['name']}.

Data: {json.dumps({
    'health': base['health_summary'],
    'anomalous_sensors': base['anomalous_sensors'],
    'diagnosis': base['diagnosis'],
    'immediate_actions': base['immediate_actions'],
}, indent=2)}

Write a concise executive summary (2-3 sentences) and a root cause analysis (3-4 sentences).
Respond in JSON: {{"executive_summary": "...", "root_cause_analysis": "..."}}"""

    resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=400,
                                   messages=[{"role": "user", "content": prompt}])
    text = resp.content[0].text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        enriched = json.loads(text)
        base["executive_summary"] = enriched.get("executive_summary", base["executive_summary"])
        base["root_cause"] = enriched.get("root_cause_analysis", base["root_cause"])
    except Exception:
        pass
    return base


def format_report_markdown(report: dict) -> str:
    """Convert a report dict to readable markdown."""
    lines = []
    lines.append(f"# {report.get('report_type', 'Maintenance Report')}")
    lines.append(f"**Report ID:** {report.get('report_id', 'N/A')}  ")
    lines.append(f"**Generated:** {report.get('generated_at', 'N/A')}  ")
    lines.append(f"**Equipment:** {report.get('equipment', {}).get('name', 'N/A')} ({report.get('equipment', {}).get('id', '')})")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append(report.get("executive_summary", "N/A"))
    lines.append("")
    h = report.get("health_summary", {})
    lines.append("## Health & Risk Summary")
    lines.append(f"- **Health Score:** {h.get('health_score', 'N/A')}%")
    lines.append(f"- **Risk Level:** {h.get('risk_level', 'N/A')} ({h.get('risk_score', 0):.1f}/100)")
    lines.append(f"- **Est. RUL:** {h.get('rul_days', 'N/A')} days")
    lines.append(f"- **P(failure 7d):** {h.get('failure_probability_7d', 0):.1f}%")
    lines.append(f"- **P(failure 30d):** {h.get('failure_probability_30d', 0):.1f}%")
    lines.append("")
    lines.append("## Root Cause Analysis")
    lines.append(report.get("root_cause", report.get("fault_description", {}).get("primary_fault", "N/A")))
    lines.append("")
    actions = report.get("immediate_actions", [])
    if actions:
        lines.append("## Immediate Actions Required")
        for a in actions:
            lines.append(f"1. {a}")
    lines.append("")
    lt = report.get("long_term_actions", [])
    if lt:
        lines.append("## Long-Term Recommendations")
        for a in lt:
            lines.append(f"- {a}")
    lines.append("")
    sops = report.get("sop_references", [])
    if sops:
        lines.append("## SOP References")
        for s in sops:
            lines.append(f"- {s}")
    return "\n".join(lines)
