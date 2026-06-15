"""
MINERVA Setup Script
Run this once before launching the application.
Usage: python setup_minerva.py
"""
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))


def print_banner():
    print("""
╔══════════════════════════════════════════════════════════════╗
║   MINERVA — Maintenance Intelligence System                  ║
║   Tata Steel AI Hackathon 2026 — Round 2                     ║
╚══════════════════════════════════════════════════════════════╝
    """)


def check_env():
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("⚠️  ANTHROPIC_API_KEY not set — running in DEMO MODE (pre-computed responses)")
        print("   To enable live AI: set ANTHROPIC_API_KEY in .env file\n")
    else:
        print(f"✓ Anthropic API key detected ({api_key[:8]}…)")


def setup_database():
    print("📊 Generating synthetic steel plant data…")
    from data.synthetic_data import seed_database
    seed_database()


def setup_knowledge_base():
    print("📚 Seeding knowledge base (manuals, SOPs, failure reports)…")
    try:
        from knowledge_base.vector_store import seed_knowledge_base
        seed_knowledge_base()
    except Exception as e:
        print(f"⚠️  Knowledge base seeding failed: {e}")
        print("   Install sentence-transformers: pip install sentence-transformers")


def fit_ml_models():
    print("🤖 Fitting ML models (Anomaly Detector, Equipment Genome)…")
    try:
        import sqlite3, pandas as pd
        from config import DB_PATH
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query("SELECT * FROM sensor_readings", conn)
        conn.close()

        from ml_engine.engine import AnomalyDetector, EquipmentGenome
        ad = AnomalyDetector()
        ad.train(df)
        print(f"  ✓ Anomaly Detector trained on {len(df)} sensor readings")

        eg = EquipmentGenome()
        eg.fit(df)
        print(f"  ✓ Equipment Genome fitted for {len(eg.genomes)} equipment")
    except Exception as e:
        print(f"  ⚠️  ML model fitting error: {e} (will use fallback methods)")


def create_init_files():
    """Create __init__.py files for all packages."""
    packages = ["database", "data", "knowledge_base", "ml_engine", "agents", "api", "frontend"]
    for pkg in packages:
        init_path = BASE_DIR / pkg / "__init__.py"
        init_path.parent.mkdir(parents=True, exist_ok=True)
        if not init_path.exists():
            init_path.write_text("# MINERVA package\n")


def create_env_example():
    env_path = BASE_DIR / ".env.example"
    env_path.write_text("ANTHROPIC_API_KEY=your_api_key_here\n")
    # Also create .env if it doesn't exist (empty, so demo mode works)
    env_real = BASE_DIR / ".env"
    if not env_real.exists():
        env_real.write_text("# Add your Anthropic API key here:\n# ANTHROPIC_API_KEY=sk-ant-...\n")


def main():
    print_banner()
    check_env()
    create_init_files()
    create_env_example()
    setup_database()
    setup_knowledge_base()
    fit_ml_models()

    print("""
╔══════════════════════════════════════════════════════════════╗
║   ✅ MINERVA setup complete!                                 ║
║                                                              ║
║   To launch:                                                 ║
║     Frontend:  streamlit run frontend/app.py                 ║
║     API:       uvicorn api.main:app --reload                 ║
╚══════════════════════════════════════════════════════════════╝
    """)


if __name__ == "__main__":
    main()
