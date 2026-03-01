# Backend - Graph Extractor API

FastAPI for extracting data from PDFs using Graph Extractor.

## Installation

```bash
# In the project root directory
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

## Execution

```bash
# Development
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000

# Or using Python script directly
python -m backend.src.main
```

## Endpoints

### POST /api/graph-extract

Extracts data from multiple PDFs.

**Form Data:**
- `label` (string): Document label
- `schema` (string, optional): JSON string with schema
- `schema_file` (file, optional): JSON file with schema
- `files` (files): List of PDFs (up to 10)
- `dev_mode` (bool): If True, generates graph HTML

**Response:**
```json
{
  "runs": [
    {
      "run_id": "2025-01-15T10-12-33_doc1",
      "filename": "doc1.pdf",
      "status": "ok",
      "result": {...},
      "dev": {
        "elapsed_ms": 842,
        "rules_used": ["regex_perfect", "pattern_partial"],
        "graph_url": "/graph/2025-01-15T10-12-33_doc1.html"
      }
    }
  ]
}
```

### GET /graph/{run_id}.html

Returns graph HTML for an execution (only in dev_mode).

## Configuration

### Secrets (for LLM/OpenAI embeddings)

```bash
# Copy secrets template
cp configs/secrets.yaml.example configs/secrets.yaml
# Edit and add your OPENAI_API_KEY
# Windows: notepad configs/secrets.yaml
# Linux/Mac: nano configs/secrets.yaml
```

**Important:** The `secrets.yaml` file is git-ignored. Use the `secrets.yaml.example` template as a base.

### Environment Variables (Frontend)

The frontend uses the `NEXT_PUBLIC_API_URL` variable (default: `http://localhost:8000`). Configure in `.env.local` in the `frontend/` directory if needed.
