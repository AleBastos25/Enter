# API de Processamento em Lote

Este projeto oferece duas formas de processar uma pasta com PDFs e obter um JSON consolidado:

## 1. Script de Linha de Comando (Batch Processing)

Processa todos os PDFs de uma pasta e retorna um JSON consolidado.

### Uso

```bash
python scripts/batch_process.py \
  --folder data/samples \
  --label carteira_oab \
  --schema data/samples/dataset.json \
  --out output.json
```

### Parâmetros

- `--folder`: Caminho para a pasta contendo os PDFs
- `--label`: Tipo/label do documento (ex: `carteira_oab`, `tela_sistema`)
- `--schema`: Caminho para o arquivo JSON do schema
- `--out`: (Opcional) Caminho para salvar o JSON de saída
- `--debug`: (Opcional) Ativa diagnósticos de debug

### Exemplo de Output

```json
{
  "label": "carteira_oab",
  "schema_path": "data/samples/dataset.json",
  "folder_path": "data/samples",
  "total_pdfs": 6,
  "successful": 6,
  "errors": 0,
  "results": [
    {
      "label": "carteira_oab",
      "pdf_name": "oab_1.pdf",
      "pdf_path": "data/samples/oab_1.pdf",
      "results": {
        "inscricao": {
          "value": "101943",
          "confidence": 0.9,
          "source": "heuristic",
          "trace": {...}
        },
        ...
      }
    },
    ...
  ]
}
```

## 2. API HTTP (FastAPI)

Servidor HTTP REST para processar pastas via requisições HTTP.

### Instalação

```bash
pip install fastapi uvicorn
```

### Iniciar o Servidor

```bash
python scripts/api_server.py
```

O servidor estará disponível em:
- **API**: http://localhost:8000
- **Documentação**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

### Uso via cURL

```bash
curl -X POST "http://localhost:8000/process-folder" \
  -H "Content-Type: application/json" \
  -d '{
    "folder_path": "data/samples",
    "label": "carteira_oab",
    "schema_path": "data/samples/dataset.json",
    "debug": false
  }'
```

### Uso via Python

```python
import requests

response = requests.post(
    "http://localhost:8000/process-folder",
    json={
        "folder_path": "data/samples",
        "label": "carteira_oab",
        "schema_path": "data/samples/dataset.json",
        "debug": False
    }
)

result = response.json()
print(f"Processados: {result['successful']}/{result['total_pdfs']} PDFs")
```

### Endpoints

#### `POST /process-folder`

Processa todos os PDFs de uma pasta e retorna JSON consolidado.

**Request Body:**
```json
{
  "folder_path": "data/samples",
  "label": "carteira_oab",
  "schema_path": "data/samples/dataset.json",
  "debug": false
}
```

**Response:**
```json
{
  "label": "carteira_oab",
  "schema_path": "data/samples/dataset.json",
  "folder_path": "data/samples",
  "total_pdfs": 6,
  "successful": 6,
  "errors": 0,
  "results": [...],
  "error_details": null
}
```

#### `GET /health`

Verifica se o servidor está funcionando.

**Response:**
```json
{
  "status": "healthy"
}
```

#### `GET /`

Informações sobre a API.

## Exemplos Práticos

### Processar pasta de amostras

```bash
# Via CLI
python scripts/batch_process.py \
  --folder data/samples \
  --label carteira_oab \
  --schema data/samples/dataset.json \
  --out results.json

# Via API (com servidor rodando)
curl -X POST "http://localhost:8000/process-folder" \
  -H "Content-Type: application/json" \
  -d @request.json
```

### Verificar status do servidor

```bash
curl http://localhost:8000/health
```

## Notas

- O script de batch processa todos os `.pdf` encontrados na pasta
- Os resultados são consolidados em um único JSON
- Erros são capturados e incluídos no output (não interrompem o processamento)
- Ambos os métodos retornam o mesmo formato de output

