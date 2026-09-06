# Land Record AI — SIH 26018

AI-powered land record digitisation, validation, and tamper-evident storage system.

## Team Branches
| Member | Role | Branch |
|--------|------|--------|
| 1 | OCR / Document Processing | `feature/ocr` |
| 2 | Validation / Anomaly Detection | `feature/validation` |
| 3 | Land-Use Rules Engine | `feature/land-use` |
| 4 | Backend + Database | `feature/backend` |
| 5 | Frontend / UI | `feature/frontend` |
| 6 | Testing / Dataset / Docs | `feature/testing` |

## Quick Start
```bash
git clone https://github.com/AdmirableAmbiguity/land-record-ai
cd land-record-ai
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Folder Structure
```
land-record-ai/
├── backend/
│   ├── api/          # FastAPI routes (Member 4)
│   ├── processing/   # OCR pipeline (Member 1)
│   ├── validation/   # Validation engine (Member 2) ✅
│   ├── land_use/     # Rules engine (Member 3)
│   ├── database/     # DB models (Member 4)
│   └── blockchain/   # Integrity (Member 4)
├── frontend/         # React/Next.js (Member 5)
├── tests/            # Test suite (Member 6)
├── data/             # Sample records
├── docs/             # Architecture & API contracts
└── models/prompts/   # VLM prompts
```

> **Disclaimer:** This system provides a *preliminary* warning based on available rules and extracted data.  
> It does **not** constitute final legal approval or a government-verified record.
