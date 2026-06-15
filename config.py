"""
MINERVA Configuration
Maintenance Intelligence with Neural Engines for Reasoning, Vigilance, and Action
"""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "database" / "minerva.db"
CHROMA_PATH = BASE_DIR / "database" / "chroma_store"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-sonnet-4-20250514"

# Demo mode: works without Claude API key using pre-computed responses
DEMO_MODE = not bool(ANTHROPIC_API_KEY)

# Steel plant equipment registry
EQUIPMENT_REGISTRY = {
    "RM-2":   {"name": "Rolling Mill 2",         "type": "rolling_mill",     "criticality": "critical"},
    "BF-1":   {"name": "Blast Furnace 1",         "type": "blast_furnace",    "criticality": "critical"},
    "CCM-1":  {"name": "Continuous Caster 1",     "type": "caster",           "criticality": "high"},
    "COMP-1": {"name": "Compressor 1",            "type": "compressor",       "criticality": "high"},
    "OHC-1":  {"name": "Overhead Crane 1",        "type": "crane",            "criticality": "medium"},
    "CB-2":   {"name": "Conveyor Belt 2",         "type": "conveyor",         "criticality": "medium"},
    "CT-1":   {"name": "Cooling Tower 1",         "type": "cooling_tower",    "criticality": "medium"},
    "HYD-1":  {"name": "Hydraulic System 1",      "type": "hydraulic",        "criticality": "high"},
}

# Sensor definitions per equipment type
SENSOR_MAP = {
    "rolling_mill":  ["vibration_rms", "temperature_bearing", "motor_current", "roll_force", "rpm", "oil_pressure"],
    "blast_furnace": ["temperature_shell", "pressure_blast", "temperature_cooling", "flow_rate_gas", "vibration_rms", "co_ratio"],
    "caster":        ["temperature_mold", "flow_rate_water", "vibration_rms", "speed_casting", "pressure_cooling", "oscillation_freq"],
    "compressor":    ["vibration_rms", "temperature_discharge", "pressure_outlet", "motor_current", "rpm", "oil_temperature"],
    "crane":         ["load_weight", "motor_current", "vibration_rms", "brake_temp", "cable_tension", "rpm"],
    "conveyor":      ["belt_tension", "motor_current", "vibration_rms", "temperature_bearing", "speed_belt", "alignment_deviation"],
    "cooling_tower": ["flow_rate_water", "temperature_inlet", "temperature_outlet", "fan_rpm", "vibration_rms", "pressure_drop"],
    "hydraulic":     ["pressure_system", "oil_temperature", "flow_rate_oil", "vibration_rms", "filter_dp", "pump_efficiency"],
}

# Normal operating ranges [min, max] per sensor
SENSOR_BASELINES = {
    "vibration_rms":       {"normal": (1.0, 4.5),   "warn": (4.5, 7.0),  "critical": (7.0, 20.0), "unit": "mm/s"},
    "temperature_bearing": {"normal": (45, 75),     "warn": (75, 90),    "critical": (90, 130),   "unit": "°C"},
    "temperature_shell":   {"normal": (180, 350),   "warn": (350, 420),  "critical": (420, 600),  "unit": "°C"},
    "temperature_discharge":{"normal":(60, 90),     "warn": (90, 110),   "critical": (110, 150),  "unit": "°C"},
    "temperature_mold":    {"normal": (30, 60),     "warn": (60, 80),    "critical": (80, 120),   "unit": "°C"},
    "oil_pressure":        {"normal": (3.5, 5.5),   "warn": (2.5, 3.5),  "critical": (0.5, 2.5),  "unit": "bar"},
    "oil_temperature":     {"normal": (40, 65),     "warn": (65, 80),    "critical": (80, 110),   "unit": "°C"},
    "motor_current":       {"normal": (80, 140),    "warn": (140, 180),  "critical": (180, 250),  "unit": "A"},
    "pressure_outlet":     {"normal": (4.5, 7.5),   "warn": (7.5, 9.0),  "critical": (9.0, 12.0), "unit": "bar"},
    "pressure_system":     {"normal": (150, 220),   "warn": (120, 150),  "critical": (80, 120),   "unit": "bar"},
    "rpm":                 {"normal": (1440, 1500), "warn": (1380, 1440),"critical": (1200, 1380),"unit": "RPM"},
    "flow_rate_water":     {"normal": (120, 180),   "warn": (90, 120),   "critical": (50, 90),    "unit": "m³/h"},
    "flow_rate_oil":       {"normal": (25, 40),     "warn": (15, 25),    "critical": (5, 15),     "unit": "L/min"},
    "roll_force":          {"normal": (800, 1200),  "warn": (1200, 1500),"critical": (1500, 2000),"unit": "kN"},
    "pressure_blast":      {"normal": (2.5, 4.0),   "warn": (4.0, 5.0),  "critical": (5.0, 7.0),  "unit": "bar"},
    "filter_dp":           {"normal": (0.5, 2.0),   "warn": (2.0, 3.5),  "critical": (3.5, 6.0),  "unit": "bar"},
    "pump_efficiency":     {"normal": (75, 95),     "warn": (60, 75),    "critical": (40, 60),    "unit": "%"},
    "belt_tension":        {"normal": (2500, 3500), "warn": (3500, 4500),"critical": (4500, 6000),"unit": "N"},
    "co_ratio":            {"normal": (0.40, 0.55), "warn": (0.55, 0.65),"critical": (0.65, 0.80),"unit": "ratio"},
    "alignment_deviation": {"normal": (0, 1.5),     "warn": (1.5, 3.0),  "critical": (3.0, 6.0),  "unit": "mm"},
    "pressure_drop":       {"normal": (0.2, 0.6),   "warn": (0.6, 1.0),  "critical": (1.0, 2.0),  "unit": "bar"},
    "speed_casting":       {"normal": (0.8, 1.6),   "warn": (0.5, 0.8),  "critical": (0.2, 0.5),  "unit": "m/min"},
    "pressure_cooling":    {"normal": (3.0, 6.0),   "warn": (2.0, 3.0),  "critical": (0.5, 2.0),  "unit": "bar"},
    "oscillation_freq":    {"normal": (100, 180),   "warn": (80, 100),   "critical": (50, 80),    "unit": "opm"},
    "load_weight":         {"normal": (0, 150),     "warn": (150, 200),  "critical": (200, 250),  "unit": "tonnes"},
    "brake_temp":          {"normal": (20, 60),     "warn": (60, 90),    "critical": (90, 150),   "unit": "°C"},
    "cable_tension":       {"normal": (500, 1200),  "warn": (1200, 1600),"critical": (1600, 2500),"unit": "kN"},
    "fan_rpm":             {"normal": (400, 600),   "warn": (300, 400),  "critical": (100, 300),  "unit": "RPM"},
    "temperature_inlet":   {"normal": (28, 40),     "warn": (40, 50),    "critical": (50, 70),    "unit": "°C"},
    "temperature_outlet":  {"normal": (18, 28),     "warn": (28, 35),    "critical": (35, 50),    "unit": "°C"},
    "temperature_cooling": {"normal": (25, 45),     "warn": (45, 60),    "critical": (60, 90),    "unit": "°C"},
    "flow_rate_gas":       {"normal": (3000, 5000), "warn": (2000, 3000),"critical": (500, 2000), "unit": "Nm³/h"},
    "speed_belt":          {"normal": (1.5, 3.0),   "warn": (0.8, 1.5),  "critical": (0.2, 0.8),  "unit": "m/s"},
}

RISK_LEVELS = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
MAINTENANCE_TYPES = ["Corrective", "Preventive", "Predictive", "Emergency"]
SHIFT_COLORS = {"normal": "#00C49A", "warn": "#FFBB28", "critical": "#FF4444", "offline": "#888888"}
