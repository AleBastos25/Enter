# Backend - Graph Extractor API

API FastAPI para extração de dados de PDFs usando Graph Extractor.

## Instalação

```bash
# No diretório raiz do projeto
pip install -r requirements.txt
pip install -r backend/requirements.txt
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

## Configuração

### Secrets (para LLM/OpenAI embeddings)

```bash
# Copiar template de secrets
cp configs/secrets.yaml.example configs/secrets.yaml
# Editar e adicionar sua OPENAI_API_KEY
# Windows: notepad configs/secrets.yaml
# Linux/Mac: nano configs/secrets.yaml
```

**Importante:** O arquivo `secrets.yaml` é git-ignored. Use o template `secrets.yaml.example` como base.

### Variáveis de Ambiente (Frontend)

O frontend usa a variável `NEXT_PUBLIC_API_URL` (padrão: `http://localhost:8000`). Configure em `.env.local` no diretório `frontend/` se necessário.

