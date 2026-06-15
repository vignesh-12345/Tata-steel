"""
MINERVA Archaeologist Agent
NOVEL COMPONENT: Temporal backward reasoning.
Instead of asking "what will fail?", it asks "how did we get here?"
Reconstructs the causal chain that led to the current anomalous state.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE, SENSOR_BASELINES


# ── Pre-baked archaeology for demo mode ──────────────────────────────────────
DEMO_ARCHAEOLOGY = {
    "RM-2": {
        "causal_chain": [
            {"day": -42, "event": "Lubrication interval extended from 200h to 300h due to maintenance backlog", "sensor": "oil_pressure", "significance": "ROOT CAUSE – initiated bearing starvation"},
            {"day": -28, "event": "Vibration baseline shift: 2.8 → 3.4 mm/s. Below alert threshold, no action taken", "sensor": "vibration_rms", "significance": "EARLY INDICATOR – bearing surface fatigue beginning"},
            {"day": -19, "event": "BPFO frequency component appeared in spectrum at 3.2 kHz during routine check", "sensor": "vibration_rms", "significance": "DEFINITIVE INDICATOR – outer race damage confirmed"},
            {"day": -12, "event": "Bearing temperature rose 8°C above baseline. Maintenance note: 'monitoring'", "sensor": "temperature_bearing", "significance": "ESCALATION – thermal damage accelerating wear"},
            {"day": -7,  "event": "Vibration crossed 5.1 mm/s warning threshold. Alert generated.", "sensor": "vibration_rms", "significance": "LATE WARNING – damage well established"},
            {"day": -3,  "event": "Motor current increased 12% above baseline – mechanical loading from damaged bearing", "sensor": "motor_current", "significance": "SECONDARY EFFECT – bearing drag on motor"},
            {"day": 0,   "event": "Current state: vibration 7.3 mm/s (critical), temperature 89°C (warning). Failure imminent", "sensor": "vibration_rms", "significance": "CRITICAL – intervention required within 48 hours"},
        ],
        "root_cause_summary": "Root cause traces to lubrication interval extension 42 days ago. Bearing oil film breakdown led to micro-pitting on outer race, generating characteristic BPFO vibration signature. The degradation was detectable 28 days ago but below alert thresholds. Current state represents advanced outer race damage.",
        "missed_intervention_window": "Optimal intervention window was Day -19 when BPFO signature first appeared. At that stage, bearing replacement could have been planned during next scheduled downtime, avoiding emergency shutdown.",
        "timeline_days": [-42, -28, -19, -12, -7, -3, 0],
    },
    "CB-2": {
        "causal_chain": [
            {"day": -55, "event": "Belt tension adjustment skipped at scheduled PM due to time constraints", "sensor": "belt_tension", "significance": "ROOT CAUSE – belt drift began"},
            {"day": -40, "event": "Intermittent alignment deviation spikes noted in log – marked as 'transient'", "sensor": "alignment_deviation", "significance": "EARLY INDICATOR – ignored as noise"},
            {"day": -25, "event": "Motor current spikes (15% above baseline) correlating with alignment events", "sensor": "motor_current", "significance": "ESCALATION – mechanical stress increasing"},
            {"day": 0,   "event": "Current: 55% health. Intermittent 3mm alignment deviation causing belt edge wear", "sensor": "alignment_deviation", "significance": "WARNING – belt life reducing"},
        ],
        "root_cause_summary": "Missed belt tension adjustment led to gradual misalignment. Early spikes were dismissed as transient. Belt edge wear accumulating.",
        "missed_intervention_window": "Day -40 was the optimal window – belt tracking adjustment at that point would have been a 30-minute repair.",
        "timeline_days": [-55, -40, -25, 0],
    },
}


def run_archaeology(equip_id: str, context: dict) -> dict:
    """
    Run the temporal archaeology engine.
    Uses LLM to generate causal timeline narrative from sensor history.
    Falls back to demo data if DEMO_MODE or API unavailable.
    """
    from database.db_manager import get_sensor_history, get_maintenance_history

    # Build sensor trend evidence
    anomalous = context.get("anomalous_sensors", [])
    trends = context.get("sensor_trends_7d", {})
    history = context.get("maintenance_history", [])
    equip_name = context.get("equip_name", equip_id)
    equip_type = context.get("equip_type", "unknown")

    # Get detailed time-series for anomalous sensors
    sensor_timelines = {}
    for s_info in anomalous[:3]:  # Top 3 anomalous sensors
        sensor = s_info.get("sensor", "")
        if sensor:
            df = get_sensor_history(equip_id, sensor, days=60)
            if len(df) > 0:
                sensor_timelines[sensor] = {
                    "first_date": df["date"].iloc[0],
                    "last_date": df["date"].iloc[-1],
                    "first_val": round(float(df["value"].iloc[0]), 3),
                    "last_val": round(float(df["value"].iloc[-1]), 3),
                    "pct_change": round((df["value"].iloc[-1] - df["value"].iloc[0]) /
                                       (abs(df["value"].iloc[0]) + 1e-9) * 100, 1),
                    "days_in_warning": int((df["status"] == "warning").sum()),
                    "days_in_critical": int((df["status"] == "critical").sum()),
                }

    if DEMO_MODE or not ANTHROPIC_API_KEY:
        return _demo_archaeology(equip_id, sensor_timelines, history)

    return _llm_archaeology(equip_id, equip_name, equip_type,
                             anomalous, sensor_timelines, trends, history)


def _demo_archaeology(equip_id: str, sensor_timelines: dict, history: list) -> dict:
    """Return pre-baked archaeology for demo mode."""
    demo = DEMO_ARCHAEOLOGY.get(equip_id, {
        "causal_chain": [
            {"day": -30, "event": "Gradual parameter drift noted in sensor data",
             "sensor": "vibration_rms", "significance": "EARLY INDICATOR"},
            {"day": 0, "event": "Current anomalous state",
             "sensor": "vibration_rms", "significance": "CURRENT"},
        ],
        "root_cause_summary": f"Sensor data for {equip_id} shows degradation trend. Full analysis available with API key.",
        "missed_intervention_window": "Analysis requires historical sensor data.",
        "timeline_days": [-30, 0],
    })

    return {
        "equip_id": equip_id,
        "causal_chain": demo["causal_chain"],
        "root_cause_summary": demo["root_cause_summary"],
        "missed_intervention_window": demo["missed_intervention_window"],
        "sensor_timelines": sensor_timelines,
        "maintenance_correlations": _find_maintenance_correlations(history),
        "earliest_detectable_day": min(demo["timeline_days"]),
        "analysis_depth_days": 60,
    }


def _llm_archaeology(equip_id, equip_name, equip_type,
                      anomalous, sensor_timelines, trends, history) -> dict:
    """Use Claude API for deep temporal archaeology."""
    import anthropic

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    context_str = f"""
EQUIPMENT: {equip_name} ({equip_id}) | Type: {equip_type}

CURRENT ANOMALOUS SENSORS:
{json.dumps(anomalous, indent=2)}

SENSOR TRENDS (60-day history):
{json.dumps(sensor_timelines, indent=2)}

7-DAY SLOPE PER SENSOR:
{json.dumps(trends, indent=2)}

RECENT MAINTENANCE EVENTS:
{json.dumps(history, indent=2)}
"""

    prompt = f"""You are the MINERVA Temporal Archaeology Engine.
Your unique role: trace BACKWARD from the current anomalous state to find the ROOT CAUSE and complete causal chain.

{context_str}

Perform a temporal archaeology analysis. Reconstruct the sequence of events that led to the current state.

Respond in this exact JSON format:
{{
  "causal_chain": [
    {{"day": -N, "event": "what happened N days ago", "sensor": "sensor_name", "significance": "ROOT CAUSE|EARLY INDICATOR|ESCALATION|WARNING|CURRENT"}}
  ],
  "root_cause_summary": "one paragraph explaining the root cause and how it progressed",
  "missed_intervention_window": "when was the optimal intervention point and what action was needed",
  "earliest_detectable_day": -N
}}

Be specific about sensor values, dates, and causal mechanisms. Trace at least 4 events in the chain."""

    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1200,
        messages=[{"role": "user", "content": prompt}],
    )

    text = response.content[0].text
    # Strip markdown fences if present
    text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = {
            "causal_chain": [{"day": 0, "event": text[:300], "sensor": "multiple", "significance": "CURRENT"}],
            "root_cause_summary": text[:500],
            "missed_intervention_window": "See root cause summary",
            "earliest_detectable_day": -30,
        }

    result["equip_id"] = equip_id
    result["sensor_timelines"] = sensor_timelines
    result["maintenance_correlations"] = _find_maintenance_correlations(history)
    result["analysis_depth_days"] = 60
    return result


def _find_maintenance_correlations(history: list) -> list:
    """Find maintenance events that may have triggered or missed the current issue."""
    correlations = []
    for mh in history:
        # Look for maintenance events within 60 days that may be relevant
        finding = mh.get("finding", "").lower()
        if any(kw in finding for kw in ["vibration", "noise", "temperature", "wear", "leak",
                                         "monitoring", "trending", "noted", "observed"]):
            correlations.append({
                "date": mh.get("maintenance_date"),
                "type": mh.get("type"),
                "action": mh.get("action"),
                "finding": mh.get("finding"),
                "missed_escalation": "monitoring" in finding or "trending" in finding,
            })
    return correlations
