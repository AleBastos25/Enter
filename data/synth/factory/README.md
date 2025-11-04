# Synthetic Document Factory

Gerador genérico de PDFs sintéticos com layouts variados, orientado a schemas.

## Uso

### Gerar dataset sintético

```bash
# Gera 800 documentos diversos para um schema qualquer
python -m data.synth.factory.synth \
  --schema data/samples/dataset.json \
  --label generic \
  --n 800 \
  --archetypes generic_card,generic_form,generic_screen,generic_invoice,generic_report \
  --out data/synth/generic \
  --engine weasyprint \
  --with-noise

# Gera 300 documentos estilo "telas de sistema" para stressar tabelas
python -m data.synth.factory.synth \
  --schema data/samples/dataset.json \
  --label tela_sistema \
  --n 300 \
  --archetypes generic_screen \
  --out data/synth/telas \
  --config configs/augment.yaml
```

### Arquétipos disponíveis

- `generic_card`: Cartões/IDs (compacto, título, KV, badge)
- `generic_form`: Formulários (grid, instruções, assinatura)
- `generic_screen`: Telas de sistema (tabela grande, KV laterais)
- `generic_invoice`: Faturas/recibos (cabeçalho KV, tabela, totais)
- `generic_report`: Relatórios/certificados (títulos, parágrafos, KV esparsa)

### Estrutura de saída

```
data/synth/<label>/
  pdfs/*.pdf           # PDFs gerados
  labels.jsonl         # Ground truth (compatível com dataset.json)
  html/*.html          # HTML gerado (debug)
```

### Formato de labels.jsonl

Cada linha é um JSON com:
```json
{
  "label": "generic",
  "extraction_schema": {
    "field1": "description1",
    "field2": "description2"
  },
  "pdf_path": "synth/generic/pdfs/doc_0.pdf",
  "answers": {
    "field1": "valor1",
    "field2": "valor2"
  }
}
```

## Configuração

Veja `configs/augment.yaml` para parâmetros de:
- Layout (colunas, relações KV)
- Tabelas
- Ruído/perturbações (rotação, compressão JPEG, blur)
- Tipografia

## Requisitos

- `faker`: Geração de valores sintéticos
- `weasyprint`: Conversão HTML→PDF (ou `wkhtmltopdf`)
- `Pillow`: Manipulação de imagens para ruído

