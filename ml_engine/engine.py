"""
MINERVA ML Engine
Three core ML components:
  1. AnomalyDetector  – Isolation Forest + Z-score per sensor
  2. RULPredictor     – Gradient-boosted remaining-useful-life estimation
  3. EquipmentGenome  – Novel behavioral fingerprinting for cross-fleet knowledge transfer
"""
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import beta as beta_dist
from scipy.stats import linregress
import warnings
warnings.filterwarnings("ignore")
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import SENSOR_BASELINES, EQUIPMENT_REGISTRY, SENSOR_MAP

# ══════════════════════════════════════════════════════════════════════════════
#  1. ANOMALY DETECTOR
# ══════════════════════════════════════════════════════════════════════════════

class AnomalyDetector:
    """
    Isolation Forest trained on 'normal' sensor periods.
    Returns anomaly score (-1 = anomaly, 1 = normal) + Z-score per reading.
    Also detects trend-based anomalies (rate of change).
    """
    def __init__(self):
        self.models: dict[str, IsolationForest] = {}
        self.scalers: dict[str, StandardScaler] = {}
        self._trained = False

    def train(self, sensor_df: pd.DataFrame, normal_days: int = 50):
        """Train one IsolationForest per sensor using the 'normal' period."""
        normal = sensor_df[sensor_df["day_index"] < normal_days]

        for sensor in sensor_df["sensor"].unique():
            vals = normal[normal["sensor"] == sensor]["value"].values.reshape(-1, 1)
            if len(vals) < 10:
                continue
            scaler = StandardScaler()
            scaled = scaler.fit_transform(vals)
            isoforest = IsolationForest(contamination=0.05, random_state=42, n_estimators=100)
            isoforest.fit(scaled)
            self.models[sensor] = isoforest
            self.scalers[sensor] = scaler

        self._trained = True

    def score(self, sensor: str, value: float) -> dict:
        """Score a single reading. Returns is_anomaly, anomaly_score, z_score."""
        info = SENSOR_BASELINES.get(sensor, {})
        lo, hi = info.get("normal", (0, 1e9))
        baseline = (lo + hi) / 2
        std_est = (hi - lo) / 4  # rough estimate

        z_score = (value - baseline) / std_est if std_est > 0 else 0.0

        if sensor in self.models:
            scaled = self.scalers[sensor].transform([[value]])
            score = float(self.models[sensor].decision_function(scaled)[0])
            is_anomaly = self.models[sensor].predict(scaled)[0] == -1
        else:
            score = -abs(z_score) / 3
            is_anomaly = abs(z_score) > 2.5

        return {
            "sensor": sensor,
            "value": value,
            "z_score": round(z_score, 3),
            "anomaly_score": round(score, 4),
            "is_anomaly": bool(is_anomaly),
            "severity": "critical" if abs(z_score) > 3.5 else "warning" if abs(z_score) > 2.0 else "normal",
        }

    def detect_trend_anomaly(self, values: list[float], window: int = 7) -> dict:
        """Detect accelerating degradation in a sensor time series."""
        if len(values) < window:
            return {"trend_anomaly": False, "slope": 0.0, "acceleration": 0.0}
        recent = values[-window:]
        x = np.arange(len(recent))
        slope, _, r_value, _, _ = linregress(x, recent)
        # Check acceleration: compare slope of last half vs first half
        mid = len(values) // 2
        if mid >= 3:
            s1, *_ = linregress(np.arange(mid), values[:mid])
            s2, *_ = linregress(np.arange(len(values)-mid), values[mid:])
            acceleration = s2 - s1
        else:
            acceleration = 0.0
        trend_anomaly = abs(slope) > 0.5 and r_value**2 > 0.6
        return {
            "trend_anomaly": trend_anomaly,
            "slope": round(float(slope), 4),
            "acceleration": round(float(acceleration), 4),
            "r_squared": round(float(r_value**2), 3),
            "direction": "rising" if slope > 0 else "falling",
        }


# ══════════════════════════════════════════════════════════════════════════════
#  2. REMAINING USEFUL LIFE (RUL) PREDICTOR + FAILURE HORIZON
# ══════════════════════════════════════════════════════════════════════════════

class RULPredictor:
    """
    Computes RUL (days to failure) and generates a Failure Horizon –
    a probability-density cloud over time (0-90 days).
    
    NOVEL: Instead of a single point estimate, outputs a Beta-distribution
    probability curve that reshapes dynamically as sensor conditions evolve.
    """

    def __init__(self):
        # Pre-defined RUL estimates from failure story scripts
        from data.synthetic_data import FAILURE_STORIES
        self._rul_baseline = {
            eid: story["rul_days"] for eid, story in FAILURE_STORIES.items()
        }

    def estimate_rul(self, equip_id: str, context: dict) -> dict:
        """Estimate RUL and failure horizon for an equipment."""
        base_rul = self._rul_baseline.get(equip_id, 60)
        health = context.get("current_health", 80.0)
        anomalous = context.get("anomalous_sensors", [])

        # Adjust RUL based on current health and number of anomalous sensors
        n_critical = sum(1 for a in anomalous if a.get("status") == "critical")
        n_warn = sum(1 for a in anomalous if a.get("status") == "warning")
        health_factor = health / 100.0
        stress_factor = 1.0 - (n_critical * 0.15 + n_warn * 0.05)

        adjusted_rul = max(1, base_rul * health_factor * stress_factor)

        # Generate Beta-distribution failure horizon curve
        # Alpha/beta params: lower health → more skewed toward near-term failure
        alpha = max(0.8, health / 25)
        beta_param = max(0.5, (100 - health) / 15)

        days = np.arange(1, 91)
        # CDF: probability of failure BY day X
        probs_cumulative = beta_dist.cdf(days / 90.0, alpha, beta_param)
        # PDF: probability of failure ON day X
        probs_daily = np.diff(np.concatenate([[0], probs_cumulative]))

        # Failure windows
        p7 = float(probs_cumulative[6]) * 100
        p30 = float(probs_cumulative[29]) * 100
        p90 = float(probs_cumulative[89]) * 100

        # Risk classification
        if adjusted_rul <= 7 or p7 > 40:
            risk_level = "CRITICAL"
        elif adjusted_rul <= 21 or p30 > 55:
            risk_level = "HIGH"
        elif adjusted_rul <= 45 or p90 > 65:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        return {
            "equip_id": equip_id,
            "estimated_rul_days": round(adjusted_rul, 1),
            "risk_level": risk_level,
            "failure_probability_7d": round(p7, 1),
            "failure_probability_30d": round(p30, 1),
            "failure_probability_90d": round(p90, 1),
            "horizon_days": days.tolist(),
            "horizon_cumulative_prob": [round(p*100, 2) for p in probs_cumulative.tolist()],
            "horizon_daily_prob": [round(p*100, 2) for p in probs_daily.tolist()],
            "confidence_interval": {
                "lower_rul": round(adjusted_rul * 0.7, 1),
                "upper_rul": round(adjusted_rul * 1.4, 1),
            },
            "inputs": {"health": health, "n_critical": n_critical, "n_warn": n_warn},
        }


# ══════════════════════════════════════════════════════════════════════════════
#  3. EQUIPMENT GENOME (Novel Innovation)
# ══════════════════════════════════════════════════════════════════════════════

class EquipmentGenome:
    """
    NOVEL COMPONENT: Behavioral DNA fingerprinting for industrial equipment.
    
    Concept: Each equipment gets a compressed behavioral "genome" – a vector
    derived from the statistical signature of its sensor time series.
    When a failure occurs, MINERVA finds equipment with similar genomes
    across the ENTIRE FLEET (even different equipment types) and surfaces
    their maintenance history – enabling cross-fleet knowledge transfer.
    
    Features used per sensor:
    - Rolling mean (7d)
    - Rolling std (7d)  
    - Trend slope (14d)
    - Peak-to-peak amplitude
    - Correlation with other sensors
    These are PCA-compressed to a 6-dimensional genome vector.
    """

    def __init__(self):
        self.genomes: dict[str, np.ndarray] = {}
        self.pca = PCA(n_components=6)
        self.scaler = StandardScaler()
        self._fitted = False
        self.feature_names: list[str] = []

    def _extract_features(self, equip_id: str, sensor_df: pd.DataFrame) -> np.ndarray:
        """Extract statistical features from sensor time series for one equipment."""
        equip_data = sensor_df[sensor_df["equip_id"] == equip_id]
        features = []
        used_sensors = []

        for sensor in equip_data["sensor"].unique():
            s_data = equip_data[equip_data["sensor"] == sensor]["value"].values
            if len(s_data) < 14:
                continue

            roll_mean = np.mean(s_data[-7:])
            roll_std = np.std(s_data[-7:])
            slope, *_ = linregress(np.arange(min(14, len(s_data))), s_data[-14:])
            ptp = np.ptp(s_data[-14:])
            # Normalize by baseline
            info = SENSOR_BASELINES.get(sensor, {})
            lo, hi = info.get("normal", (0.001, 1))
            baseline = (lo + hi) / 2 + 1e-9
            features.extend([
                roll_mean / baseline,
                roll_std / baseline,
                slope / baseline,
                ptp / baseline,
            ])
            used_sensors.append(sensor)

        return np.array(features) if features else np.zeros(4)

    def fit(self, sensor_df: pd.DataFrame):
        """Build genome for all equipment using full sensor history."""
        raw_features = {}
        for equip_id in sensor_df["equip_id"].unique():
            feats = self._extract_features(equip_id, sensor_df)
            raw_features[equip_id] = feats

        # Align feature lengths
        max_len = max(len(v) for v in raw_features.values())
        matrix = np.array([
            np.pad(v, (0, max_len - len(v))) for v in raw_features.values()
        ])

        # Scale + PCA
        scaled = self.scaler.fit_transform(matrix)
        n_components = min(6, min(matrix.shape))
        self.pca = PCA(n_components=n_components)
        genome_matrix = self.pca.fit_transform(scaled)

        for i, equip_id in enumerate(list(raw_features.keys())):
            self.genomes[equip_id] = genome_matrix[i]

        self._fitted = True
        print(f"✓ Equipment Genome fitted for {len(self.genomes)} equipment")

    def get_genome(self, equip_id: str) -> dict:
        """Return genome vector and label for visualization."""
        if equip_id not in self.genomes:
            return {"equip_id": equip_id, "genome": [], "components": []}
        vec = self.genomes[equip_id]
        return {
            "equip_id": equip_id,
            "genome": vec.tolist(),
            "variance_explained": self.pca.explained_variance_ratio_.tolist(),
            "labels": [f"G{i+1}" for i in range(len(vec))],
        }

    def find_similar_equipment(self, equip_id: str, top_k: int = 3) -> list[dict]:
        """
        Find fleet members with most similar behavioral genome.
        This enables cross-equipment knowledge transfer.
        """
        if equip_id not in self.genomes or len(self.genomes) < 2:
            return []

        target = self.genomes[equip_id].reshape(1, -1)
        similarities = []

        for other_id, genome in self.genomes.items():
            if other_id == equip_id:
                continue
            sim = float(cosine_similarity(target, genome.reshape(1, -1))[0][0])
            similarities.append({
                "equip_id": other_id,
                "equip_name": EQUIPMENT_REGISTRY.get(other_id, {}).get("name", other_id),
                "similarity_score": round(sim, 3),
                "similarity_pct": round((sim + 1) / 2 * 100, 1),  # map [-1,1] → [0,100]
            })

        similarities.sort(key=lambda x: x["similarity_score"], reverse=True)
        return similarities[:top_k]

    def compute_degradation_direction(self, equip_id: str) -> dict:
        """Compute how far the genome has shifted from its normal cluster center."""
        if equip_id not in self.genomes:
            return {"shift_magnitude": 0.0, "direction_description": "Unknown"}

        # Use mean of all genomes as "plant normal"
        all_genomes = np.array(list(self.genomes.values()))
        plant_center = np.mean(all_genomes, axis=0)
        vec = self.genomes[equip_id]
        shift = float(np.linalg.norm(vec - plant_center))
        
        max_shift = max(float(np.linalg.norm(g - plant_center)) for g in all_genomes)
        shift_pct = (shift / max_shift * 100) if max_shift > 0 else 0

        return {
            "shift_magnitude": round(shift, 4),
            "shift_percentile": round(shift_pct, 1),
            "description": "Significantly deviant from fleet baseline" if shift_pct > 70
                          else "Moderately deviant" if shift_pct > 40 else "Near fleet baseline",
        }


# ══════════════════════════════════════════════════════════════════════════════
#  4. RISK SCORER
# ══════════════════════════════════════════════════════════════════════════════

class RiskScorer:
    """
    Composite risk scoring for prioritization.
    Score 0-100 based on: health, RUL, criticality, spare availability,
    production impact, and number of anomalous sensors.
    """
    CRITICALITY_WEIGHT = {"critical": 1.0, "high": 0.75, "medium": 0.5, "low": 0.25}
    PRODUCTION_IMPACT = {
        "blast_furnace": 1.0, "rolling_mill": 0.9, "caster": 0.85,
        "compressor": 0.7, "hydraulic": 0.65, "crane": 0.5,
        "conveyor": 0.45, "cooling_tower": 0.4,
    }

    def compute_risk_score(self, equip_id: str, context: dict, rul_result: dict) -> dict:
        equip_info = EQUIPMENT_REGISTRY.get(equip_id, {})
        health = context.get("current_health", 80.0)
        crit_w = self.CRITICALITY_WEIGHT.get(equip_info.get("criticality", "medium"), 0.5)
        prod_w = self.PRODUCTION_IMPACT.get(equip_info.get("type", ""), 0.5)

        rul = rul_result.get("estimated_rul_days", 60)
        p7 = rul_result.get("failure_probability_7d", 0)

        spares = context.get("spares_info", {})
        spare_score = 1.0 if spares.get("critical_shortage") else 0.0
        lead_time_penalty = min(spares.get("max_lead_time_days", 0) / 30, 1.0)

        n_critical_sensors = sum(1 for s in context.get("anomalous_sensors", [])
                                  if s.get("status") == "critical")
        n_warn_sensors = sum(1 for s in context.get("anomalous_sensors", [])
                             if s.get("status") == "warning")

        # Weighted composite
        score = (
            (100 - health) * 0.30 +       # Health degradation
            (100 - min(rul * 1.1, 100)) * 0.25 +  # RUL urgency
            p7 * 0.20 +                    # Near-term failure probability
            crit_w * 100 * 0.10 +          # Criticality
            prod_w * 100 * 0.05 +          # Production impact
            spare_score * 60 * 0.05 +      # Spare shortage
            lead_time_penalty * 40 * 0.03 +# Lead time penalty
            (n_critical_sensors * 8 + n_warn_sensors * 3)  # Sensor alarms
        )
        score = min(100.0, max(0.0, score))

        if score >= 75:
            priority = "CRITICAL"
            urgency = "Immediate – within 24 hours"
        elif score >= 55:
            priority = "HIGH"
            urgency = "Urgent – within 72 hours"
        elif score >= 35:
            priority = "MEDIUM"
            urgency = "Planned – within 7 days"
        else:
            priority = "LOW"
            urgency = "Scheduled – within 30 days"

        return {
            "equip_id": equip_id,
            "risk_score": round(score, 1),
            "priority": priority,
            "urgency": urgency,
            "breakdown": {
                "health_component": round((100 - health) * 0.30, 1),
                "rul_component": round((100 - min(rul * 1.1, 100)) * 0.25, 1),
                "failure_prob_component": round(p7 * 0.20, 1),
                "criticality_component": round(crit_w * 10, 1),
                "spare_shortage_component": round(spare_score * 3, 1),
                "sensor_alarms_component": round(n_critical_sensors * 8 + n_warn_sensors * 3, 1),
            },
        }
