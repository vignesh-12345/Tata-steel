"""
MINERVA Alert System + Digital Maintenance Logbook
Two components:

1. AlertEngine  – continuously monitors sensor readings, generates prioritised
   alerts, manages alert lifecycle (active → acknowledged → resolved).

2. MaintenanceLogbook – auto-generates log entries from agent sessions and
   allows engineers to add manual entries. Serves as the "digital logbook"
   optional enhancement from the problem statement.
"""
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, SENSOR_BASELINES, EQUIPMENT_REGISTRY


# ══════════════════════════════════════════════════════════════════════════════
#  1. ALERT ENGINE
# ══════════════════════════════════════════════════════════════════════════════

ALERT_RULES = [
    # Rule: (sensor_pattern, condition_fn, severity, title_template, body_template)
    {
        "rule_id": "RULE-001",
        "name": "Critical vibration threshold",
        "sensor_pattern": "vibration_rms",
        "severity": "CRITICAL",
        "condition": lambda v, info: v > info.get("critical", (7.0, 20.0))[0],
        "title": "Critical vibration on {equip_id}",
        "body": "Vibration RMS {value:.2f} mm/s exceeds critical threshold {thresh:.1f} mm/s. Bearing failure risk. Inspect immediately.",
        "action": "SOP-GEN-001 Priority 1 work order",
    },
    {
        "rule_id": "RULE-002",
        "name": "Warning vibration threshold",
        "sensor_pattern": "vibration_rms",
        "severity": "HIGH",
        "condition": lambda v, info: info.get("normal", (0,4.5))[1] < v <= info.get("critical", (7.0,20.0))[0],
        "title": "Elevated vibration on {equip_id}",
        "body": "Vibration RMS {value:.2f} mm/s above normal range. Schedule vibration analysis.",
        "action": "Schedule vibration analysis within 72 hours",
    },
    {
        "rule_id": "RULE-003",
        "name": "Bearing temperature critical",
        "sensor_pattern": "temperature_bearing",
        "severity": "CRITICAL",
        "condition": lambda v, info: v > info.get("critical", (90, 130))[0],
        "title": "Critical bearing temperature on {equip_id}",
        "body": "Bearing temperature {value:.1f}°C exceeds critical threshold {thresh:.0f}°C. Thermal damage risk.",
        "action": "Immediate shutdown and inspection",
    },
    {
        "rule_id": "RULE-004",
        "name": "Low oil pressure",
        "sensor_pattern": "oil_pressure",
        "severity": "HIGH",
        "condition": lambda v, info: v < info.get("warn", (2.5, 3.5))[0],
        "title": "Low oil pressure on {equip_id}",
        "body": "Oil pressure {value:.2f} bar below warning threshold. Check for leaks and pump condition.",
        "action": "Inspect oil system within 24 hours",
    },
    {
        "rule_id": "RULE-005",
        "name": "Motor current overload",
        "sensor_pattern": "motor_current",
        "severity": "HIGH",
        "condition": lambda v, info: v > info.get("warn", (140, 180))[1],
        "title": "Motor current overload on {equip_id}",
        "body": "Motor current {value:.1f} A exceeds warning threshold. Mechanical overload or electrical fault.",
        "action": "Inspect motor and mechanical drivetrain",
    },
    {
        "rule_id": "RULE-006",
        "name": "Rapid health decline",
        "sensor_pattern": "_health_score",
        "severity": "HIGH",
        "condition": lambda v, info: v < 40,
        "title": "Critical health score on {equip_id}",
        "body": "Equipment health score {value:.0f}% is in critical range. Multiple sensors showing abnormal conditions.",
        "action": "Full diagnostic inspection recommended",
    },
]


def _get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_alert_tables():
    """Create alert and logbook tables if not present."""
    conn = _get_connection()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_id TEXT UNIQUE,
        rule_id TEXT,
        equip_id TEXT,
        sensor TEXT,
        severity TEXT,
        title TEXT,
        body TEXT,
        action TEXT,
        sensor_value REAL,
        threshold REAL,
        status TEXT DEFAULT 'active',
        created_at TEXT,
        acknowledged_at TEXT,
        resolved_at TEXT,
        acknowledged_by TEXT,
        resolution_note TEXT
    );
    CREATE TABLE IF NOT EXISTS maintenance_logbook (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        log_id TEXT UNIQUE,
        created_at TEXT,
        equip_id TEXT,
        entry_type TEXT,
        title TEXT,
        content TEXT,
        author TEXT,
        source TEXT,
        related_alert_id TEXT,
        related_session_id TEXT
    );
    """)
    conn.commit()
    conn.close()


def scan_and_generate_alerts() -> list[dict]:
    """
    Scan all latest sensor readings and generate new alerts for any violations.
    Idempotent – won't duplicate active alerts for the same rule+equipment.
    Returns list of newly created alerts.
    """
    from database.db_manager import get_latest_readings, get_all_latest_health
    init_alert_tables()

    new_alerts = []
    existing = _get_active_alert_keys()
    conn = _get_connection()

    # Scan sensor readings
    for equip_id in EQUIPMENT_REGISTRY:
        readings = get_latest_readings(equip_id)
        for reading in readings:
            sensor = reading.get("sensor", "")
            value = float(reading.get("value", 0))
            info = SENSOR_BASELINES.get(sensor, {})

            for rule in ALERT_RULES:
                if rule["sensor_pattern"] not in sensor:
                    continue
                try:
                    triggered = rule["condition"](value, info)
                except Exception:
                    triggered = False

                if triggered:
                    alert_key = f"{equip_id}_{rule['rule_id']}"
                    if alert_key in existing:
                        continue  # already active

                    thresh = info.get("critical", info.get("warn", (0, 0)))[0]
                    alert_id = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{equip_id[:3]}-{rule['rule_id'][-3:]}"

                    alert = {
                        "alert_id": alert_id,
                        "rule_id": rule["rule_id"],
                        "equip_id": equip_id,
                        "sensor": sensor,
                        "severity": rule["severity"],
                        "title": rule["title"].format(equip_id=equip_id),
                        "body": rule["body"].format(
                            equip_id=equip_id, value=value,
                            thresh=thresh, sensor=sensor,
                        ),
                        "action": rule["action"],
                        "sensor_value": value,
                        "threshold": thresh,
                        "status": "active",
                        "created_at": datetime.now().isoformat(),
                    }
                    conn.execute("""
                        INSERT OR IGNORE INTO alerts
                        (alert_id,rule_id,equip_id,sensor,severity,title,body,action,
                         sensor_value,threshold,status,created_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                    """, (alert["alert_id"], alert["rule_id"], alert["equip_id"],
                          alert["sensor"], alert["severity"], alert["title"],
                          alert["body"], alert["action"], alert["sensor_value"],
                          alert["threshold"], alert["status"], alert["created_at"]))
                    new_alerts.append(alert)

                    # Auto-log to logbook
                    _auto_log_alert(conn, alert)

    # Scan health scores
    health_data = get_all_latest_health()
    for h in health_data:
        equip_id = h["equip_id"]
        score = float(h.get("health_score", 100))
        rule = next(r for r in ALERT_RULES if r["rule_id"] == "RULE-006")
        if rule["condition"](score, {}):
            alert_key = f"{equip_id}_{rule['rule_id']}"
            if alert_key not in existing:
                alert_id = f"ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{equip_id[:3]}-006"
                alert = {
                    "alert_id": alert_id,
                    "rule_id": "RULE-006",
                    "equip_id": equip_id,
                    "sensor": "health_score",
                    "severity": "HIGH",
                    "title": rule["title"].format(equip_id=equip_id),
                    "body": rule["body"].format(equip_id=equip_id, value=score, thresh=40, sensor="health_score"),
                    "action": rule["action"],
                    "sensor_value": score,
                    "threshold": 40,
                    "status": "active",
                    "created_at": datetime.now().isoformat(),
                }
                conn.execute("""
                    INSERT OR IGNORE INTO alerts
                    (alert_id,rule_id,equip_id,sensor,severity,title,body,action,
                     sensor_value,threshold,status,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (alert["alert_id"], alert["rule_id"], alert["equip_id"],
                      alert["sensor"], alert["severity"], alert["title"],
                      alert["body"], alert["action"], alert["sensor_value"],
                      alert["threshold"], alert["status"], alert["created_at"]))
                new_alerts.append(alert)

    conn.commit()
    conn.close()
    return new_alerts


def get_alerts(status: str = None, equip_id: str = None,
               severity: str = None, limit: int = 50) -> list[dict]:
    """Retrieve alerts with optional filters."""
    init_alert_tables()
    conn = _get_connection()
    clauses, params = [], []
    if status:
        clauses.append("status = ?"); params.append(status)
    if equip_id:
        clauses.append("equip_id = ?"); params.append(equip_id)
    if severity:
        clauses.append("severity = ?"); params.append(severity)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"SELECT * FROM alerts {where} ORDER BY created_at DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def acknowledge_alert(alert_id: str, acknowledged_by: str = "Engineer") -> bool:
    """Acknowledge an active alert."""
    conn = _get_connection()
    conn.execute("""
        UPDATE alerts SET status='acknowledged', acknowledged_at=?, acknowledged_by=?
        WHERE alert_id=? AND status='active'
    """, (datetime.now().isoformat(), acknowledged_by, alert_id))
    conn.commit()
    conn.close()
    return True


def resolve_alert(alert_id: str, resolution_note: str = "") -> bool:
    """Resolve an alert."""
    conn = _get_connection()
    conn.execute("""
        UPDATE alerts SET status='resolved', resolved_at=?, resolution_note=?
        WHERE alert_id=?
    """, (datetime.now().isoformat(), resolution_note, alert_id))
    conn.commit()
    conn.close()
    return True


def get_alert_summary() -> dict:
    """Quick summary of current alert status."""
    init_alert_tables()
    conn = _get_connection()
    rows = conn.execute("SELECT severity, status, COUNT(*) as cnt FROM alerts GROUP BY severity, status").fetchall()
    conn.close()
    summary = {"active_critical": 0, "active_high": 0, "active_medium": 0,
                "acknowledged": 0, "resolved_today": 0, "total_active": 0}
    for r in rows:
        if r["status"] == "active":
            if r["severity"] == "CRITICAL":
                summary["active_critical"] += r["cnt"]
            elif r["severity"] == "HIGH":
                summary["active_high"] += r["cnt"]
            else:
                summary["active_medium"] += r["cnt"]
            summary["total_active"] += r["cnt"]
        elif r["status"] == "acknowledged":
            summary["acknowledged"] += r["cnt"]
    return summary


def _get_active_alert_keys() -> set:
    try:
        conn = _get_connection()
        rows = conn.execute(
            "SELECT equip_id, rule_id FROM alerts WHERE status IN ('active','acknowledged')"
        ).fetchall()
        conn.close()
        return {f"{r['equip_id']}_{r['rule_id']}" for r in rows}
    except Exception:
        return set()


# ══════════════════════════════════════════════════════════════════════════════
#  2. DIGITAL MAINTENANCE LOGBOOK
# ══════════════════════════════════════════════════════════════════════════════

def add_logbook_entry(equip_id: str, entry_type: str, title: str,
                      content: str, author: str = "Engineer",
                      source: str = "manual",
                      related_alert_id: str = None,
                      related_session_id: str = None) -> str:
    """Add an entry to the digital maintenance logbook."""
    init_alert_tables()
    log_id = f"LOG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{equip_id[:3]}"
    conn = _get_connection()
    conn.execute("""
        INSERT INTO maintenance_logbook
        (log_id,created_at,equip_id,entry_type,title,content,author,source,
         related_alert_id,related_session_id)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, (log_id, datetime.now().isoformat(), equip_id, entry_type, title,
          content, author, source, related_alert_id, related_session_id))
    conn.commit()
    conn.close()
    return log_id


def get_logbook_entries(equip_id: str = None, entry_type: str = None,
                        days: int = 30, limit: int = 50) -> list[dict]:
    """Retrieve logbook entries."""
    init_alert_tables()
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _get_connection()
    clauses = ["created_at >= ?"]
    params = [cutoff]
    if equip_id:
        clauses.append("equip_id = ?"); params.append(equip_id)
    if entry_type:
        clauses.append("entry_type = ?"); params.append(entry_type)
    rows = conn.execute(
        f"SELECT * FROM maintenance_logbook WHERE {' AND '.join(clauses)} ORDER BY created_at DESC LIMIT ?",
        params + [limit]
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def auto_log_from_session(session_id: str, equip_id: str,
                           query: str, verdict: str, actions: str):
    """Auto-generate a logbook entry from an agent session."""
    if not equip_id or equip_id == "PLANT":
        return
    content = f"Query: {query}\n\nAI Verdict: {verdict}\n\nRecommended Actions:\n{actions}"
    add_logbook_entry(
        equip_id=equip_id,
        entry_type="AI_Diagnosis",
        title=f"MINERVA diagnosis — {query[:60]}{'...' if len(query)>60 else ''}",
        content=content,
        author="MINERVA AI",
        source="agent_session",
        related_session_id=session_id,
    )


def _auto_log_alert(conn, alert: dict):
    """Auto-log an alert to the logbook."""
    log_id = f"LOG-ALT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{alert['equip_id'][:3]}"
    conn.execute("""
        INSERT OR IGNORE INTO maintenance_logbook
        (log_id,created_at,equip_id,entry_type,title,content,author,source,related_alert_id)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, (log_id, datetime.now().isoformat(), alert["equip_id"],
          "Alert", alert["title"], alert["body"],
          "MINERVA Alert System", "auto_alert", alert["alert_id"]))


ENTRY_TYPES = [
    "AI_Diagnosis", "Alert", "Observation", "Inspection",
    "Repair", "Parts_Used", "Measurement", "Shift_Handover", "Other"
]
