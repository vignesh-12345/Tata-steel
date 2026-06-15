"""
MINERVA Knowledge Base
Tries ChromaDB first; falls back to TF-IDF (sklearn) if unavailable.
This means the system works with zero extra installs.
"""
import json
import numpy as np
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Seed documents (steel-plant domain) ─────────────────────────────────────
SEED_DOCUMENTS = [
    {"id":"rm-man-001","type":"manual","equipment":"rolling_mill",
     "content":"Rolling Mill Bearing Inspection: Vibration >4.5 mm/s RMS requires investigation; >7.0 mm/s requires immediate shutdown. Bearing temperature >75°C needs lubrication check; >90°C needs immediate inspection. BPFO frequency at 3.2 kHz indicates outer race defect. Re-grease every 250 hours with Mobilux EP2."},
    {"id":"rm-man-002","type":"manual","equipment":"rolling_mill",
     "content":"Rolling Mill Lubrication: Use ISO VG 220 gear oil. Change every 3000 hours or 6 months. If oil temperature exceeds 80°C check oil cooler. Excessive grease consumption (>50% above normal) indicates bearing seal damage."},
    {"id":"rm-sop-001","type":"sop","equipment":"rolling_mill",
     "content":"SOP-RM-042 Emergency Bearing Replacement: 1) Issue work permit and LOTO. 2) Cool bearing housing below 40°C. 3) Remove coupling with hydraulic puller only. 4) Inspect housing bore. 5) Heat new bearing to 80°C max. 6) Fill grease to 1/3 housing volume. Estimated time: 6-8 hours. Minimum 3 technicians."},
    {"id":"rm-fail-001","type":"failure_report","equipment":"rolling_mill",
     "content":"FR-2024-031 Rolling Mill RM-2 Bearing Failure (March 2024): Outer race defect. Vibration rose 3.1 to 6.8 mm/s over 11 days. Temperature increased 22°C. BPFO at 3.2 kHz confirmed. Root cause: lubrication interval extended. Downtime 18 hours. Corrective action: bearing replaced, lubrication returned to 200-hour interval."},
    {"id":"bf-man-001","type":"manual","equipment":"blast_furnace",
     "content":"Blast Furnace Cooling System: Minimum flow 120 m³/h. Below 90 m³/h triggers alarm. Monthly inspection mandatory. Scale deposits cause progressive flow reduction over weeks. Annual chemical cleaning with 15% HCl recommended. Temperature rise >10°C in cooling outlet above normal differential indicates blockage."},
    {"id":"bf-sop-001","type":"sop","equipment":"blast_furnace",
     "content":"SOP-BF-015 Cooling Circuit Cleaning: 1) Identify circuit via thermal imaging. 2) Isolate with bypass valves. 3) Flush with demineralized water at 1.5x flow. 4) Inject 200L of 15% HCl at 0.5 L/min. 5) Soak 2 hours then flush until pH>6. 6) Restore flow and verify temperature differential."},
    {"id":"comp-man-001","type":"manual","equipment":"compressor",
     "content":"Compressor Maintenance: Discharge temperature normal 60-90°C; above 100°C indicates valve inefficiency or intercooler fouling. Vibration normal below 4.5 mm/s. Valve failure is most common mode (60% of compressor failures). Symptoms: increased temperature, reduced throughput, abnormal knock. MTTR 4-6 hours."},
    {"id":"gen-sop-001","type":"sop","equipment":"general",
     "content":"SOP-GEN-001 Work Order Priority: PRIORITY 1 CRITICAL - immediate shutdown risk or safety hazard, respond within 1 hour 24/7. PRIORITY 2 HIGH - significant degradation, respond within 4 hours. PRIORITY 3 MEDIUM - preventive action within 7 days. PRIORITY 4 LOW - routine maintenance within 30 days."},
    {"id":"gen-sop-002","type":"sop","equipment":"general",
     "content":"SOP-GEN-004 Vibration Analysis: ISO 10816-3 severity: Good <2.3 mm/s, Satisfactory 2.3-4.5, Unsatisfactory 4.5-7.1, Unacceptable >7.1. Frequency: 1x RPM = unbalance/misalignment; 2x RPM = angular misalignment; BPFI/BPFO = bearing inner/outer race. Vibration doubling in <7 days indicates accelerating failure."},
    {"id":"gen-fail-001","type":"failure_report","equipment":"general",
     "content":"Failure Mode Frequency 2023-2024: Bearing failure 34% most common. Seal/gasket failure 18%. Belt/coupling wear 15%. Electrical fault 13%. Corrosion/fouling 11%. Average unplanned downtime cost Rs 4.2 lakhs per hour for critical equipment. Bearing failures account for 41% of total maintenance cost."},
    {"id":"hyd-man-001","type":"manual","equipment":"hydraulic",
     "content":"Hydraulic System Maintenance: System pressure 150-220 bar. Change filter when DP>2.0 bar or every 1000 hours. Check oil viscosity, water content, particle count every 500 hours. High filter DP with good oil indicates contamination ingress. Pump efficiency below 70% requires overhaul."},
    {"id":"ct-man-001","type":"manual","equipment":"cooling_tower",
     "content":"Cooling Tower Maintenance: Target outlet 18-28°C. Flow minimum 120 m³/h. Pressure drop increase across fill pack indicates fouling. Annual fill pack inspection - replace if >40% blocked. Fan blade inspection every 3 months. Biocide dosing weekly, scale inhibitor continuous."},
    {"id":"cb-man-001","type":"manual","equipment":"conveyor",
     "content":"Conveyor Belt Maintenance: Belt tension target 2500-3500 N. Low tension causes slippage, high tension causes premature wear. Alignment deviation >25mm (3mm measurement) requires immediate correction. Motor current increase >20% above baseline indicates blockage, slip, or overload."},
    {"id":"ohc-man-001","type":"manual","equipment":"crane",
     "content":"Overhead Crane Maintenance: Brake inspection every 250 hours. Minimum brake pad thickness 5mm. Brake temperature after normal stop max 80°C; above 90°C indicates glazing. Wire rope: discard if 10% wire breaks per rope lay or >10% diameter reduction. Annual load test at 125% SWL required."},
]

# ── Backend selection ─────────────────────────────────────────────────────────
_BACKEND = None   # "chroma" | "tfidf"
_chroma_col = None
_tfidf_mat = None
_tfidf_vec = None


def _init_backend():
    global _BACKEND, _chroma_col, _tfidf_mat, _tfidf_vec
    if _BACKEND is not None:
        return

    # Try ChromaDB first
    try:
        import chromadb
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
        from config import CHROMA_PATH
        CHROMA_PATH.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_PATH))
        ef = DefaultEmbeddingFunction()
        col = client.get_or_create_collection("minerva_knowledge", embedding_function=ef)
        existing = set(col.get()["ids"])
        new_docs = [d for d in SEED_DOCUMENTS if d["id"] not in existing]
        if new_docs:
            col.add(ids=[d["id"] for d in new_docs],
                    documents=[d["content"] for d in new_docs],
                    metadatas=[{"type": d["type"], "equipment": d["equipment"]} for d in new_docs])
        _chroma_col = col
        _BACKEND = "chroma"
        return
    except Exception:
        pass

    # Fallback: TF-IDF with sklearn
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity as cs
        corpus = [d["content"] for d in SEED_DOCUMENTS]
        vec = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        mat = vec.fit_transform(corpus)
        _tfidf_vec = vec
        _tfidf_mat = mat
        _BACKEND = "tfidf"
    except Exception as e:
        print(f"Knowledge base init failed: {e}. Using empty fallback.")
        _BACKEND = "empty"


def seed_knowledge_base():
    _init_backend()
    print(f"✓ Knowledge base ready (backend: {_BACKEND}, {len(SEED_DOCUMENTS)} documents)")


def query_knowledge_base(query: str, equip_type: str = None, n_results: int = 4) -> list[dict]:
    _init_backend()

    if _BACKEND == "chroma":
        try:
            where = {"equipment": equip_type} if equip_type else None
            results = _chroma_col.query(query_texts=[query],
                                         n_results=min(n_results, len(SEED_DOCUMENTS)),
                                         where=where)
            return [{"id": results["ids"][0][i],
                     "content": results["documents"][0][i],
                     "metadata": results["metadatas"][0][i],
                     "distance": results["distances"][0][i]}
                    for i in range(len(results["ids"][0]))]
        except Exception:
            pass

    if _BACKEND == "tfidf":
        from sklearn.metrics.pairwise import cosine_similarity
        q_vec = _tfidf_vec.transform([query])
        sims = cosine_similarity(q_vec, _tfidf_mat)[0]
        # filter by equipment type if supplied
        indices = list(range(len(SEED_DOCUMENTS)))
        if equip_type:
            indices = [i for i in indices if SEED_DOCUMENTS[i]["equipment"] in (equip_type, "general")]
        indices_sorted = sorted(indices, key=lambda i: sims[i], reverse=True)[:n_results]
        return [{"id": SEED_DOCUMENTS[i]["id"],
                 "content": SEED_DOCUMENTS[i]["content"],
                 "metadata": {"type": SEED_DOCUMENTS[i]["type"], "equipment": SEED_DOCUMENTS[i]["equipment"]},
                 "distance": float(1 - sims[i])}
                for i in indices_sorted]

    # Empty fallback — return first n documents
    return [{"id": d["id"], "content": d["content"],
             "metadata": {"type": d["type"], "equipment": d["equipment"]}, "distance": 0.5}
            for d in SEED_DOCUMENTS[:n_results]]


def add_document(doc_id: str, content: str, doc_type: str, equipment: str):
    _init_backend()
    if _BACKEND == "chroma" and _chroma_col:
        _chroma_col.upsert(ids=[doc_id], documents=[content],
                           metadatas=[{"type": doc_type, "equipment": equipment}])
