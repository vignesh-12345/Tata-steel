# ⚙️ MINERVA
## Maintenance Intelligence with Neural Engines for Reasoning, Vigilance, and Action
### Tata Steel AI Hackathon 2026 — Round 2: Agentic AI Challenge

---

## What is MINERVA?

MINERVA is an intelligent maintenance decision-support system for steel plant operations. It goes beyond traditional monitoring by deploying **five genuinely novel AI components** that make maintenance decisions transparent, trustworthy, and continuously improving.

---

## 🧠 Five Novel Innovations

### 1. Adversarial Diagnosis Council
Instead of a single LLM answer (which engineers distrust), **three specialist agents debate every diagnosis**:
- **Dr. Forward** (Hypothesis Agent) — proposes most likely failure mode with evidence
- **Dr. Challenge** (Skeptic Agent) — finds counter-evidence and alternative hypotheses  
- **Dr. Verdict** (Arbitrator) — weighs the debate and renders a confidence-ranked verdict

The debate transcript IS the explainability layer. Engineers see *why* the system chose one diagnosis over another.

### 2. Temporal Archaeology Engine
Instead of asking "what will fail?", MINERVA asks **"how did we get here?"**  
It traces backward through sensor history to reconstruct the causal chain:
> *"42 days ago: lubrication interval extended → 28 days ago: vibration baseline shifted → 19 days ago: BPFO signature appeared → 7 days ago: warning threshold crossed → TODAY: critical state"*

### 3. Equipment Genome (Behavioral Fingerprinting)
Each equipment gets a **behavioral DNA signature** — a compressed vector of how it operates across all sensors. When a failure occurs, MINERVA finds equipment with similar genomes across the **entire fleet** (even different equipment types) and surfaces their maintenance histories. Cross-fleet knowledge transfer.

### 4. Failure Horizon (Probabilistic Failure Cloud)
Instead of binary "will fail / won't fail", MINERVA generates a **Beta-distribution probability curve** over 90 days:
> *"35% chance of failure in 7 days, 68% in 30 days, 89% in 90 days"*  
The curve reshapes dynamically as sensor conditions evolve.

### 5. Counterfactual Learning Loop
After every failure event, MINERVA automatically generates:
> *"If we had intervened 6 days earlier when vibration crossed X, failure probability reduction: 78%. Estimated savings: ₹6.8 lakhs + 4.8 hours production. Revised threshold for next time: Y."*
This feeds back into future prediction thresholds.

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MINERVA ARCHITECTURE                          │
│                                                                      │
│  INTERFACE LAYER                                                     │
│  ┌─────────────────────┐  ┌─────────────────────┐                   │
│  │  Streamlit Frontend  │  │  FastAPI REST API    │                   │
│  │  (7 interactive tabs)│  │  (12 endpoints)     │                   │
│  └──────────┬──────────┘  └──────────┬──────────┘                   │
│             └─────────────┬──────────┘                               │
│                           ↓                                          │
│  ORCHESTRATION LAYER                                                 │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │              MINERVA Orchestrator (Intent → Route → Assemble)│   │
│  └──────┬──────────┬──────────┬──────────┬──────────┬──────────┘   │
│         ↓          ↓          ↓          ↓          ↓               │
│  AGENT LAYER                                                         │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
│  │Adversarial│ │Temporal  │ │Failure   │ │Prioritizer│ │Reporter  │  │
│  │Council   │ │Archaeo-  │ │Horizon   │ │(Risk+    │ │(Structured│  │
│  │(3 agents)│ │logist    │ │Predictor │ │Scheduling)│ │Reports)  │  │
│  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │
│                           ↓                                          │
│  ML ENGINE LAYER                                                     │
│  ┌─────────────┐ ┌───────────────┐ ┌──────────────────────────┐    │
│  │Anomaly      │ │RUL Predictor  │ │Equipment Genome          │    │
│  │Detector     │ │(Beta Horizon) │ │(PCA Fingerprinting)      │    │
│  │(IsoForest+  │ │               │ │                          │    │
│  │Z-score)     │ │               │ │                          │    │
│  └─────────────┘ └───────────────┘ └──────────────────────────┘    │
│                           ↓                                          │
│  DATA LAYER                                                          │
│  ┌─────────────────────────┐  ┌────────────────────────────────┐   │
│  │ SQLite (sensor readings,│  │ ChromaDB (manuals, SOPs,       │   │
│  │ maintenance history,    │  │ failure reports, procedures)   │   │
│  │ spares, feedback)       │  │ — RAG with vector search       │   │
│  └─────────────────────────┘  └────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Technology Stack

| Layer | Technology | Why |
|---|---|---|
| Orchestration | Custom Python (stateful, inspectable) | Full transparency over agent routing |
| LLM | Anthropic Claude claude-sonnet-4-20250514 | Best reasoning + tool use |
| Vector DB | ChromaDB | Local, no infra needed |
| Anomaly Detection | Isolation Forest (scikit-learn) | Unsupervised, works without labeled anomaly data |
| Failure Prediction | Beta Distribution + domain heuristics | Probabilistic, interpretable |
| Behavioral Genome | PCA + cosine similarity | Compact, cross-fleet comparable |
| Backend | FastAPI | Fast, typed, auto-documented |
| Frontend | Streamlit + Plotly | Rapid development, rich visuals |
| Storage | SQLite | Embedded, zero infrastructure |

---

## 🚀 Quick Start

### Prerequisites
```bash
pip install -r requirements.txt
```

### 1. Add your API key (optional — works in demo mode without it)
```bash
cp .env.example .env
# Edit .env and add: ANTHROPIC_API_KEY=sk-ant-...
```

### 2. Initialize the system
```bash
python setup_minerva.py
```

### 3. Launch the frontend
```bash
streamlit run frontend/app.py
```

### 4. (Optional) Launch the API
```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
# API docs: http://localhost:8000/docs
```

---

## 📁 Project Structure

```
minerva/
├── config.py                   Central configuration + equipment registry
├── requirements.txt            All dependencies
├── setup_minerva.py            One-command initialization
│
├── data/
│   └── synthetic_data.py       Steel plant data generator (8 equipment, 90 days)
│
├── database/
│   └── db_manager.py           SQLite queries + context builder
│
├── knowledge_base/
│   └── vector_store.py         ChromaDB RAG (manuals, SOPs, failure reports)
│
├── ml_engine/
│   └── engine.py               AnomalyDetector + RULPredictor + EquipmentGenome + RiskScorer
│
├── agents/
│   ├── orchestrator.py         Main routing + assembly
│   ├── adversarial_council.py  3-agent debate system (NOVEL)
│   └── archaeologist.py        Temporal backward reasoning (NOVEL)
│
├── api/
│   └── main.py                 FastAPI REST API (12 endpoints)
│
└── frontend/
    └── app.py                  Streamlit dashboard (7 tabs)
```

---

## 🎯 Inputs Handled

| Input Type | Source | How Used |
|---|---|---|
| Sensor readings | SQLite (synthetic/real-time) | Anomaly detection, trend analysis, genome |
| Equipment manuals | ChromaDB (embedded) | RAG for SOP references |
| Maintenance SOPs | ChromaDB (embedded) | Step-by-step repair instructions |
| Historical failure reports | ChromaDB + SQLite | Pattern matching in archaeology |
| Natural language queries | Streamlit / API | Intent classification → agent routing |
| Multi-turn conversations | Session state | Context-aware follow-up answers |
| Engineer feedback | SQLite feedback_log | Counterfactual learning |

---

## 📊 Expected Business Impact

| Metric | Baseline | With MINERVA | Improvement |
|---|---|---|---|
| Mean Time to Diagnose | 4-6 hours | 15 minutes | **~95% reduction** |
| Unplanned downtime | 18h/event | 4h/event | **~78% reduction** |
| Maintenance cost per event | ₹22L avg | ₹8L avg | **~64% reduction** |
| False positive alerts | 35% | <10% | **72% reduction** (via adversarial council) |
| Knowledge retention | Expert-dependent | Institutional | **Cross-fleet transfer** |

---

## 🔮 Future Enhancements

- **Real SCADA/IoT integration** via OPC-UA or MQTT connectors
- **Fine-tuned domain SLM** on Tata Steel maintenance corpus
- **Multi-plant deployment** with federated genome learning
- **Voice interface** for hands-free shop floor use
- **AR overlay** for field technicians

---

*Built for Tata Steel AI Hackathon 2026 — Round 2: Agentic AI Challenge*
