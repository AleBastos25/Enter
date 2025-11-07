# Backend - Graph Extractor API

API FastAPI para extração de dados de PDFs usando Graph Extractor.

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
# Desenvolvimento
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000

# Ou usando o script Python diretamente
python -m backend.src.main
```

## Endpoints

### POST /api/graph-extract

Extrai dados de múltiplos PDFs.

**Form Data:**
- `label` (string): Label do documento
- `schema` (string, opcional): JSON string com schema
- `schema_file` (file, opcional): Arquivo JSON com schema
- `files` (files): Lista de PDFs (até 10)
- `dev_mode` (bool): Se True, gera HTML do grafo

**Resposta:**
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

Retorna HTML do grafo para uma execução (apenas em dev_mode).

## Variáveis de Ambiente

Crie um arquivo `.env` na raiz do projeto:

```env
# Opcional: configurações de CORS
CORS_ORIGINS=http://localhost:3000
```

