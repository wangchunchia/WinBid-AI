# WinBid-AI Backend

FastAPI backend scaffold for the automated bid-writing system.

## Quick Start

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

## PostgreSQL

Default local connection in `.env.example`:

```env
WINBID_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/winbid
```

If you want a local database quickly:

```bash
docker compose up -d db
```

## LLM Draft Generation

This project can optionally use the OpenAI Responses API to rewrite rule-based chapter drafts into more formal bid text.

Enable it in `.env`:

```env
WINBID_OPENAI_ENABLE_DRAFT_GENERATION=true
WINBID_OPENAI_MODEL=gpt-5-mini
WINBID_OPENAI_API_KEY=your_api_key
```

If not enabled, the backend falls back to deterministic draft generation.

## Current Scope

1. Project and API skeleton
2. PostgreSQL-backed core persistence for projects and materials
3. Alembic migration scaffold
4. Core route definitions from the system design
5. Real document parsing, chunking, and OCR fallback pipeline

## Next Steps

1. Persist clauses, requirements, chapters, and compliance issues
2. Add object storage integration
3. Add OCR / parser / agent execution jobs
4. Replace orchestrator stub outputs with real pipeline execution
