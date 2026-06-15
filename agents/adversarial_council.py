"""
MINERVA Adversarial Diagnosis Council
NOVEL COMPONENT: Three-agent adversarial reasoning system.

Instead of a single LLM answer (which engineers distrust), three specialized agents
argue, challenge, and adjudicate — making the reasoning transparent and trustworthy.

    DR. FORWARD  (Hypothesis Agent) – proposes the most likely failure mode with evidence
    DR. CHALLENGE (Skeptic Agent)   – finds counter-evidence and alternative hypotheses
    DR. VERDICT   (Arbitrator)      – weighs the debate and renders a confidence-ranked verdict

The debate transcript IS the explainability layer. Engineers see WHY the system
chose one diagnosis over another, not just the conclusion.
"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import ANTHROPIC_API_KEY, CLAUDE_MODEL, DEMO_MODE

# ── Pre-baked council debates for demo mode ───────────────────────────────────
DEMO_COUNCILS = {
    "RM-2": {
        "hypothesis": {
            "agent": "Dr. Forward (Hypothesis Agent)",
            "primary_failure_mode": "Outer Race Bearing Damage (BPFO)",
            "confidence": 74,
            "evidence": [
                "Vibration RMS: 7.3 mm/s (critical threshold 7.0) — consistent with advanced bearing defect",
                "BPFO frequency at 3.2 kHz confirmed in spectral data — this is the definitive bearing outer race signature",
                "Bearing temperature: 89°C (warning) — thermal signature consistent with increased friction from damaged race",
                "Historical match: FR-2024-031 (March 2024) — identical vibration+temperature pattern preceded confirmed outer race failure in same equipment",
                "Progression rate: vibration doubled in 14 days — exponential growth characteristic of rolling element bearing failure",
            ],
            "proposed_action": "Emergency bearing inspection and replacement (SOP-RM-042). Shutdown within 48 hours.",
        },
        "skeptic": {
            "agent": "Dr. Challenge (Skeptic Agent)",
            "counter_evidence": [
                "Oil analysis from last service (15 days ago) showed viscosity within normal range — if bearing damage were this advanced, we'd expect metallic particle contamination in oil",
                "Motor current increased only 12% above baseline — more severe bearing damage typically causes 20-30% current increase at this vibration level",
                "No acoustic anomaly reported by operators in last shift walk-around log",
            ],
            "alternative_hypotheses": [
                {
                    "mode": "Shaft Misalignment (Progressive)",
                    "confidence": 22,
                    "rationale": "Last alignment check was 180 days ago. Misalignment at 1x/2x frequencies can mimic bearing vibration. Explain current motor current increase.",
                },
                {
                    "mode": "Coupling Wear",
                    "confidence": 9,
                    "rationale": "Coupling inspection was not part of recent PM. Worn coupling teeth can generate high-frequency vibration signatures.",
                },
            ],
            "recommended_additional_checks": [
                "Oil sample analysis (metallic particle count) — results available same day",
                "Time waveform analysis to distinguish bearing defect from misalignment",
            ],
        },
        "verdict": {
            "agent": "Dr. Verdict (Arbitrator)",
            "final_diagnosis": "Outer Race Bearing Damage — HIGH confidence",
            "probability_ranking": [
                {"mode": "Outer Race Bearing Damage", "probability": 68, "action": "Primary action"},
                {"mode": "Shaft Misalignment", "probability": 24, "action": "Secondary check during bearing replacement"},
                {"mode": "Coupling Wear", "probability": 8, "action": "Visual inspection only"},
            ],
            "arbitration_reasoning": "The skeptic raises valid points about oil analysis, but the BPFO spectral signature at exactly 3.2 kHz is highly specific for outer race damage and cannot be explained by misalignment alone. Oil analysis lag is expected — bearing surface spalling typically precedes oil contamination by 7-14 days. The exponential vibration growth rate (consistent with bearing failure cascade) combined with the exact historical match from FR-2024-031 tips the balance decisively toward bearing damage. Misalignment cannot be ruled out and should be checked simultaneously.",
            "confidence_in_primary": 68,
            "immediate_actions": [
                "Issue work permit for RM-2 bearing inspection (SOP-RM-042) — within 48 hours",
                "Pre-order SKF-6312-C3 bearing (2 units) — 2 in stock, sufficient",
                "During teardown: check coupling and shaft alignment as secondary check",
                "Collect oil sample NOW for same-day analysis",
            ],
            "long_term_actions": [
                "Revert lubrication interval to 200 hours (was extended to 300h)",
                "Add BPFO spectral monitoring to weekly vibration route",
                "Schedule alignment check in 30 days after bearing replacement",
            ],
            "sop_references": ["SOP-RM-042 (Bearing Replacement)", "SOP-GEN-001 (Work Order Priority)"],
            "knowledge_base_citations": ["FR-2024-031 (March 2024 bearing failure, same equipment)", "RM-MAN-001 (Bearing inspection thresholds)"],
        },
    },
    "BF-1": {
        "hypothesis": {
            "agent": "Dr. Forward (Hypothesis Agent)",
            "primary_failure_mode": "Cooling Circuit Scale Fouling",
            "confidence": 71,
            "evidence": [
                "Flow rate declining 15% over 20 days — consistent with progressive scale deposition",
                "Cooling outlet temperature rising 8°C above normal differential — reduced heat transfer capacity",
                "Inspection 30 days ago found scale deposits in cooling lines",
                "Pattern matches known fouling progression in BF cooling circuits",
            ],
            "proposed_action": "Chemical cleaning of affected cooling circuits per SOP-BF-015 within 2 weeks.",
        },
        "skeptic": {
            "agent": "Dr. Challenge (Skeptic Agent)",
            "counter_evidence": [
                "Water treatment records show correct biocide and scale inhibitor dosing",
                "Flow reduction could also indicate partial valve closure or pump wear",
            ],
            "alternative_hypotheses": [
                {"mode": "Pump Wear / Impeller Damage", "confidence": 18, "rationale": "Pump efficiency not recently checked — degraded impeller would reduce flow similarly"},
                {"mode": "Partial Control Valve Fault", "confidence": 11, "rationale": "Valve positioners can drift, causing partial closure"},
            ],
            "recommended_additional_checks": ["Pump discharge pressure check to isolate pump vs circuit blockage"],
        },
        "verdict": {
            "agent": "Dr. Verdict (Arbitrator)",
            "final_diagnosis": "Cooling Circuit Scale Fouling — MEDIUM-HIGH confidence",
            "probability_ranking": [
                {"mode": "Scale Fouling", "probability": 68, "action": "Primary action: chemical cleaning"},
                {"mode": "Pump Wear", "probability": 21, "action": "Check pump pressure during cleaning"},
                {"mode": "Valve Fault", "probability": 11, "action": "Verify valve position"},
            ],
            "arbitration_reasoning": "Prior inspection evidence of scale deposits combined with progressive flow reduction is most consistent with fouling. Water treatment compliance reduces biological fouling risk but does not prevent mineral scale in high-temperature zones.",
            "confidence_in_primary": 68,
            "immediate_actions": ["Schedule cooling circuit inspection", "Measure pump discharge pressure"],
            "long_term_actions": ["Increase descaling frequency", "Add flow rate alert at -10% from baseline"],
            "sop_references": ["SOP-BF-015 (Cooling Circuit Cleaning)"],
            "knowledge_base_citations": ["BF-MAN-001 (Cooling system maintenance)"],
        },
    },
}

GENERIC_DEMO = {
    "hypothesis": {
        "agent": "Dr. Forward (Hypothesis Agent)",
        "primary_failure_mode": "Degradation Pattern Detected",
        "confidence": 65,
        "evidence": ["Sensor readings trending outside normal range", "Historical patterns suggest component wear"],
        "proposed_action": "Inspection and targeted maintenance recommended.",
    },
    "skeptic": {
        "agent": "Dr. Challenge (Skeptic Agent)",
        "counter_evidence": ["Insufficient data for definitive diagnosis"],
        "alternative_hypotheses": [{"mode": "Transient operational condition", "confidence": 35, "rationale": "Could be load-related variation"}],
        "recommended_additional_checks": ["Collect additional sensor data", "Manual inspection"],
    },
    "verdict": {
        "agent": "Dr. Verdict (Arbitrator)",
        "final_diagnosis": "Monitoring Recommended",
        "probability_ranking": [{"mode": "Component Wear", "probability": 65, "action": "Inspect and plan maintenance"}],
        "arbitration_reasoning": "Limited data available. Recommend targeted inspection to confirm diagnosis.",
        "confidence_in_primary": 65,
        "immediate_actions": ["Manual inspection", "Increase monitoring frequency"],
        "long_term_actions": ["Review maintenance schedule"],
        "sop_references": ["SOP-GEN-001"],
        "knowledge_base_citations": [],
    },
}


def run_adversarial_council(equip_id: str, context: dict, kb_results: list) -> dict:
    """
    Run the full 3-agent adversarial council on an equipment.
    Returns hypothesis, skeptic challenge, and final verdict.
    """
    if DEMO_MODE or not ANTHROPIC_API_KEY:
        return _demo_council(equip_id)
    return _llm_council(equip_id, context, kb_results)


def _demo_council(equip_id: str) -> dict:
    council = DEMO_COUNCILS.get(equip_id, GENERIC_DEMO)
    return {
        "equip_id": equip_id,
        "mode": "demo",
        "hypothesis": council["hypothesis"],
        "skeptic": council["skeptic"],
        "verdict": council["verdict"],
        "council_summary": _format_council_summary(council),
    }


def _llm_council(equip_id: str, context: dict, kb_results: list) -> dict:
    """Full 3-call LLM adversarial council."""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    equip_name = context.get("equip_name", equip_id)
    equip_type = context.get("equip_type", "")
    anomalous = context.get("anomalous_sensors", [])
    history = context.get("maintenance_history", [])
    health = context.get("current_health", 80)

    kb_text = "\n---\n".join(r.get("content", "")[:400] for r in kb_results[:3])

    base_context = f"""
EQUIPMENT: {equip_name} ({equip_id}) | Type: {equip_type} | Health: {health:.0f}%

CURRENT ANOMALOUS SENSORS:
{json.dumps(anomalous, indent=2)}

SENSOR TRENDS (7d slope):
{json.dumps(context.get('sensor_trends_7d', {}), indent=2)}

RECENT MAINTENANCE HISTORY:
{json.dumps(history, indent=2)}

RELEVANT KNOWLEDGE BASE:
{kb_text}
"""

    # ── Call 1: Hypothesis Agent ───────────────────────────────────────────────
    hypothesis_prompt = f"""You are Dr. Forward, the Hypothesis Agent in the MINERVA Adversarial Diagnosis Council.
Your role: Propose the MOST LIKELY failure mode with supporting evidence. Be bold and specific.

{base_context}

Respond ONLY in JSON (no preamble):
{{
  "agent": "Dr. Forward (Hypothesis Agent)",
  "primary_failure_mode": "specific failure mode name",
  "confidence": 0-100,
  "evidence": ["specific evidence 1 with values", "evidence 2", "evidence 3", "evidence 4"],
  "proposed_action": "specific action with SOP reference if applicable"
}}"""

    h_resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=600,
                                     messages=[{"role": "user", "content": hypothesis_prompt}])
    hypothesis = _safe_parse(h_resp.content[0].text)

    # ── Call 2: Skeptic Agent ──────────────────────────────────────────────────
    skeptic_prompt = f"""You are Dr. Challenge, the Skeptic Agent in the MINERVA Adversarial Diagnosis Council.
Your role: CHALLENGE the hypothesis. Find counter-evidence. Propose alternatives. Be rigorous.

{base_context}

HYPOTHESIS TO CHALLENGE:
{json.dumps(hypothesis, indent=2)}

Respond ONLY in JSON:
{{
  "agent": "Dr. Challenge (Skeptic Agent)",
  "counter_evidence": ["specific counter-evidence 1", "counter-evidence 2"],
  "alternative_hypotheses": [
    {{"mode": "Alternative 1", "confidence": 0-100, "rationale": "why this could explain the data"}},
    {{"mode": "Alternative 2", "confidence": 0-100, "rationale": "rationale"}}
  ],
  "recommended_additional_checks": ["check 1", "check 2"]
}}"""

    s_resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=600,
                                     messages=[{"role": "user", "content": skeptic_prompt}])
    skeptic = _safe_parse(s_resp.content[0].text)

    # ── Call 3: Arbitrator ─────────────────────────────────────────────────────
    arbitrator_prompt = f"""You are Dr. Verdict, the Arbitrator in the MINERVA Adversarial Diagnosis Council.
Your role: Weigh the hypothesis against the skeptic's challenge. Render a final, actionable verdict.

{base_context}

HYPOTHESIS (Dr. Forward):
{json.dumps(hypothesis, indent=2)}

SKEPTIC'S CHALLENGE (Dr. Challenge):
{json.dumps(skeptic, indent=2)}

Respond ONLY in JSON:
{{
  "agent": "Dr. Verdict (Arbitrator)",
  "final_diagnosis": "diagnosis with confidence level",
  "probability_ranking": [
    {{"mode": "failure mode", "probability": 0-100, "action": "what to do about it"}}
  ],
  "arbitration_reasoning": "2-3 sentence explanation of why you weighed the evidence this way",
  "confidence_in_primary": 0-100,
  "immediate_actions": ["action 1", "action 2", "action 3"],
  "long_term_actions": ["long-term action 1", "action 2"],
  "sop_references": ["SOP references"],
  "knowledge_base_citations": ["relevant documents cited"]
}}"""

    a_resp = client.messages.create(model=CLAUDE_MODEL, max_tokens=800,
                                     messages=[{"role": "user", "content": arbitrator_prompt}])
    verdict = _safe_parse(a_resp.content[0].text)

    council = {"hypothesis": hypothesis, "skeptic": skeptic, "verdict": verdict}
    return {
        "equip_id": equip_id,
        "mode": "live",
        "hypothesis": hypothesis,
        "skeptic": skeptic,
        "verdict": verdict,
        "council_summary": _format_council_summary(council),
    }


def _safe_parse(text: str) -> dict:
    """Safely parse LLM JSON response."""
    text = text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw_response": text[:500], "parse_error": True}


def _format_council_summary(council: dict) -> str:
    """Generate a human-readable summary of the council debate."""
    h = council.get("hypothesis", {})
    s = council.get("skeptic", {})
    v = council.get("verdict", {})

    lines = []
    lines.append(f"**Hypothesis:** {h.get('primary_failure_mode', 'N/A')} "
                 f"(confidence: {h.get('confidence', '?')}%)")
    alts = s.get("alternative_hypotheses", [])
    if alts:
        lines.append(f"**Skeptic raised:** {alts[0].get('mode', '')} as alternative "
                     f"({alts[0].get('confidence', '?')}% probability)")
    lines.append(f"**Final verdict:** {v.get('final_diagnosis', 'N/A')}")
    actions = v.get("immediate_actions", [])
    if actions:
        lines.append(f"**Top action:** {actions[0]}")
    return " | ".join(lines)
