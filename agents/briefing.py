"""
MINERVA Briefing Intelligence
Engineer-perspective features: what matters RIGHT NOW, why, and what to do.

Four capabilities:
  1. Shift Briefing    — plain-English summary of today's priorities
  2. Pattern Matching  — links current failure to historical incidents
  3. Business Case     — planned cost vs failure cost, ROI for management approval
  4. Shift Handover    — end-of-shift summary for the next team
"""
from datetime import datetime, timedelta
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EQUIPMENT_REGISTRY


# ── 1. SHIFT BRIEFING ─────────────────────────────────────────────────────────
def generate_shift_briefing() -> dict:
    """
    Generate a plain-English shift briefing from current plant state.
    An engineer should be able to act on this in under 30 seconds.
    """
    from database.db_manager import get_all_latest_health, build_equipment_context
    from ml_engine.engine import RULPredictor, RiskScorer

    rul_pred  = RULPredictor()
    risk_scor = RiskScorer()
    health_map = {h["equip_id"]: h["health_score"]
                  for h in get_all_latest_health()}

    items = []
    for eid in EQUIPMENT_REGISTRY:
        try:
            ctx  = build_equipment_context(eid)
            rul  = rul_pred.estimate_rul(eid, ctx)
            risk = risk_scor.compute_risk_score(eid, ctx, rul)
            items.append({
                "equip_id":    eid,
                "equip_name":  EQUIPMENT_REGISTRY[eid]["name"],
                "health":      health_map.get(eid, 80),
                "rul_days":    rul.get("estimated_rul_days", 90),
                "risk_score":  risk.get("risk_score", 0),
                "priority":    risk.get("priority", "LOW"),
                "urgency":     risk.get("urgency", ""),
                "anomalous":   ctx.get("anomalous_sensors", []),
                "p7":          rul.get("failure_probability_7d", 0),
            })
        except Exception:
            pass

    items.sort(key=lambda x: x["risk_score"], reverse=True)
    top = items[:3]

    # Build plain-English priorities
    priorities = []
    for item in top:
        if item["risk_score"] < 20:
            continue
        n_anom = len(item["anomalous"])
        anom_str = ""
        if item["anomalous"]:
            worst = sorted(item["anomalous"],
                           key=lambda s: 0 if s.get("status") == "critical" else 1)
            anom_str = f" — {worst[0].get('sensor','').replace('_',' ')} in {worst[0].get('status','warning')} state"

        if item["rul_days"] <= 7:
            urgency_plain = f"⛔ Failure possible within {item['rul_days']:.0f} days"
        elif item["rul_days"] <= 21:
            urgency_plain = f"⚠️ Needs attention within {item['rul_days']:.0f} days"
        else:
            urgency_plain = f"📋 Monitor — {item['rul_days']:.0f} days estimated remaining"

        priorities.append({
            "equip_id":    item["equip_id"],
            "equip_name":  item["equip_name"],
            "headline":    urgency_plain,
            "detail":      anom_str.strip(" —"),
            "rul_days":    item["rul_days"],
            "priority":    item["priority"],
            "risk_score":  item["risk_score"],
        })

    top1 = priorities[0] if priorities else None

    # Parts readiness for top item
    parts_msg = ""
    if top1:
        from database.db_manager import get_spare_availability
        spares = get_spare_availability(top1["equip_id"])
        if spares.get("critical_shortage"):
            parts_msg = f"⚠️ Parts gap: {', '.join(s['description'] for s in spares['critical_shortage'])} — order immediately (up to {spares['max_lead_time_days']}d lead time)"
        elif spares.get("total_parts", 0) > 0:
            parts_msg = f"✅ Required parts available in stores — maintenance can start today"

    hour = datetime.now().hour
    greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"

    return {
        "greeting":    greeting,
        "timestamp":   datetime.now().strftime("%d %b %Y, %H:%M"),
        "priorities":  priorities[:3],
        "top_item":    top1,
        "parts_msg":   parts_msg,
        "all_items":   items,
    }


# ── 2. PATTERN MATCHING ───────────────────────────────────────────────────────
# Historical incident library — what we've seen before and what happened
INCIDENT_LIBRARY = [
    {
        "incident_id":   "INC-2024-031",
        "date":          "March 2024",
        "equip_id":      "RM-2",
        "equip_type":    "rolling_mill",
        "failure_mode":  "Outer Race Bearing Damage",
        "trigger_pattern": {
            "vibration_rms":      {"min": 6.0, "direction": "rising", "rate": "fast"},
            "temperature_bearing":{"min": 80,  "direction": "rising"},
        },
        "days_to_failure_at_match": 11,
        "what_happened": "Vibration reached 6.8 mm/s with BPFO spectral signature. Outer race damage confirmed on teardown. Root cause: lubrication interval extended without approval.",
        "what_we_did":   "Emergency bearing replacement per SOP-RM-042. SKF-6312-C3 installed. Alignment also checked and corrected (was 0.08 mm out of spec).",
        "total_downtime_hours": 18,
        "total_cost_inr_lakhs": 22.0,
        "lesson": "Revert lubrication to 200h interval. Add BPFO spectral alert at 3.2 kHz.",
        "outcome": "No recurrence in 8 months with revised schedule.",
    },
    {
        "incident_id":   "INC-2023-087",
        "date":          "November 2023",
        "equip_id":      "OHC-1",
        "equip_type":    "crane",
        "failure_mode":  "Brake Pad Glazing",
        "trigger_pattern": {
            "brake_temp": {"min": 70, "direction": "rising", "rate": "slow"},
        },
        "days_to_failure_at_match": 5,
        "what_happened": "Brake temperature rose 18°C over 5 days. No alert was triggered (threshold was set too high). Pad glazed during a heavy lift — load dropped safely but inspection required.",
        "what_we_did":   "Emergency shutdown, brake pad replacement. Threshold revised from 90°C to 70°C.",
        "total_downtime_hours": 6,
        "total_cost_inr_lakhs": 8.5,
        "lesson": "Lower brake temperature alert to 70°C. Add daily brake inspection on high-utilisation cranes.",
        "outcome": "New threshold has since caught 2 early warnings — both resolved in planned downtime.",
    },
    {
        "incident_id":   "INC-2023-041",
        "date":          "June 2023",
        "equip_id":      "CCM-1",
        "equip_type":    "caster",
        "failure_mode":  "Oscillation Mechanism Seizure",
        "trigger_pattern": {
            "oscillation_freq": {"max": 110, "direction": "falling"},
            "vibration_rms":    {"min": 5.0, "direction": "rising"},
        },
        "days_to_failure_at_match": 7,
        "what_happened": "Oscillation frequency drifted 12% over 10 days. Vibration increased simultaneously. Cam follower seized during casting, causing emergency stop.",
        "what_we_did":   "14-hour corrective maintenance. Cam follower and eccentric pin replaced. Alignment re-done.",
        "total_downtime_hours": 14,
        "total_cost_inr_lakhs": 22.0,
        "lesson": "Add oscillation frequency ±8% drift alert. Include mechanism check in 500h PM.",
        "outcome": "Mechanism now on predictive maintenance schedule with monthly frequency checks.",
    },
    {
        "incident_id":   "INC-2024-019",
        "date":          "February 2024",
        "equip_id":      "BF-1",
        "equip_type":    "blast_furnace",
        "failure_mode":  "Cooling Circuit Blockage",
        "trigger_pattern": {
            "flow_rate_gas":       {"max": 3500, "direction": "falling"},
            "temperature_cooling": {"min": 48,   "direction": "rising"},
        },
        "days_to_failure_at_match": 18,
        "what_happened": "Flow rate declined 20% over 3 weeks. Scale deposits progressively blocked cooling circuit. Furnace shell temperature rose dangerously — emergency shutdown triggered.",
        "what_we_did":   "Chemical descaling per SOP-BF-015. 8-hour circuit isolation and flush. Scale removed, flow restored.",
        "total_downtime_hours": 12,
        "total_cost_inr_lakhs": 18.5,
        "lesson": "Annual chemical cleaning is insufficient. Move to 6-monthly. Add flow rate trending alert at -10% baseline.",
        "outcome": "Second cleaning scheduled. Flow rate alert now active.",
    },
]


def find_pattern_matches(equip_id: str, context: dict) -> list:
    """
    Compare current sensor state against the incident library.
    Returns matching incidents with similarity score and key insight.
    """
    equip_type = EQUIPMENT_REGISTRY.get(equip_id, {}).get("type", "")
    anomalous  = {r["sensor"]: r for r in context.get("anomalous_sensors", [])}
    trends     = context.get("sensor_trends_7d", {})
    health     = context.get("current_health", 80)

    matches = []
    for incident in INCIDENT_LIBRARY:
        score = 0
        reasons = []

        # Same equipment type
        if incident.get("equip_type") == equip_type:
            score += 30
            reasons.append("Same equipment type")

        # Same equipment (strongest match)
        if incident.get("equip_id") == equip_id:
            score += 25
            reasons.append(f"Same equipment ({equip_id})")

        # Sensor pattern matching
        trigger = incident.get("trigger_pattern", {})
        for sensor, criteria in trigger.items():
            if sensor in anomalous:
                val = float(anomalous[sensor].get("value", 0))
                if "min" in criteria and val >= criteria["min"]:
                    score += 20
                    reasons.append(f"{sensor.replace('_',' ')} matches trigger threshold")
                if "max" in criteria and val <= criteria["max"]:
                    score += 20
                    reasons.append(f"{sensor.replace('_',' ')} below normal (matches pattern)")

            # Trend direction match
            if sensor in trends:
                slope = trends[sensor]
                if criteria.get("direction") == "rising" and slope > 0.1:
                    score += 15
                    reasons.append(f"{sensor.replace('_',' ')} rising trend matches")
                elif criteria.get("direction") == "falling" and slope < -0.1:
                    score += 15
                    reasons.append(f"{sensor.replace('_',' ')} falling trend matches")

        # Health score similarity
        if health < 45 and incident.get("days_to_failure_at_match", 99) <= 14:
            score += 10
            reasons.append("Critical health score similar to pre-failure state")

        if score >= 35:
            matches.append({
                "incident_id":   incident["incident_id"],
                "date":          incident["date"],
                "equip_id":      incident["equip_id"],
                "equip_name":    EQUIPMENT_REGISTRY.get(incident["equip_id"], {}).get("name", ""),
                "failure_mode":  incident["failure_mode"],
                "match_score":   min(score, 100),
                "match_reasons": reasons[:3],
                "days_to_failure_at_match": incident["days_to_failure_at_match"],
                "what_happened": incident["what_happened"],
                "what_we_did":   incident["what_we_did"],
                "total_downtime_hours": incident["total_downtime_hours"],
                "total_cost_inr_lakhs": incident["total_cost_inr_lakhs"],
                "lesson":        incident["lesson"],
                "outcome":       incident["outcome"],
            })

    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches[:2]


# ── 3. BUSINESS CASE ──────────────────────────────────────────────────────────
# Production loss per hour (₹ lakhs) per equipment type
PRODUCTION_LOSS_PER_HOUR = {
    "blast_furnace": 6.5,
    "rolling_mill":  4.2,
    "caster":        5.0,
    "compressor":    2.8,
    "crane":         1.5,
    "conveyor":      1.2,
    "cooling_tower": 1.0,
    "hydraulic":     1.8,
}

EMERGENCY_LABOR_HOURS = {
    "blast_furnace": 12, "rolling_mill": 8, "caster": 14,
    "compressor": 6, "crane": 8, "conveyor": 4,
    "cooling_tower": 10, "hydraulic": 6,
}

LABOR_RATE_PER_HOUR_INR = 5_000   # per technician
LABOR_TEAM_SIZE = 3
EMERGENCY_LABOR_MULTIPLIER = 3.0   # night/weekend emergency premium
EMERGENCY_PARTS_PREMIUM = 2.5      # express procurement premium


def calculate_business_case(equip_id: str, context: dict, rul_result: dict) -> dict:
    """
    Plain-English cost comparison: act now vs wait until failure.
    Returns numbers a non-engineer supervisor can understand.
    """
    equip_type  = EQUIPMENT_REGISTRY.get(equip_id, {}).get("type", "rolling_mill")
    spares_info = context.get("spares_info", {})
    spares      = spares_info.get("spares", [])
    rul_days    = rul_result.get("estimated_rul_days", 14)

    # ── Planned maintenance cost ───────────────────────────────────────────────
    parts_cost_planned = sum(
        s.get("unit_cost_inr", 0) * max(1, s.get("reorder_point", 1))
        for s in spares if s.get("qty_stock", 0) > 0
    ) / 100_000  # convert to lakhs

    planned_labor_hours = max(4, EMERGENCY_LABOR_HOURS.get(equip_type, 8) * 0.8)
    planned_labor_cost  = (LABOR_TEAM_SIZE * planned_labor_hours
                           * LABOR_RATE_PER_HOUR_INR) / 100_000
    planned_downtime_h  = planned_labor_hours
    planned_total       = parts_cost_planned + planned_labor_cost

    # ── Failure cost ──────────────────────────────────────────────────────────
    failure_downtime_h  = EMERGENCY_LABOR_HOURS.get(equip_type, 10) * 2
    prod_loss_per_hour  = PRODUCTION_LOSS_PER_HOUR.get(equip_type, 2.5)
    production_loss     = failure_downtime_h * prod_loss_per_hour

    emergency_parts     = parts_cost_planned * EMERGENCY_PARTS_PREMIUM
    emergency_labor     = (LABOR_TEAM_SIZE * failure_downtime_h
                           * LABOR_RATE_PER_HOUR_INR
                           * EMERGENCY_LABOR_MULTIPLIER) / 100_000
    failure_total       = production_loss + emergency_parts + emergency_labor

    # Saving & ROI
    saving   = max(0, failure_total - planned_total)
    roi      = failure_total / max(planned_total, 0.01)

    # Urgency window
    if rul_days <= 7:
        urgency_msg = f"⛔ Act within 48 hours — {rul_days:.0f} days remaining"
    elif rul_days <= 21:
        urgency_msg = f"⚠️ Act this week — {rul_days:.0f} days remaining"
    else:
        urgency_msg = f"📋 Plan for next downtime window — {rul_days:.0f} days"

    return {
        "equip_id":  equip_id,
        "equip_name": EQUIPMENT_REGISTRY[equip_id]["name"],
        "urgency_msg": urgency_msg,
        "rul_days":   rul_days,

        "planned": {
            "parts_cost_lakhs":   round(parts_cost_planned, 2),
            "labor_cost_lakhs":   round(planned_labor_cost, 2),
            "total_lakhs":        round(planned_total, 2),
            "downtime_hours":     round(planned_downtime_h, 1),
            "description":        "Planned maintenance at scheduled time",
        },
        "failure": {
            "production_loss_lakhs": round(production_loss, 2),
            "emergency_parts_lakhs": round(emergency_parts, 2),
            "emergency_labor_lakhs": round(emergency_labor, 2),
            "total_lakhs":           round(failure_total, 2),
            "downtime_hours":        round(failure_downtime_h, 1),
            "description":           "Emergency repair after catastrophic failure",
        },
        "saving_lakhs": round(saving, 2),
        "roi_multiple": round(roi, 1),
        "recommendation": (
            f"Every day of delay increases risk. Planned repair "
            f"(₹{planned_total:.1f}L) prevents a potential "
            f"₹{failure_total:.1f}L emergency — a {roi:.0f}x return on action."
        ),
    }


# ── 4. SHIFT HANDOVER ─────────────────────────────────────────────────────────
def generate_shift_handover(shift_hours: int = 8) -> dict:
    """
    Generate a structured shift handover for the incoming team.
    Covers: what happened, what's in progress, what needs attention.
    """
    from database.db_manager import (
        get_all_latest_health, get_all_maintenance_recent,
        get_failure_events,
    )
    from agents.alert_system import get_alerts, get_logbook_entries

    health_map  = {h["equip_id"]: h["health_score"]
                   for h in get_all_latest_health()}
    recent_maint = get_all_maintenance_recent(days=1)
    active_alerts = get_alerts(status="active", limit=10)
    acked_alerts  = get_alerts(status="acknowledged", limit=5)
    log_entries   = get_logbook_entries(days=1, limit=10)

    critical_equip = [
        {"equip_id": eid, "name": EQUIPMENT_REGISTRY[eid]["name"], "health": sc}
        for eid, sc in health_map.items() if sc < 40
    ]
    warning_equip = [
        {"equip_id": eid, "name": EQUIPMENT_REGISTRY[eid]["name"], "health": sc}
        for eid, sc in health_map.items() if 40 <= sc < 70
    ]

    shift_label = _shift_label()
    now_str = datetime.now().strftime("%d %b %Y, %H:%M")

    return {
        "generated_at": now_str,
        "shift":        shift_label,
        "for_next_shift": _next_shift_label(),
        "critical_equipment":  critical_equip,
        "warning_equipment":   warning_equip,
        "active_alerts":       active_alerts[:5],
        "in_progress":         acked_alerts,
        "maintenance_done":    recent_maint[:5],
        "log_entries":         log_entries[:8],
        "handover_notes":      _auto_handover_notes(critical_equip, warning_equip, active_alerts, acked_alerts),
    }


def _auto_handover_notes(critical, warning, active_alerts, acked_alerts):
    notes = []
    if critical:
        equips = ", ".join(f"{e['equip_id']} ({e['health']:.0f}%)" for e in critical)
        notes.append(f"IMMEDIATE: {equips} in critical state — do not delay inspection")
    if warning:
        equips = ", ".join(e['equip_id'] for e in warning[:3])
        notes.append(f"MONITOR: {equips} in warning state — check at start of shift")
    if acked_alerts:
        notes.append(f"{len(acked_alerts)} alert(s) acknowledged but not yet resolved — follow up required")
    crit_alerts = [a for a in active_alerts if a.get("severity") == "CRITICAL"]
    if crit_alerts:
        notes.append(f"{len(crit_alerts)} CRITICAL alert(s) require immediate engineer response")
    if not notes:
        notes.append("Plant operating normally. Continue scheduled rounds.")
    return notes


def _shift_label():
    h = datetime.now().hour
    if 6 <= h < 14:  return "Day Shift (06:00–14:00)"
    if 14 <= h < 22: return "Afternoon Shift (14:00–22:00)"
    return "Night Shift (22:00–06:00)"


def _next_shift_label():
    h = datetime.now().hour
    if 6 <= h < 14:  return "Afternoon Shift (14:00–22:00)"
    if 14 <= h < 22: return "Night Shift (22:00–06:00)"
    return "Day Shift (06:00–14:00)"
