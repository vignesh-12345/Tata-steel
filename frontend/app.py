"""
MINERVA Frontend v2 — Clean, simple, focused
Navigation: Overview | Diagnose | Alerts | Logbook
"""
import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np
from datetime import datetime
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import EQUIPMENT_REGISTRY, SENSOR_BASELINES

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="MINERVA", page_icon="⚙️",
                   layout="wide", initial_sidebar_state="expanded")

# ── CSS — minimal, clean ──────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp, [data-testid="stAppViewContainer"] { background:#0f1117 }
  [data-testid="stSidebarContent"] { background:#0a0d14 }
  [data-testid="stSidebarContent"] * { color:#e0e0e0 }

  /* Cards */
  .card {
    background:rgba(255,255,255,0.04);
    border:1px solid rgba(255,255,255,0.08);
    border-radius:12px; padding:16px 20px; margin-bottom:10px;
  }
  .card-metric { text-align:center }
  .val  { font-size:32px; font-weight:700; line-height:1.1; font-family:Arial,sans-serif }
  .lbl  { font-size:11px; color:#777; text-transform:uppercase; letter-spacing:.08em; margin-top:4px }

  /* Status tags */
  .tag { display:inline-block; padding:2px 9px; border-radius:12px; font-size:11px; font-weight:600 }
  .t-critical { background:#3d0000; color:#ff4444 }
  .t-high     { background:#2d1500; color:#ff8c00 }
  .t-medium   { background:#2d2800; color:#ffbb28 }
  .t-warning  { background:#2d2800; color:#ffbb28 }
  .t-low, .t-normal { background:#0d2a1a; color:#00c49a }

  /* Agent debate cards */
  .agent { border-radius:10px; padding:14px 16px; margin-bottom:10px }
  .a-h { background:rgba(30,144,255,.08); border-left:3px solid #1e90ff }
  .a-s { background:rgba(255,107,53,.08); border-left:3px solid #ff6b35 }
  .a-v { background:rgba(0,196,154,.08);  border-left:3px solid #00c49a }

  /* Action items */
  .act { background:rgba(0,196,154,.06); border-left:3px solid #00c49a;
         padding:10px 14px; border-radius:0 8px 8px 0; margin:5px 0; font-size:13px }

  /* Timeline */
  .tl  { padding:7px 0; border-bottom:1px solid rgba(255,255,255,.05); font-size:13px }

  /* Progress bar */
  .bar-outer { background:rgba(255,255,255,.08); border-radius:3px; height:4px; margin-top:7px }
</style>
""", unsafe_allow_html=True)

# ── Session state ─────────────────────────────────────────────────────────────
defaults = dict(page="🏠 Overview", equip="RM-2",
                result=None, result_equip=None)
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ── Helpers ───────────────────────────────────────────────────────────────────
def hcolor(s):
    return "#ff4444" if s < 40 else "#ffbb28" if s < 70 else "#00c49a"

def hlabel(s):
    return "Critical" if s < 40 else "Warning" if s < 70 else "Normal"

def tag(text, level="normal"):
    lvl = (level or "normal").lower()
    return f'<span class="tag t-{lvl}">{text}</span>'

@st.cache_resource(show_spinner="Starting MINERVA…")
def get_orch():
    from agents.orchestrator import get_orchestrator
    return get_orchestrator()

@st.cache_data(ttl=60, show_spinner=False)
def plant_health():
    from database.db_manager import get_all_latest_health
    return {h["equip_id"]: h["health_score"] for h in get_all_latest_health()}

@st.cache_data(ttl=30, show_spinner=False)
def latest_sensors(equip_id):
    from database.db_manager import get_latest_readings
    return get_latest_readings(equip_id)

@st.cache_data(ttl=30, show_spinner=False)
def sensor_trend(equip_id, sensor, days=30):
    from database.db_manager import get_sensor_history
    return get_sensor_history(equip_id, sensor, days)

# ── SIDEBAR ───────────────────────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("## ⚙️ MINERVA")
        st.caption("Maintenance Intelligence System")
        st.divider()

        page = st.radio("Navigation", ["🏠 Overview","🔍 Diagnose","⚠️ Alerts","📓 Logbook"],
                        label_visibility="collapsed")
        st.session_state.page = page
        st.divider()

        st.markdown("**Equipment**")
        opts = {f"{eid} — {info['name']}": eid for eid, info in EQUIPMENT_REGISTRY.items()}
        sel = st.selectbox("Select Equipment", list(opts.keys()),
                           index=list(opts.values()).index(st.session_state.equip),
                           label_visibility="collapsed")
        new_eq = opts[sel]
        if new_eq != st.session_state.equip:
            st.session_state.equip = new_eq
            st.session_state.result = None
            st.rerun()

        # Health badge
        hm = plant_health()
        score = hm.get(new_eq, 80)
        c = hcolor(score)
        st.markdown(f"""
        <div style="text-align:center;padding:16px;background:rgba(255,255,255,.04);
                    border-radius:10px;margin-top:8px;border:1px solid rgba(255,255,255,.08)">
          <div style="font-size:44px;font-weight:700;color:{c};line-height:1">{score:.0f}<span style="font-size:16px">%</span></div>
          <div style="color:{c};font-size:12px;margin-top:3px">{hlabel(score)}</div>
        </div>""", unsafe_allow_html=True)

        # Alert badge
        try:
            from agents.alert_system import get_alert_summary
            s = get_alert_summary()
            n = s.get("total_active", 0)
            if n:
                st.markdown(f"""
                <div style="background:#2d0a0a;border-radius:8px;padding:8px 12px;
                            margin-top:8px;text-align:center">
                  <span style="color:#ff4444;font-weight:700">{n} Active Alert{'s' if n>1 else ''}</span>
                </div>""", unsafe_allow_html=True)
        except Exception:
            pass

# ── PAGE 1 — OVERVIEW ─────────────────────────────────────────────────────────
def page_overview():
    # ── Shift Briefing ─────────────────────────────────────────────────────
    try:
        from agents.briefing import generate_shift_briefing
        brief = generate_shift_briefing()

        priorities = brief.get("priorities", [])
        top = brief.get("top_item")

        pri_color = {"CRITICAL": "#ff4444", "HIGH": "#ff8c00",
                     "MEDIUM": "#ffbb28", "LOW": "#00c49a"}

        st.markdown(f"## ☀️ {brief['greeting']} — Shift Briefing")
        st.caption(brief["timestamp"])

        if top:
            tc = pri_color.get(top["priority"], "#888")
            st.markdown(f"""
            <div class="card" style="border-left:4px solid {tc};padding:16px 20px">
              <div style="font-size:11px;color:#777;font-weight:600;text-transform:uppercase;letter-spacing:.1em">Top Priority Right Now</div>
              <div style="font-size:20px;font-weight:700;color:{tc};margin:6px 0">{top["headline"]}</div>
              <div style="font-weight:600">{top["equip_name"]} ({top["equip_id"]})</div>
              {"<div style='color:#aaa;font-size:13px;margin-top:4px'>" + top["detail"] + "</div>" if top.get("detail") else ""}
              {"<div style='color:#ffbb28;font-size:12px;margin-top:8px'>📦 " + brief["parts_msg"] + "</div>" if brief.get("parts_msg") else ""}
            </div>""", unsafe_allow_html=True)
        else:
            st.success("✅ Plant operating normally — no immediate actions required")

        if len(priorities) > 1:
            with st.expander("See all shift priorities"):
                for item in priorities[1:]:
                    ic = pri_color.get(item["priority"], "#888")
                    st.markdown(f"""
                    <div class="card" style="border-left:3px solid {ic};padding:10px 14px">
                      <div style="font-weight:600;font-size:13px">{item["equip_name"]} ({item["equip_id"]})</div>
                      <div style="color:{ic};font-size:12px">{item["headline"]}</div>
                    </div>""", unsafe_allow_html=True)
        st.divider()
    except Exception as e:
        st.markdown("## 🏭 Plant Overview")

    hm = plant_health()
    vals = list(hm.values())
    avg = np.mean(vals) if vals else 80
    critical = sum(1 for s in vals if s < 40)
    warning  = sum(1 for s in vals if 40 <= s < 70)
    normal   = sum(1 for s in vals if s >= 70)

    c1, c2, c3, c4 = st.columns(4)
    for col, v, lbl, clr in [
        (c1, f"{avg:.0f}%", "Plant Health",    hcolor(avg)),
        (c2, critical,      "Critical",        "#ff4444"),
        (c3, warning,       "Warning",         "#ffbb28"),
        (c4, normal,        "Normal",          "#00c49a"),
    ]:
        with col:
            st.markdown(f"""<div class="card card-metric">
              <div class="val" style="color:{clr}">{v}</div>
              <div class="lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.divider()

    # Risk data
    try:
        orch = get_orch()
        risk_map = {r["equip_id"]: r for r in orch.get_plant_risk_ranking()}
    except Exception:
        risk_map = {}

    # Equipment grid
    st.markdown("### Equipment Health")
    equips = list(EQUIPMENT_REGISTRY.items())
    for row in range(0, len(equips), 4):
        cols = st.columns(4)
        for col, (eid, info) in zip(cols, equips[row:row+4]):
            sc = hm.get(eid, 80); c = hcolor(sc)
            rk = risk_map.get(eid, {})
            rul = rk.get("rul_days", 0)
            pri = rk.get("priority", "LOW")
            with col:
                st.markdown(f"""
                <div class="card" style="border-top:3px solid {c}">
                  <div style="font-weight:700;font-size:14px">{eid}</div>
                  <div style="color:#777;font-size:11px;margin-bottom:8px">{info['name']}</div>
                  <div style="font-size:30px;font-weight:700;color:{c}">{sc:.0f}<span style="font-size:13px;color:#888">%</span></div>
                  <div class="bar-outer"><div style="background:{c};width:{sc:.0f}%;height:100%;border-radius:3px"></div></div>
                  <div style="display:flex;justify-content:space-between;margin-top:8px;font-size:11px;color:#777">
                    <span>RUL {rul:.0f}d</span>
                    {tag(pri, pri)}
                  </div>
                </div>""", unsafe_allow_html=True)
                if st.button("Diagnose →", key=f"go_{eid}", use_container_width=True):
                    st.session_state.equip = eid
                    st.session_state.page = "🔍 Diagnose"
                    st.session_state.result = None
                    st.rerun()

    st.divider()

    # Top alerts
    st.markdown("### Active Alerts")
    try:
        from agents.alert_system import scan_and_generate_alerts, get_alerts
        scan_and_generate_alerts()
        alerts = get_alerts(status="active", limit=5)
        if not alerts:
            st.success("✅ No active alerts — all equipment normal")
        for a in alerts:
            sc = a.get("severity","HIGH")
            clr = {"CRITICAL":"#ff4444","HIGH":"#ff8c00","MEDIUM":"#ffbb28"}.get(sc,"#888")
            nm  = EQUIPMENT_REGISTRY.get(a.get("equip_id",""),{}).get("name","")
            st.markdown(f"""
            <div class="card" style="border-left:3px solid {clr}">
              <div style="display:flex;justify-content:space-between;align-items:center">
                <span>{tag(sc, sc)} &nbsp;<b>{a.get('title','')}</b></span>
                <span style="color:#666;font-size:11px">{a.get('equip_id','')} — {nm}</span>
              </div>
              <div style="color:#aaa;font-size:12px;margin-top:6px">{a.get('body','')[:160]}</div>
            </div>""", unsafe_allow_html=True)
    except Exception as e:
        st.warning(f"Alerts: {e}")

# ── PAGE 2 — DIAGNOSE ─────────────────────────────────────────────────────────
def page_diagnose():
    eid  = st.session_state.equip
    info = EQUIPMENT_REGISTRY.get(eid, {})
    st.markdown(f"## 🔍 {eid} — {info.get('name', eid)}")

    # Summary row
    hm = plant_health()
    sc = hm.get(eid, 80); c = hcolor(sc)
    try:
        orch = get_orch()
        from database.db_manager import build_equipment_context
        ctx  = build_equipment_context(eid)
        rul  = orch.rul_predictor.estimate_rul(eid, ctx)
        risk = orch.risk_scorer.compute_risk_score(eid, ctx, rul)
        rul_days = rul.get("estimated_rul_days", 60)
        p7       = rul.get("failure_probability_7d", 0)
        rscore   = risk.get("risk_score", 0)
        priority = risk.get("priority", "LOW")
        urgency  = risk.get("urgency", "")
    except Exception:
        rul_days, p7, rscore, priority, urgency = 60, 0, 0, "LOW", ""
        rul, risk, ctx = {}, {}, {}

    c1, c2, c3, c4 = st.columns(4)
    for col, v, lbl, clr in [
        (c1, f"{sc:.0f}%",         "Health Score",       c),
        (c2, f"{rul_days:.0f}d",   "Remaining Useful Life", c),
        (c3, f"{p7:.0f}%",         "Fail Prob (7 days)", "#ff4444" if p7>30 else "#ffbb28"),
        (c4, f"{rscore:.0f}/100",  f"Risk — {priority}", "#ff4444" if rscore>70 else "#ffbb28" if rscore>40 else "#00c49a"),
    ]:
        with col:
            st.markdown(f"""<div class="card card-metric">
              <div class="val" style="color:{clr}">{v}</div>
              <div class="lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    if urgency:
        uc = {"CRITICAL":"#ff4444","HIGH":"#ff8c00","MEDIUM":"#ffbb28","LOW":"#00c49a"}.get(priority,"#888")
        st.markdown(f"""<div class="card" style="border:1px solid {uc}">
          <b style="color:{uc}">{priority}</b> &nbsp;— {urgency}
        </div>""", unsafe_allow_html=True)

    st.divider()

    # Sensor readings
    st.markdown("### 📡 Sensor Readings")
    readings = latest_sensors(eid)
    if readings:
        cols = st.columns(3)
        for i, r in enumerate(readings):
            sens   = r.get("sensor","")
            val    = float(r.get("value", 0))
            status = r.get("status","normal")
            unit   = r.get("unit","")
            sinfo  = SENSOR_BASELINES.get(sens, {})
            lo, hi = sinfo.get("normal", (0,100))
            sc_c   = {"critical":"#ff4444","warning":"#ffbb28","normal":"#00c49a"}.get(status,"#888")
            fill   = max(0, min(100, (val-lo)/max(hi-lo,0.001)*100))

            with cols[i % 3]:
                st.markdown(f"""
                <div class="card" style="border-top:2px solid {sc_c}">
                  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
                    <span style="font-size:11px;color:#888;font-weight:600">{sens.upper().replace('_',' ')}</span>
                    {tag(status, status)}
                  </div>
                  <div style="font-size:26px;font-weight:700;color:{sc_c}">{val:.2f}
                    <span style="font-size:12px;color:#888">{unit}</span></div>
                  <div style="font-size:10px;color:#666;margin-top:2px">Normal: {lo}–{hi} {unit}</div>
                  <div class="bar-outer">
                    <div style="background:{sc_c};width:{fill:.0f}%;height:100%;border-radius:3px"></div>
                  </div>
                </div>""", unsafe_allow_html=True)

    st.divider()

    # Sensor trend chart
    from config import SENSOR_MAP
    equip_type = info.get("type","")
    sensors = SENSOR_MAP.get(equip_type, [])
    if sensors:
        with st.expander("📈 View Sensor Trend", expanded=False):
            chosen = st.selectbox("Sensor", sensors, key="trend_sensor")
            df = sensor_trend(eid, chosen, 30)
            if len(df) > 0:
                si = SENSOR_BASELINES.get(chosen, {})
                lo, hi = si.get("normal", (0,100))
                unit = si.get("unit","")
                fig = go.Figure()
                fig.add_hrect(y0=lo, y1=hi, fillcolor="rgba(0,196,154,.06)", line_width=0)
                fig.add_trace(go.Scatter(
                    x=df["date"], y=df["value"], mode="lines+markers",
                    line=dict(color="#1e90ff", width=2),
                    marker=dict(size=4, color=["#ff4444" if s=="critical" else "#ffbb28" if s=="warning" else "#1e90ff" for s in df["status"]]),
                    hovertemplate=f"%{{x}}: %{{y:.3f}} {unit}<extra></extra>",
                ))
                fig.update_layout(
                    title=f"{chosen} — 30-day trend",
                    height=280, margin=dict(l=40,r=20,t=40,b=30),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,22,30,.8)",
                    font_color="#ccc",
                    xaxis=dict(gridcolor="rgba(255,255,255,.06)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,.06)"),
                )
                st.plotly_chart(fig, use_container_width=True)

    st.divider()

    # AI Diagnosis
    st.markdown("### 🧠 AI Diagnosis")
    col_btn, col_info = st.columns([2, 5])
    with col_btn:
        run = st.button("⚡ Run Full Diagnosis", type="primary", use_container_width=True)
    with col_info:
        if st.session_state.result_equip == eid and st.session_state.result:
            st.success("✅ Analysis ready — see tabs below")
        else:
            st.caption("Runs: Adversarial Council · Temporal Archaeology · Failure Horizon · Risk Scoring")

    if run:
        with st.spinner("Running 3-agent adversarial diagnosis…"):
            try:
                orch = get_orch()
                res  = orch.process_query(f"Diagnose equipment issue for {eid}", eid)
                st.session_state.result       = res
                st.session_state.result_equip = eid
                st.rerun()
            except Exception as e:
                st.error(f"Diagnosis failed: {e}")

    res = st.session_state.result
    if res and st.session_state.result_equip == eid:
        t1, t2, t3, t4, t5, t6 = st.tabs([
            "⚖️ Council Debate", "🏛️ Causal Timeline",
            "📊 Failure Horizon", "⚡ Action Plan",
            "🔁 Past Incidents",  "💰 Business Case",
        ])
        with t1: _council(res.get("council",{}))
        with t2: _archaeology(res.get("archaeology",{}))
        with t3: _horizon(res.get("rul",{}), eid)
        with t4: _actions(res.get("council",{}), res.get("risk",{}), res.get("spares",{}))
        with t5: _pattern_matches(eid, res)
        with t6: _business_case(eid, res)

# ─── Diagnosis sub-renderers ─────────────────────────────────────────────────
def _council(council):
    if not council:
        st.info("Run diagnosis first.")
        return
    h = council.get("hypothesis", {}); s = council.get("skeptic", {}); v = council.get("verdict", {})

    ev_html = "".join(f"<div style='margin:3px 0;font-size:12px'>• {e}</div>" for e in h.get("evidence",[])[:4])
    st.markdown(f"""<div class="agent a-h">
      <div style="font-weight:700;color:#1e90ff;margin-bottom:8px">🔵 DR. FORWARD — HYPOTHESIS</div>
      <div style="margin-bottom:4px"><b>Diagnosis:</b> {h.get('primary_failure_mode','N/A')} &nbsp;
        <span style="color:#888;font-size:12px">(confidence: {h.get('confidence','?')}%)</span></div>
      <div style="color:#aaa;font-size:12px"><b>Evidence:</b>{ev_html}</div>
    </div>""", unsafe_allow_html=True)

    ct_html = "".join(f"<div style='margin:3px 0;font-size:12px'>• {c}</div>" for c in s.get("counter_evidence",[])[:3])
    alts_html = "".join(f"<div style='margin:3px 0;font-size:12px'>• {a.get('mode','')} ({a.get('confidence','?')}%) — {a.get('rationale','')}</div>" for a in s.get("alternative_hypotheses",[])[:2])
    st.markdown(f"""<div class="agent a-s">
      <div style="font-weight:700;color:#ff6b35;margin-bottom:8px">🟠 DR. CHALLENGE — SKEPTIC</div>
      <div style="color:#aaa;font-size:12px"><b>Counter-evidence:</b>{ct_html}</div>
      <div style="color:#aaa;font-size:12px;margin-top:6px"><b>Alternatives:</b>{alts_html}</div>
    </div>""", unsafe_allow_html=True)

    probs = v.get("probability_ranking", [])
    ph = "".join(f"<div style='display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid rgba(255,255,255,.05)'><span style='font-size:12px'>{p.get('mode','')}</span><span style='color:#00c49a;font-weight:600'>{p.get('probability','?')}%</span></div>" for p in probs)
    st.markdown(f"""<div class="agent a-v">
      <div style="font-weight:700;color:#00c49a;margin-bottom:8px">🟢 DR. VERDICT — ARBITRATOR</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
        <div><b>Verdict:</b> {v.get('final_diagnosis','N/A')}<div style="margin-top:8px">{ph}</div></div>
        <div style="font-size:12px;color:#aaa"><b>Reasoning:</b><br>{v.get('arbitration_reasoning','')}</div>
      </div>
      <div style="margin-top:10px;font-size:11px;color:#555">
        📚 {' · '.join(v.get('knowledge_base_citations',['N/A'])[:3])} &nbsp;|&nbsp;
        📋 {' · '.join(v.get('sop_references',['N/A'])[:2])}
      </div>
    </div>""", unsafe_allow_html=True)


def _archaeology(arch):
    if not arch:
        st.info("Run diagnosis first.")
        return
    st.caption("How did we get here? Causal chain traced backward through sensor history.")
    chain = arch.get("causal_chain", [])
    for item in chain:
        sig = (item.get("significance","") or "").upper().split(" —")[0]
        clr = {"ROOT CAUSE":"#ff4444","EARLY INDICATOR":"#ffbb28","ESCALATION":"#ff8c00","WARNING":"#ff8c00","CURRENT":"#ff4444"}.get(sig,"#888")
        day = item.get("day", 0)
        day_str = f"T{day:+d}d" if day != 0 else "TODAY"
        st.markdown(f"""<div class="tl">
          <span style="color:#666;font-size:11px;display:inline-block;min-width:55px">{day_str}</span>
          <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:{clr};margin:0 10px 1px 0;vertical-align:middle"></span>
          <span>{item.get('event','')}</span>
          <span style="color:{clr};font-size:11px;margin-left:8px">{item.get('significance','')}</span>
        </div>""", unsafe_allow_html=True)
    if arch.get("root_cause_summary"):
        st.markdown(f"""<div class="card" style="border-left:3px solid #ff4444;margin-top:14px">
          <b>Root Cause:</b> {arch['root_cause_summary']}
        </div>""", unsafe_allow_html=True)
    if arch.get("missed_intervention_window"):
        st.markdown(f"""<div class="card" style="border-left:3px solid #00c49a">
          <b>Optimal Intervention:</b> {arch['missed_intervention_window']}
        </div>""", unsafe_allow_html=True)


def _horizon(rul, eid):
    if not rul or not rul.get("horizon_days"):
        st.info("Run diagnosis first.")
        return
    days = rul.get("horizon_days", [])
    cum  = rul.get("horizon_cumulative_prob", [])
    rul_days = rul.get("estimated_rul_days", 60)

    fig = go.Figure()
    fig.add_hrect(y0=0,  y1=30,  fillcolor="rgba(0,196,154,.05)",  line_width=0)
    fig.add_hrect(y0=30, y1=65,  fillcolor="rgba(255,187,40,.05)", line_width=0)
    fig.add_hrect(y0=65, y1=100, fillcolor="rgba(255,68,68,.05)",  line_width=0)
    fig.add_trace(go.Scatter(
        x=days, y=cum, mode="lines", fill="tozeroy",
        fillcolor="rgba(255,68,68,.10)",
        line=dict(color="#ff4444", width=2.5),
        hovertemplate="Day %{x}: %{y:.1f}% failure probability<extra></extra>",
    ))
    fig.add_vline(x=rul_days, line=dict(color="white", dash="dash", width=1.5),
                  annotation=dict(text=f"Est. RUL: {rul_days:.0f}d", font=dict(color="white", size=11)))
    fig.add_vline(x=7,  line=dict(color="rgba(255,68,68,.4)",  dash="dot", width=1))
    fig.add_vline(x=30, line=dict(color="rgba(255,187,40,.4)", dash="dot", width=1))
    fig.update_layout(
        title=dict(text=f"Failure Horizon — {eid}", font=dict(size=14)),
        xaxis_title="Days from today", yaxis_title="Failure probability (%)",
        yaxis=dict(range=[0,105]), height=340, showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(20,22,30,.8)",
        font_color="#ccc", margin=dict(l=40,r=20,t=40,b=40),
        xaxis=dict(gridcolor="rgba(255,255,255,.05)"),
        yaxis2=dict(gridcolor="rgba(255,255,255,.05)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    c1, c2, c3 = st.columns(3)
    for col, p, lbl in [
        (c1, rul.get("failure_probability_7d",0),  "Within 7 days"),
        (c2, rul.get("failure_probability_30d",0), "Within 30 days"),
        (c3, rul.get("failure_probability_90d",0), "Within 90 days"),
    ]:
        clr = "#ff4444" if p>50 else "#ffbb28" if p>25 else "#00c49a"
        with col:
            st.markdown(f"""<div class="card card-metric">
              <div class="val" style="color:{clr}">{p:.1f}%</div>
              <div class="lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)


def _actions(council, risk, spares):
    v = council.get("verdict", {})
    immediate = v.get("immediate_actions", [])
    longterm  = v.get("long_term_actions", [])
    sops      = v.get("sop_references", [])
    parts     = (spares or {}).get("spares", [])

    pri = risk.get("priority","LOW")
    urg = risk.get("urgency","")
    if urg:
        uc = {"CRITICAL":"#ff4444","HIGH":"#ff8c00","MEDIUM":"#ffbb28","LOW":"#00c49a"}.get(pri,"#888")
        st.markdown(f"""<div class="card" style="border:1px solid {uc}">
          <b style="color:{uc}">{pri}</b> — {urg}
        </div>""", unsafe_allow_html=True)

    if immediate:
        st.markdown("**Immediate Actions**")
        for i, a in enumerate(immediate, 1):
            st.markdown(f'<div class="act"><b style="color:#00c49a">{i}.</b> {a}</div>',
                        unsafe_allow_html=True)

    if longterm:
        st.markdown("**Long-Term**")
        for a in longterm:
            st.markdown(f"- {a}")

    if sops:
        st.markdown("**SOP References:** " + "  ·  ".join(f"`{s}`" for s in sops))

    if parts:
        st.markdown("**Spare Parts**")
        df = pd.DataFrame(parts)[["part_code","description","qty_stock","lead_time_days","unit_cost_inr"]]
        df.columns = ["Code","Description","In Stock","Lead Time (d)","Cost (₹)"]
        df["Status"] = df["In Stock"].apply(lambda x: "✅ Available" if x > 0 else "❌ Order needed")
        st.dataframe(df, use_container_width=True, hide_index=True)

def _pattern_matches(eid, res):
    """Show historical incidents that match the current failure pattern."""
    try:
        from agents.briefing import find_pattern_matches
        from database.db_manager import build_equipment_context
        ctx = build_equipment_context(eid)
        matches = find_pattern_matches(eid, ctx)
    except Exception as e:
        st.warning(f"Pattern matching unavailable: {e}"); return

    st.markdown("#### 🔁 We've seen this before")
    st.caption("MINERVA matches current sensor patterns against the plant's historical incident library — surfacing what worked last time.")

    if not matches:
        st.info("No strong historical matches found for this equipment's current state. The pattern is novel — log observations carefully for future reference.")
        return

    for m in matches:
        sc = m.get("match_score", 0)
        sc_c = "#ff4444" if sc >= 75 else "#ffbb28" if sc >= 50 else "#888"

        st.markdown(f"""
        <div class="card" style="border-top:3px solid {sc_c}">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px">
            <div>
              <div style="font-weight:700;font-size:15px">{m['failure_mode']}</div>
              <div style="color:#777;font-size:12px">{m['incident_id']} — {m['date']} — {m['equip_name']}</div>
            </div>
            <div style="text-align:right">
              <div style="font-size:22px;font-weight:700;color:{sc_c}">{sc}%</div>
              <div style="font-size:10px;color:#666">Pattern match</div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;font-size:13px">
            <div>
              <div style="color:#888;font-size:11px;font-weight:600;margin-bottom:4px">WHY THIS MATCHES</div>
              {"".join(f"<div>• {r}</div>" for r in m.get("match_reasons", []))}
            </div>
            <div>
              <div style="color:#888;font-size:11px;font-weight:600;margin-bottom:4px">AT THIS STAGE THEN</div>
              <div>⏱️ {m['days_to_failure_at_match']} days to failure from similar sensor state</div>
              <div>⏬ {m['total_downtime_hours']}h downtime</div>
              <div>💸 ₹{m['total_cost_inr_lakhs']}L total cost</div>
            </div>
          </div>
        </div>""", unsafe_allow_html=True)

        with st.expander(f"What happened & what worked — {m['incident_id']}"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**What happened:**")
                st.markdown(m["what_happened"])
            with col_b:
                st.markdown("**What we did:**")
                st.markdown(m["what_we_did"])
            st.markdown(f"**Lesson learned:** {m['lesson']}")
            st.markdown(f"**Outcome:** ✅ {m['outcome']}")


def _business_case(eid, res):
    """Show cost justification for doing planned maintenance now vs waiting for failure."""
    try:
        from agents.briefing import calculate_business_case
        from database.db_manager import build_equipment_context
        from ml_engine.engine import RULPredictor
        ctx = build_equipment_context(eid)
        rul = RULPredictor().estimate_rul(eid, ctx)
        bc  = calculate_business_case(eid, ctx, rul)
    except Exception as e:
        st.warning(f"Business case unavailable: {e}"); return

    st.markdown("#### 💰 Maintenance Business Case")
    st.caption("Numbers a supervisor or plant manager can sign off on — why acting now is cheaper than waiting.")

    # Urgency banner
    rul_d = bc.get("rul_days", 14)
    uc = "#ff4444" if rul_d <= 7 else "#ff8c00" if rul_d <= 21 else "#ffbb28"
    st.markdown(f"""
    <div class="card" style="border:1px solid {uc};text-align:center;padding:12px">
      <span style="font-size:16px;font-weight:700;color:{uc}">{bc['urgency_msg']}</span>
    </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # Cost comparison
    pl = bc["planned"]; fl = bc["failure"]
    col1, col_vs, col2 = st.columns([5, 1, 5])

    with col1:
        st.markdown(f"""
        <div class="card" style="border-top:3px solid #00c49a">
          <div style="font-size:11px;color:#00c49a;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">✅ Planned Maintenance Now</div>
          <div style="font-size:32px;font-weight:700;color:#00c49a">₹{pl['total_lakhs']}L</div>
          <div style="font-size:12px;color:#888;margin-top:6px">
            Parts: ₹{pl['parts_cost_lakhs']}L<br>
            Labour: ₹{pl['labor_cost_lakhs']}L<br>
            Downtime: ~{pl['downtime_hours']}h
          </div>
        </div>""", unsafe_allow_html=True)

    with col_vs:
        st.markdown("<div style='text-align:center;padding-top:50px;font-size:20px;color:#666'>vs</div>",
                    unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
        <div class="card" style="border-top:3px solid #ff4444">
          <div style="font-size:11px;color:#ff4444;font-weight:700;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px">⛔ Emergency Repair After Failure</div>
          <div style="font-size:32px;font-weight:700;color:#ff4444">₹{fl['total_lakhs']}L</div>
          <div style="font-size:12px;color:#888;margin-top:6px">
            Production loss: ₹{fl['production_loss_lakhs']}L<br>
            Emergency parts: ₹{fl['emergency_parts_lakhs']}L<br>
            Downtime: ~{fl['downtime_hours']}h
          </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    save = bc["saving_lakhs"]; roi = bc["roi_multiple"]
    save_c = "#00c49a" if save > 0 else "#888"
    s1, s2 = st.columns(2)
    with s1:
        st.markdown(f"""
        <div class="card card-metric">
          <div class="val" style="color:{save_c}">₹{save}L</div>
          <div class="lbl">Potential Saving</div>
        </div>""", unsafe_allow_html=True)
    with s2:
        st.markdown(f"""
        <div class="card card-metric">
          <div class="val" style="color:{save_c}">{roi}×</div>
          <div class="lbl">Return on Acting Now</div>
        </div>""", unsafe_allow_html=True)

    st.markdown(f"""
    <div class="card" style="border-left:3px solid #00c49a;margin-top:6px">
      <b>Recommendation:</b> {bc['recommendation']}
    </div>""", unsafe_allow_html=True)


# ── PAGE 3 — ALERTS ───────────────────────────────────────────────────────────
def page_alerts():
    st.markdown("## ⚠️ Alerts")

    try:
        from agents.alert_system import (get_alerts, acknowledge_alert,
                                          resolve_alert, scan_and_generate_alerts,
                                          get_alert_summary)
    except ImportError as e:
        st.error(f"Alert system import failed: {e}"); return

    c1, c2, c3 = st.columns([1,2,5])
    with c1:
        if st.button("🔄 Scan", use_container_width=True):
            n = scan_and_generate_alerts()
            st.toast(f"{len(n)} new alert(s)")
    with c2:
        sev_f = st.selectbox("Severity", ["All","CRITICAL","HIGH","MEDIUM"],
                              label_visibility="collapsed", key="sev_f")

    s = get_alert_summary()
    m1, m2, m3, m4 = st.columns(4)
    for col, v, lbl, clr in [
        (m1, s.get("active_critical",0), "Critical",     "#ff4444"),
        (m2, s.get("active_high",0),     "High",         "#ff8c00"),
        (m3, s.get("acknowledged",0),    "Acknowledged", "#6688cc"),
        (m4, s.get("total_active",0),    "Total Active", "#ffbb28"),
    ]:
        with col:
            st.markdown(f"""<div class="card card-metric">
              <div class="val" style="color:{clr}">{v}</div>
              <div class="lbl">{lbl}</div>
            </div>""", unsafe_allow_html=True)

    st.divider()
    alerts = get_alerts(status=None,
                        severity=None if sev_f=="All" else sev_f,
                        limit=30)
    active = [a for a in alerts if a.get("status") in ("active","acknowledged")]

    if not active:
        st.success("✅ No active alerts")
    else:
        st.markdown(f"### {len(active)} Open Alert(s)")
        for a in active:
            sev  = a.get("severity","HIGH")
            stat = a.get("status","active")
            clr  = {"CRITICAL":"#ff4444","HIGH":"#ff8c00","MEDIUM":"#ffbb28"}.get(sev,"#888")
            ico  = "🔴" if stat=="active" else "🔵"
            nm   = EQUIPMENT_REGISTRY.get(a.get("equip_id",""),{}).get("name","")

            with st.expander(f"{ico} [{sev}]  {a.get('title','')}  ·  {a.get('equip_id','')} — {nm}",
                             expanded=(sev=="CRITICAL" and stat=="active")):
                st.markdown(f"**Detail:** {a.get('body','')}")
                st.markdown(f"**Recommended action:** {a.get('action','')}")
                st.caption(f"Sensor: {a.get('sensor','')} = {a.get('sensor_value','?')}  |  Threshold: {a.get('threshold','?')}  |  {(a.get('created_at','') or '')[:16]}")
                if stat == "active":
                    ca, cb = st.columns([3,1])
                    with ca: eng = st.text_input("Your name", "Engineer", key=f"e_{a['alert_id']}")
                    with cb:
                        if st.button("✅ Acknowledge", key=f"ack_{a['alert_id']}", use_container_width=True):
                            acknowledge_alert(a["alert_id"], eng); st.rerun()
                elif stat == "acknowledged":
                    ca, cb = st.columns([3,1])
                    with ca: note = st.text_input("Action taken", key=f"n_{a['alert_id']}", placeholder="Describe what was done")
                    with cb:
                        if st.button("🔓 Resolve", key=f"r_{a['alert_id']}", use_container_width=True):
                            resolve_alert(a["alert_id"], note); st.rerun()

    st.divider()
    st.markdown("### Recently Resolved")
    resolved = get_alerts(status="resolved", limit=6)
    if not resolved:
        st.caption("No resolved alerts yet.")
    for a in resolved:
        st.markdown(f"🟢 ~~{a.get('title','')}~~ — {a.get('equip_id','')} — resolved {(a.get('resolved_at','') or '')[:10]}")

# ── PAGE 4 — LOGBOOK ──────────────────────────────────────────────────────────
def page_logbook():
    st.markdown("## 📓 Maintenance Logbook")

    try:
        from agents.alert_system import get_logbook_entries, add_logbook_entry, ENTRY_TYPES
    except ImportError as e:
        st.error(f"Logbook import failed: {e}"); return

    # ── Shift Handover ─────────────────────────────────────────────────────
    with st.expander("🔄 Generate Shift Handover Report", expanded=False):
        st.caption("Auto-generates a structured handover summary for the incoming team.")
        if st.button("📋 Generate Handover Now", type="primary"):
            try:
                from agents.briefing import generate_shift_handover
                ho = generate_shift_handover()

                st.markdown(f"""
                <div class="card" style="border-top:3px solid #1e90ff">
                  <div style="font-size:18px;font-weight:700">Shift Handover Report</div>
                  <div style="color:#777;font-size:12px">{ho['generated_at']} · {ho['shift']} → {ho['for_next_shift']}</div>
                </div>""", unsafe_allow_html=True)

                # Auto-notes
                if ho.get("handover_notes"):
                    st.markdown("**⚡ Key Messages for Incoming Shift:**")
                    for note in ho["handover_notes"]:
                        clr = "#ff4444" if "IMMEDIATE" in note else "#ffbb28" if "MONITOR" in note else "#00c49a"
                        st.markdown(f"""
                        <div class="card" style="border-left:3px solid {clr};padding:8px 14px">
                          <span style="font-size:13px">{note}</span>
                        </div>""", unsafe_allow_html=True)

                # Critical / warning equipment
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Critical Equipment:**")
                    if ho.get("critical_equipment"):
                        for e in ho["critical_equipment"]:
                            st.markdown(f"🔴 **{e['equip_id']}** — {e['name']} ({e['health']:.0f}%)")
                    else:
                        st.markdown("*None*")
                with c2:
                    st.markdown("**Warning Equipment:**")
                    if ho.get("warning_equipment"):
                        for e in ho["warning_equipment"]:
                            st.markdown(f"🟡 **{e['equip_id']}** — {e['name']} ({e['health']:.0f}%)")
                    else:
                        st.markdown("*None*")

                # Active / in-progress alerts
                if ho.get("active_alerts"):
                    st.markdown("**Open Alerts (requires attention):**")
                    for a in ho["active_alerts"][:4]:
                        st.markdown(f"⚠️ [{a.get('severity','')}] {a.get('title','')} — {a.get('equip_id','')}")

                if ho.get("in_progress"):
                    st.markdown("**In Progress (acknowledged, not resolved):**")
                    for a in ho["in_progress"]:
                        st.markdown(f"🔵 {a.get('title','')} — acknowledged by {a.get('acknowledged_by','?')}")

                # Recent maintenance done this shift
                if ho.get("maintenance_done"):
                    st.markdown("**Maintenance Completed This Shift:**")
                    for m in ho["maintenance_done"]:
                        st.markdown(f"✅ {m.get('equip_id','')} — {m.get('action','')} ({m.get('type','')})")

                # Save to logbook
                from agents.alert_system import add_logbook_entry
                summary_lines = [f"Handover: {ho['shift']} → {ho['for_next_shift']}"]
                for note in ho.get("handover_notes", []):
                    summary_lines.append(f"• {note}")
                add_logbook_entry("PLANT", "Shift_Handover",
                                  f"Shift Handover — {ho['shift']}",
                                  "\n".join(summary_lines),
                                  "MINERVA Auto", "shift_handover")
                st.success("✅ Handover saved to logbook")

            except Exception as e:
                st.error(f"Handover generation failed: {e}")

    st.divider()

    # Add entry
    with st.expander("✍️ Add Entry", expanded=False):
        c1, c2, c3 = st.columns(3)
        with c1: eq  = st.selectbox("Equipment", list(EQUIPMENT_REGISTRY.keys()), key="lb_eq_add")
        with c2: et  = st.selectbox("Type", ENTRY_TYPES, key="lb_et_add")
        with c3: aut = st.text_input("Engineer", "Engineer", key="lb_aut")
        ttl = st.text_input("Title", key="lb_ttl")
        bdy = st.text_area("Details", height=80, key="lb_bdy")
        if st.button("Add Entry", key="lb_add") and ttl:
            add_logbook_entry(eq, et, ttl, bdy, aut, "manual")
            st.success("Entry added!"); st.rerun()

    st.divider()

    # Filters
    c1, c2, c3 = st.columns(3)
    with c1: lb_eq = st.selectbox("Equipment", ["All"]+list(EQUIPMENT_REGISTRY.keys()), key="lb_eq_f")
    with c2: lb_ty = st.selectbox("Type", ["All"]+ENTRY_TYPES, key="lb_ty_f")
    with c3: lb_dy = st.slider("Days back", 1, 90, 30, key="lb_dy_f")

    entries = get_logbook_entries(
        equip_id=None if lb_eq=="All" else lb_eq,
        entry_type=None if lb_ty=="All" else lb_ty,
        days=lb_dy,
    )
    st.caption(f"{len(entries)} entries")
    st.divider()

    if not entries:
        st.info("No entries yet. Run a diagnosis or add one above.")
        return

    type_colors = {
        "AI_Diagnosis":"#3c3489","Alert":"#993c1d","Repair":"#854f0b",
        "Inspection":"#0f6e56","Observation":"#0f6e56","Measurement":"#0f6e56",
        "Parts_Used":"#854f0b","Shift_Handover":"#555","Other":"#888",
    }
    for e in entries:
        et   = e.get("entry_type","Other")
        clr  = type_colors.get(et,"#888")
        nm   = EQUIPMENT_REGISTRY.get(e.get("equip_id",""),{}).get("name","")
        body = (e.get("content","") or "")[:280]
        date = (e.get("created_at","") or "")[:10]
        st.markdown(f"""<div class="card" style="border-left:3px solid {clr}">
          <div style="display:flex;justify-content:space-between;margin-bottom:4px">
            <div>
              <span style="font-size:11px;color:{clr};font-weight:600">{et}</span>
              <span style="color:#666;font-size:11px;margin-left:6px">· {e.get('equip_id','')} {nm} · {e.get('author','')}</span>
            </div>
            <span style="color:#555;font-size:11px">{date}</span>
          </div>
          <div style="font-weight:600;font-size:13px;color:#ddd">{e.get('title','')}</div>
          <div style="color:#999;font-size:12px;margin-top:4px">{body}</div>
        </div>""", unsafe_allow_html=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    try:
        get_orch()
    except Exception as e:
        st.error(f"**MINERVA startup failed:** {e}\n\nRun: `python setup_minerva.py`")
        st.stop()

    sidebar()

    p = st.session_state.page
    if   p == "🏠 Overview": page_overview()
    elif p == "🔍 Diagnose":  page_diagnose()
    elif p == "⚠️ Alerts":    page_alerts()
    elif p == "📓 Logbook":   page_logbook()

if __name__ == "__main__":
    main()
