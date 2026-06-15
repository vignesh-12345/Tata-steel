"""
MINERVA Synthetic Data Generator
Generates realistic steel plant sensor data with degradation patterns.
Each equipment has a scripted "story" mimicking real-world failure progression.
"""
import numpy as np
import pandas as pd
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EQUIPMENT_REGISTRY, SENSOR_MAP, SENSOR_BASELINES, DB_PATH

np.random.seed(42)

# ── Failure mode scripts ──────────────────────────────────────────────────────
# Each equipment gets a "failure story" over the 90-day window
# Pattern: normal → early degradation → warning → critical
FAILURE_STORIES = {
    "RM-2": {
        "description": "Outer race bearing defect – vibration and temperature escalating",
        "failure_mode": "Bearing Outer Race Damage",
        "affected_sensors": {
            "vibration_rms":      {"story": "bearing_vib",  "onset_day": 55, "severity": 0.9},
            "temperature_bearing":{"story": "bearing_temp", "onset_day": 60, "severity": 0.8},
            "motor_current":      {"story": "gradual_rise", "onset_day": 62, "severity": 0.4},
        },
        "health_score_day90": 28,
        "rul_days": 8,
        "status": "critical",
    },
    "BF-1": {
        "description": "Cooling circuit partial blockage – flow rate declining",
        "failure_mode": "Cooling System Fouling",
        "affected_sensors": {
            "flow_rate_gas":       {"story": "gradual_drop", "onset_day": 70, "severity": 0.5},
            "temperature_cooling": {"story": "gradual_rise", "onset_day": 72, "severity": 0.4},
            "pressure_blast":      {"story": "gradual_rise", "onset_day": 75, "severity": 0.3},
        },
        "health_score_day90": 62,
        "rul_days": 22,
        "status": "warning",
    },
    "CCM-1": {
        "description": "Mold oscillation anomaly – recently repaired, recovering",
        "failure_mode": "Oscillation Mechanism Wear",
        "affected_sensors": {
            "oscillation_freq":    {"story": "recover",     "onset_day": 0,  "severity": 0.6},
            "vibration_rms":       {"story": "recover",     "onset_day": 0,  "severity": 0.5},
        },
        "health_score_day90": 78,
        "rul_days": 65,
        "status": "normal",
    },
    "COMP-1": {
        "description": "Normal operation with minor discharge temperature trend",
        "failure_mode": "None",
        "affected_sensors": {
            "temperature_discharge":{"story": "very_slow_rise","onset_day": 80,"severity": 0.2},
        },
        "health_score_day90": 85,
        "rul_days": 55,
        "status": "normal",
    },
    "OHC-1": {
        "description": "Historical brake overheating event at day 40 – since resolved",
        "failure_mode": "Brake Pad Glazing (Resolved)",
        "affected_sensors": {
            "brake_temp":  {"story": "spike_resolved", "onset_day": 35, "severity": 0.9},
            "motor_current":{"story": "spike_resolved","onset_day": 35, "severity": 0.5},
        },
        "health_score_day90": 88,
        "rul_days": 70,
        "status": "normal",
    },
    "CB-2": {
        "description": "Intermittent belt misalignment causing current spikes",
        "failure_mode": "Belt Misalignment",
        "affected_sensors": {
            "alignment_deviation": {"story": "intermittent", "onset_day": 50, "severity": 0.7},
            "motor_current":       {"story": "intermittent", "onset_day": 52, "severity": 0.5},
            "belt_tension":        {"story": "intermittent", "onset_day": 53, "severity": 0.4},
        },
        "health_score_day90": 55,
        "rul_days": 18,
        "status": "warning",
    },
    "CT-1": {
        "description": "Gradual fouling reducing cooling effectiveness",
        "failure_mode": "Heat Exchanger Fouling",
        "affected_sensors": {
            "flow_rate_water":     {"story": "gradual_drop", "onset_day": 60, "severity": 0.4},
            "pressure_drop":       {"story": "gradual_rise", "onset_day": 60, "severity": 0.5},
            "temperature_outlet":  {"story": "gradual_rise", "onset_day": 65, "severity": 0.3},
        },
        "health_score_day90": 68,
        "rul_days": 30,
        "status": "warning",
    },
    "HYD-1": {
        "description": "All parameters nominal – healthy reference system",
        "failure_mode": "None",
        "affected_sensors": {},
        "health_score_day90": 94,
        "rul_days": 90,
        "status": "normal",
    },
}

# Maintenance history entries (realistic for demo)
MAINTENANCE_HISTORY = [
    {"equip_id":"RM-2",  "date_offset":-45, "type":"Preventive","action":"Lubrication and visual inspection","finding":"Minor vibration noted – monitoring","technician":"R.Kumar","duration_h":2},
    {"equip_id":"RM-2",  "date_offset":-15, "type":"Predictive","action":"Vibration analysis performed","finding":"Vibration trending upward at bearing frequency 3.2kHz","technician":"S.Mehta","duration_h":1},
    {"equip_id":"BF-1",  "date_offset":-30, "type":"Preventive","action":"Cooling circuit inspection and cleaning","finding":"Partial scale deposits found in cooling lines","technician":"P.Sharma","duration_h":6},
    {"equip_id":"CCM-1", "date_offset":-80, "type":"Corrective","action":"Oscillation mechanism replaced","finding":"Worn cam follower and eccentric pin","technician":"A.Singh","duration_h":14},
    {"equip_id":"OHC-1", "date_offset":-50, "type":"Emergency","action":"Brake system emergency shutdown and inspection","finding":"Brake pad glazing and overheating – pads replaced","technician":"V.Patel","duration_h":8},
    {"equip_id":"OHC-1", "date_offset":-48, "type":"Corrective","action":"Brake pad replacement and adjustment","finding":"New pads installed, adjustment completed","technician":"V.Patel","duration_h":4},
    {"equip_id":"CB-2",  "date_offset":-60, "type":"Preventive","action":"Belt inspection and tension adjustment","finding":"Minor tracking deviation observed","technician":"R.Kumar","duration_h":3},
    {"equip_id":"CT-1",  "date_offset":-90, "type":"Preventive","action":"Annual cleaning and inspection","finding":"Light fouling, cleaned and treated","technician":"N.Rao","duration_h":12},
    {"equip_id":"COMP-1","date_offset":-120,"type":"Preventive","action":"Oil change, filter replacement, vibration check","finding":"All parameters within normal limits","technician":"S.Mehta","duration_h":4},
    {"equip_id":"HYD-1", "date_offset":-60, "type":"Preventive","action":"Oil analysis and filter inspection","finding":"Oil clean, filter within limits","technician":"P.Sharma","duration_h":2},
    {"equip_id":"RM-2",  "date_offset":-90, "type":"Preventive","action":"6-month scheduled overhaul","finding":"Bearing clearances measured within spec","technician":"A.Singh","duration_h":24},
]

# Failure event log (for counterfactual analysis)
FAILURE_EVENTS = [
    {
        "equip_id": "OHC-1",
        "date_offset": -48,
        "failure_mode": "Brake Pad Glazing",
        "downtime_hours": 6,
        "cost_inr_lakhs": 8.5,
        "precursor_missed": "Temperature rise of 18°C over 5 days before event – no alert triggered",
        "counterfactual": "Had intervention occurred 5 days earlier (brake inspection), probability of failure event reduced by 81%. Estimated savings: ₹6.8 lakhs + 4.8 hours production.",
        "lessons": "Revised brake temperature threshold from 90°C to 70°C for early warning."
    },
    {
        "equip_id": "CCM-1",
        "date_offset": -85,
        "failure_mode": "Oscillation Mechanism Failure",
        "downtime_hours": 14,
        "cost_inr_lakhs": 22.0,
        "precursor_missed": "Oscillation frequency drift of 12% over 10 days before failure",
        "counterfactual": "Planned replacement 7 days earlier would have been possible during scheduled downtime. Savings: ₹14 lakhs (avoided emergency shutdown).",
        "lessons": "Added oscillation frequency trending to predictive maintenance schedule."
    },
]

# Spare parts inventory
SPARES_INVENTORY = [
    {"part_code":"SKF-6312-C3",  "description":"Deep Groove Ball Bearing",       "equip_id":"RM-2",   "qty_stock":2, "reorder_point":1, "lead_time_days":3,  "unit_cost_inr":8500},
    {"part_code":"SKF-NJ2316",   "description":"Cylindrical Roller Bearing",      "equip_id":"RM-2",   "qty_stock":0, "reorder_point":1, "lead_time_days":7,  "unit_cost_inr":22000},
    {"part_code":"HYD-SEAL-KIT", "description":"Hydraulic Seal Kit",              "equip_id":"HYD-1",  "qty_stock":5, "reorder_point":2, "lead_time_days":2,  "unit_cost_inr":4500},
    {"part_code":"COMP-FILTER-A","description":"Compressor Air Filter",           "equip_id":"COMP-1", "qty_stock":8, "reorder_point":3, "lead_time_days":1,  "unit_cost_inr":2200},
    {"part_code":"BRAKE-PAD-OHC","description":"Crane Brake Pad Set",            "equip_id":"OHC-1",  "qty_stock":4, "reorder_point":2, "lead_time_days":5,  "unit_cost_inr":6800},
    {"part_code":"BELT-CB2-MAIN","description":"Conveyor Main Belt (per metre)",  "equip_id":"CB-2",   "qty_stock":0, "reorder_point":10, "lead_time_days":14,"unit_cost_inr":3200},
    {"part_code":"CT-FILL-PACK", "description":"Cooling Tower Fill Pack",        "equip_id":"CT-1",   "qty_stock":1, "reorder_point":1, "lead_time_days":21, "unit_cost_inr":85000},
    {"part_code":"BF-NOZZLE",    "description":"Blast Furnace Tuyere Nozzle",   "equip_id":"BF-1",   "qty_stock":12,"reorder_point":6, "lead_time_days":30, "unit_cost_inr":45000},
]

# ── Signal generation helpers ─────────────────────────────────────────────────

def _get_baseline(sensor: str) -> float:
    info = SENSOR_BASELINES.get(sensor, {})
    lo, hi = info.get("normal", (0, 100))
    return (lo + hi) / 2

def _normal_noise(base: float, pct: float = 0.03) -> float:
    return base + np.random.normal(0, base * pct)

def _generate_sensor_series(sensor: str, story: str, onset: int, severity: float, n_days: int = 90) -> np.ndarray:
    """Generate 90-day hourly-aggregated daily readings for a sensor based on failure story."""
    info = SENSOR_BASELINES.get(sensor, {"normal": (0, 100), "warn": (100, 150), "critical": (150, 200)})
    base = _get_baseline(sensor)
    warn_lo, warn_hi = info["warn"]
    crit_lo, crit_hi = info["critical"]

    # Determine direction of degradation (up or down)
    deg_direction = 1 if warn_hi > warn_lo else -1  # usually up; for pressure/flow it's down

    values = []
    for day in range(n_days):
        noise = np.random.normal(0, base * 0.025)
        progress = max(0, (day - onset) / (n_days - onset + 1)) if day >= onset else 0

        if story == "bearing_vib":
            # Exponential growth characteristic of bearing degradation
            val = base + noise + (progress ** 2.5) * severity * (warn_hi - base) * 2.2
        elif story == "bearing_temp":
            # Thermal lag after vibration onset
            val = base + noise + (progress ** 2.0) * severity * (warn_hi - base) * 1.6
        elif story == "gradual_rise":
            val = base + noise + progress * severity * (warn_hi - base) * 1.4
        elif story == "gradual_drop":
            lo, hi = info["normal"]
            val = base + noise - progress * severity * (base - info["critical"][0]) * 0.8
        elif story == "very_slow_rise":
            val = base + noise + progress * severity * (warn_hi - base) * 0.4
        elif story == "recover":
            # Starts in warning, recovers to normal
            start_val = warn_lo + (warn_hi - warn_lo) * 0.6
            val = start_val - (day / n_days) * (start_val - base) + noise
        elif story == "spike_resolved":
            if onset <= day <= onset + 10:
                intensity = np.sin(np.pi * (day - onset) / 10)
                val = base + noise + intensity * severity * (crit_hi - base) * 0.8
            else:
                val = base + noise
        elif story == "intermittent":
            if day >= onset:
                spike = np.random.choice([0, 1], p=[0.6, 0.4])
                val = base + noise + spike * severity * (warn_hi - base) * 1.2 * progress
            else:
                val = base + noise
        else:
            val = base + noise

        # Clamp to physical limits
        lo_limit = info["critical"][0] if "pressure" in sensor or "flow" in sensor or "pump" in sensor else 0
        hi_limit = crit_hi * 1.3
        values.append(np.clip(val, lo_limit, hi_limit))

    return np.array(values)


def generate_all_sensor_data(n_days: int = 90) -> pd.DataFrame:
    """Generate 90 days of sensor readings for all equipment."""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_date = today - timedelta(days=n_days - 1)
    dates = [start_date + timedelta(days=i) for i in range(n_days)]

    rows = []
    for equip_id, equip_info in EQUIPMENT_REGISTRY.items():
        sensors = SENSOR_MAP[equip_info["type"]]
        story_info = FAILURE_STORIES.get(equip_id, {})

        for sensor in sensors:
            affected = story_info.get("affected_sensors", {}).get(sensor)
            if affected:
                series = _generate_sensor_series(
                    sensor, affected["story"], affected["onset_day"],
                    affected["severity"], n_days
                )
            else:
                base = _get_baseline(sensor)
                series = np.array([_normal_noise(base) for _ in range(n_days)])

            for i, (dt, val) in enumerate(zip(dates, series)):
                # Classify status
                info = SENSOR_BASELINES.get(sensor, {})
                norm_lo, norm_hi = info.get("normal", (0, 1e9))
                warn_lo, warn_hi = info.get("warn", (0, 1e9))
                crit_lo, crit_hi = info.get("critical", (0, 1e9))

                if norm_lo <= val <= norm_hi:
                    status = "normal"
                elif (warn_lo <= val <= warn_hi) or (val < norm_lo and val >= crit_lo):
                    status = "warning"
                elif (val >= crit_lo and val <= crit_hi) or (val < crit_lo):
                    status = "critical"
                else:
                    status = "normal"

                rows.append({
                    "date": dt.strftime("%Y-%m-%d"),
                    "equip_id": equip_id,
                    "sensor": sensor,
                    "value": round(float(val), 4),
                    "unit": info.get("unit", ""),
                    "status": status,
                    "day_index": i,
                })

    return pd.DataFrame(rows)


def compute_health_scores(sensor_df: pd.DataFrame) -> pd.DataFrame:
    """Compute daily equipment health score (0-100) from sensor statuses."""
    status_weight = {"normal": 100, "warning": 55, "critical": 15}
    records = []

    for (date, equip_id), grp in sensor_df.groupby(["date", "equip_id"]):
        scores = [status_weight.get(r["status"], 100) for _, r in grp.iterrows()]
        health = round(float(np.mean(scores)), 1)

        # Apply equipment-specific story override for latest day
        story = FAILURE_STORIES.get(equip_id, {})
        if date == sensor_df["date"].max() and "health_score_day90" in story:
            health = float(story["health_score_day90"])

        records.append({"date": date, "equip_id": equip_id, "health_score": health})

    return pd.DataFrame(records)


def get_rul_estimates() -> dict:
    """Return current RUL estimates per equipment (days to failure)."""
    return {eid: FAILURE_STORIES[eid]["rul_days"] for eid in EQUIPMENT_REGISTRY}


def seed_database():
    """Create and populate the SQLite database."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # ── Create tables ──────────────────────────────────────────────────────────
    c.executescript("""
    CREATE TABLE IF NOT EXISTS sensor_readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, equip_id TEXT, sensor TEXT,
        value REAL, unit TEXT, status TEXT, day_index INTEGER
    );
    CREATE TABLE IF NOT EXISTS health_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT, equip_id TEXT, health_score REAL
    );
    CREATE TABLE IF NOT EXISTS maintenance_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equip_id TEXT, maintenance_date TEXT, type TEXT,
        action TEXT, finding TEXT, technician TEXT, duration_h REAL
    );
    CREATE TABLE IF NOT EXISTS failure_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        equip_id TEXT, event_date TEXT, failure_mode TEXT,
        downtime_hours REAL, cost_inr_lakhs REAL,
        precursor_missed TEXT, counterfactual TEXT, lessons TEXT
    );
    CREATE TABLE IF NOT EXISTS spares_inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_code TEXT, description TEXT, equip_id TEXT,
        qty_stock INTEGER, reorder_point INTEGER,
        lead_time_days INTEGER, unit_cost_inr REAL
    );
    CREATE TABLE IF NOT EXISTS feedback_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT, equip_id TEXT, query TEXT,
        recommendation TEXT, feedback_type TEXT,
        engineer_comment TEXT, was_correct INTEGER
    );
    CREATE TABLE IF NOT EXISTS agent_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id TEXT, timestamp TEXT, equip_id TEXT,
        query TEXT, hypothesis TEXT, skeptic_challenge TEXT,
        verdict TEXT, archaeology TEXT, risk_score REAL,
        rul_days REAL, actions TEXT
    );
    """)

    # ── Insert sensor data ─────────────────────────────────────────────────────
    print("Generating sensor data…")
    sensor_df = generate_all_sensor_data(90)
    sensor_df.to_sql("sensor_readings", conn, if_exists="replace", index=False)

    # ── Insert health scores ───────────────────────────────────────────────────
    health_df = compute_health_scores(sensor_df)
    health_df.to_sql("health_scores", conn, if_exists="replace", index=False)

    # ── Insert maintenance history ─────────────────────────────────────────────
    today = datetime.now()
    for mh in MAINTENANCE_HISTORY:
        dt = (today + timedelta(days=mh["date_offset"])).strftime("%Y-%m-%d")
        c.execute("""INSERT OR IGNORE INTO maintenance_history
                     (equip_id,maintenance_date,type,action,finding,technician,duration_h)
                     VALUES (?,?,?,?,?,?,?)""",
                  (mh["equip_id"], dt, mh["type"], mh["action"],
                   mh["finding"], mh["technician"], mh["duration_h"]))

    # ── Insert failure events ──────────────────────────────────────────────────
    for fe in FAILURE_EVENTS:
        dt = (today + timedelta(days=fe["date_offset"])).strftime("%Y-%m-%d")
        c.execute("""INSERT OR IGNORE INTO failure_events
                     (equip_id,event_date,failure_mode,downtime_hours,cost_inr_lakhs,
                      precursor_missed,counterfactual,lessons)
                     VALUES (?,?,?,?,?,?,?,?)""",
                  (fe["equip_id"], dt, fe["failure_mode"], fe["downtime_hours"],
                   fe["cost_inr_lakhs"], fe["precursor_missed"],
                   fe["counterfactual"], fe["lessons"]))

    # ── Insert spares ──────────────────────────────────────────────────────────
    for s in SPARES_INVENTORY:
        c.execute("""INSERT OR IGNORE INTO spares_inventory
                     (part_code,description,equip_id,qty_stock,reorder_point,
                      lead_time_days,unit_cost_inr)
                     VALUES (?,?,?,?,?,?,?)""",
                  (s["part_code"], s["description"], s["equip_id"],
                   s["qty_stock"], s["reorder_point"],
                   s["lead_time_days"], s["unit_cost_inr"]))

    conn.commit()
    conn.close()
    print(f"✓ Database seeded at {DB_PATH}")
    return sensor_df, health_df


if __name__ == "__main__":
    seed_database()
    print("✓ All synthetic data generated.")
