"""
MINERVA Database Manager
All SQLite query functions used by agents and API.
"""
import sqlite3
import json
import pandas as pd
from datetime import datetime
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DB_PATH, EQUIPMENT_REGISTRY, SENSOR_BASELINES


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Sensor data queries ───────────────────────────────────────────────────────

def get_latest_readings(equip_id: str) -> list[dict]:
    """Latest sensor reading for each sensor of an equipment."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT s.* FROM sensor_readings s
        INNER JOIN (
            SELECT sensor, MAX(date) as max_date
            FROM sensor_readings WHERE equip_id = ?
            GROUP BY sensor
        ) latest ON s.sensor = latest.sensor AND s.date = latest.max_date
        WHERE s.equip_id = ?
        ORDER BY s.sensor
    """, (equip_id, equip_id))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_sensor_history(equip_id: str, sensor: str, days: int = 30) -> pd.DataFrame:
    """Time-series for a specific sensor over N days."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date, value, status FROM sensor_readings
        WHERE equip_id = ? AND sensor = ?
        ORDER BY date DESC LIMIT ?
    """, conn, params=(equip_id, sensor, days))
    conn.close()
    return df.sort_values("date").reset_index(drop=True)


def get_multi_sensor_history(equip_id: str, days: int = 30) -> pd.DataFrame:
    """All sensors for an equipment over N days (pivoted)."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date, sensor, value, status FROM sensor_readings
        WHERE equip_id = ? AND day_index >= (SELECT MAX(day_index) - ? FROM sensor_readings WHERE equip_id = ?)
        ORDER BY date, sensor
    """, conn, params=(equip_id, days, equip_id))
    conn.close()
    return df


def get_anomalous_sensors(equip_id: str) -> list[dict]:
    """Current warning/critical sensors for an equipment."""
    readings = get_latest_readings(equip_id)
    return [r for r in readings if r["status"] in ("warning", "critical")]


def get_all_latest_health() -> list[dict]:
    """Latest health score for all equipment."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT h.* FROM health_scores h
        INNER JOIN (
            SELECT equip_id, MAX(date) as max_date
            FROM health_scores GROUP BY equip_id
        ) latest ON h.equip_id = latest.equip_id AND h.date = latest.max_date
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_health_trend(equip_id: str, days: int = 30) -> pd.DataFrame:
    """Health score trend for an equipment."""
    conn = get_connection()
    df = pd.read_sql_query("""
        SELECT date, health_score FROM health_scores
        WHERE equip_id = ? ORDER BY date DESC LIMIT ?
    """, conn, params=(equip_id, days))
    conn.close()
    return df.sort_values("date").reset_index(drop=True)


# ── Maintenance history queries ───────────────────────────────────────────────

def get_maintenance_history(equip_id: str, limit: int = 10) -> list[dict]:
    """Recent maintenance events for equipment."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM maintenance_history WHERE equip_id = ?
        ORDER BY maintenance_date DESC LIMIT ?
    """, (equip_id, limit))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_all_maintenance_recent(days: int = 30) -> list[dict]:
    """Plant-wide maintenance events in last N days."""
    conn = get_connection()
    cutoff = (datetime.now() - __import__("datetime").timedelta(days=days)).strftime("%Y-%m-%d")
    c = conn.cursor()
    c.execute("SELECT * FROM maintenance_history WHERE maintenance_date >= ? ORDER BY maintenance_date DESC", (cutoff,))
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Failure events & counterfactuals ─────────────────────────────────────────

def get_failure_events(equip_id: str = None) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    if equip_id:
        c.execute("SELECT * FROM failure_events WHERE equip_id = ? ORDER BY event_date DESC", (equip_id,))
    else:
        c.execute("SELECT * FROM failure_events ORDER BY event_date DESC")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


# ── Spare parts queries ───────────────────────────────────────────────────────

def get_spares(equip_id: str = None) -> list[dict]:
    conn = get_connection()
    c = conn.cursor()
    if equip_id:
        c.execute("SELECT * FROM spares_inventory WHERE equip_id = ? ORDER BY part_code", (equip_id,))
    else:
        c.execute("SELECT * FROM spares_inventory ORDER BY equip_id, part_code")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_spare_availability(equip_id: str) -> dict:
    """Returns spare availability summary for risk scoring."""
    spares = get_spares(equip_id)
    available = [s for s in spares if s["qty_stock"] >= s["reorder_point"]]
    critical_shortage = [s for s in spares if s["qty_stock"] == 0]
    max_lead_time = max((s["lead_time_days"] for s in spares), default=0)
    return {
        "total_parts": len(spares),
        "available_parts": len(available),
        "critical_shortage": critical_shortage,
        "max_lead_time_days": max_lead_time,
        "spares": spares,
    }


# ── Feedback & session logging ────────────────────────────────────────────────

def log_feedback(equip_id: str, query: str, recommendation: str,
                 feedback_type: str, comment: str, was_correct: bool):
    conn = get_connection()
    conn.execute("""
        INSERT INTO feedback_log (timestamp,equip_id,query,recommendation,
                                  feedback_type,engineer_comment,was_correct)
        VALUES (?,?,?,?,?,?,?)
    """, (datetime.now().isoformat(), equip_id, query, recommendation,
          feedback_type, comment, int(was_correct)))
    conn.commit()
    conn.close()


def log_agent_session(session_id: str, equip_id: str, query: str,
                      hypothesis: str, skeptic: str, verdict: str,
                      archaeology: str, risk_score: float, rul_days: float, actions: str):
    conn = get_connection()
    conn.execute("""
        INSERT INTO agent_sessions
        (session_id,timestamp,equip_id,query,hypothesis,skeptic_challenge,
         verdict,archaeology,risk_score,rul_days,actions)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (session_id, datetime.now().isoformat(), equip_id, query,
          hypothesis, skeptic, verdict, archaeology, risk_score, rul_days, actions))
    conn.commit()
    conn.close()


# ── Context builder (used by agents) ─────────────────────────────────────────

def build_equipment_context(equip_id: str) -> dict:
    """Aggregate all relevant data for an equipment into a single context dict."""
    equip_info = EQUIPMENT_REGISTRY.get(equip_id, {})
    latest = get_latest_readings(equip_id)
    anomalous = get_anomalous_sensors(equip_id)
    history = get_maintenance_history(equip_id, limit=5)
    spares = get_spare_availability(equip_id)
    failures = get_failure_events(equip_id)
    health_trend = get_health_trend(equip_id, days=14)

    # Sensor trend summary (last 7 days slope)
    trends = {}
    from config import SENSOR_MAP
    for sensor in SENSOR_MAP.get(equip_info.get("type", ""), []):
        hist = get_sensor_history(equip_id, sensor, days=7)
        if len(hist) >= 3:
            vals = hist["value"].values
            slope = (vals[-1] - vals[0]) / len(vals)
            trends[sensor] = round(slope, 4)

    return {
        "equip_id": equip_id,
        "equip_name": equip_info.get("name", equip_id),
        "equip_type": equip_info.get("type", "unknown"),
        "criticality": equip_info.get("criticality", "medium"),
        "latest_readings": latest,
        "anomalous_sensors": anomalous,
        "sensor_trends_7d": trends,
        "maintenance_history": history,
        "spares_info": spares,
        "failure_events": failures,
        "current_health": health_trend["health_score"].iloc[-1] if len(health_trend) > 0 else 80.0,
        "health_trend_7d": health_trend.tail(7)["health_score"].tolist() if len(health_trend) > 0 else [],
    }
