# Document Extraction System

Layout-first, hybrid extraction pipeline for structured data from PDFs. Extracts structured information from arbitrary PDF documents using a combination of spatial analysis, table detection, semantic matching, and optional LLM fallback.

## Features

- **Layout-first approach**: Analyzes spatial relationships before semantic processing
- **Multi-page support**: Processes documents with multiple pages with early-stop
- **Table detection**: Extracts data from both KV-lists and grid tables
- **Semantic matching**: Uses embeddings for finding fields even when labels vary
- **LLM fallback**: Optional budgeted LLM calls for ambiguous cases
- **Pattern memory**: Incremental learning from high-confidence extractions
- **Rich validation**: 20+ validators including Brazilian-specific types (CPF, CNPJ, etc.)
- **Deterministic by default**: Heuristics and tables before any AI usage

## Quick Start

### Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Optional: for local embeddings
pip install sentence-transformers>=2.0.0

# Optional: for LLM fallback
pip install openai>=1.0.0
```

Requires Python >= 3.10.

### Basic Usage

```bash
# Run extraction on a PDF
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/oab_1.pdf
```

### Example Schema

Create a JSON file with field descriptions:

```json
{
  "inscricao": "Número de inscrição na OAB",
  "seccional": "Sigla da seccional (UF)",
  "situacao": "Situação do profissional, normalmente no canto inferior direito"
}
```

### Output Format

```json
{
  "label": "carteira_oab",
  "results": {
    "inscricao": {
      "value": "101943",
      "confidence": 0.9,
      "source": "heuristic",
      "trace": {
        "node_id": 5,
        "relation": "same_line_right_of",
        "page_index": 0,
        "notes": "Value found to the right of label on the same line"
      }
    }
  }
}
```

## CLI Usage

### Basic Commands

```bash
# Inspect extracted blocks
python -m src.app.cli --probe --pdf data/samples/oab_1.pdf --label teste

# Debug layout structure
python -m src.app.cli --layout-debug --pdf data/samples/oab_1.pdf

# Dump detected tables
python -m src.app.cli --dump-tables --pdf data/samples/oab_1.pdf

# Run extraction
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/oab_1.pdf

# Save output to file
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/oab_1.pdf \
  --out results.json

# Enable debug diagnostics
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/oab_1.pdf \
  --debug

# Enable multi-page processing
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/document.pdf \
  --multi-page

# Control LLM/embedding usage
python -m src.app.cli --run \
  --label carteira_oab \
  --schema data/samples/schema.json \
  --pdf data/samples/oab_1.pdf \
  --no-llm \
  --no-embedding
```

### Flags

- `--run`: Execute full extraction pipeline
- `--probe`: Inspect first blocks extracted from PDF
- `--layout-debug`: Print layout structure (columns, sections, paragraphs)
- `--dump-tables`: Show detected tables
- `--pdf PATH`: Path to PDF file
- `--label LABEL`: Document type/label
- `--schema PATH`: Path to schema JSON file
- `--out PATH`: Save output JSON to file
- `--debug`: Include diagnostic information in output
- `--multi-page`: Enable multi-page processing
- `--llm`: Enable LLM fallback (default: from config)
- `--no-llm`: Disable LLM fallback
- `--no-embedding`: Disable embedding-based semantic matching

## Python API

```python
from src.core.pipeline import Pipeline

# Define schema
schema = {
    "inscricao": "Número de inscrição na OAB",
    "seccional": "Sigla da seccional (UF)",
    "situacao": "Situação do profissional"
}

# Run pipeline
pipe = Pipeline()
result = pipe.run("carteira_oab", schema, "data/samples/oab_1.pdf", debug=False)

# Access results
for field_name, field_result in result["results"].items():
    value = field_result.get("value")
    confidence = field_result.get("confidence", 0.0)
    source = field_result.get("source", "none")
    trace = field_result.get("trace", {})
    
    print(f"{field_name}: {value} (confidence: {confidence:.2f}, source: {source})")
```

## Configuration

### Secrets (for LLM/OpenAI embeddings)

```bash
cp configs/secrets.yaml.example configs/secrets.yaml
# Edit and add your OPENAI_API_KEY
```

### Configuration Files

- `configs/runtime.yaml`: Timeouts, limits, early-stop behavior
- `configs/embedding.yaml`: Embedding provider, model, thresholds
- `configs/llm.yaml`: LLM budget, triggering conditions
- `configs/tables.yaml`: Table detection thresholds
- `configs/layout.yaml`: Layout analysis thresholds
- `configs/memory.yaml`: Pattern memory settings

See `STATUS.md` for detailed configuration examples.

## Generating Synthetic Test PDFs

The system includes a synthetic PDF generator for testing and validation:

```bash
# Generate test dataset (10 PDFs)
python -m data.synth.factory.synth \
  --schema data/samples/dataset.json \
  --label test \
  --n 10 \
  --out data/synth/test \
  --engine weasyprint

# Generate larger dataset with noise
python -m data.synth.factory.synth \
  --schema data/samples/dataset.json \
  --label test \
  --n 100 \
  --out data/synth/test \
  --archetypes generic_card,generic_form,generic_screen \
  --with-noise \
  --config configs/augment.yaml
```

The generator creates:
- `pdfs/*.pdf`: Generated PDF files
- `labels.jsonl`: Ground truth (compatible with `dataset.json` format)
- `html/*.html`: HTML source (for debugging)

See `data/synth/factory/README.md` for more details.

## Field Types and Validators

The system supports 20+ field types with automatic validation and normalization:

### Basic Types
- `text`: Single or multi-line text
- `text_multiline`: Multi-line text (addresses, descriptions)
- `id_simple`: Alphanumeric ID (≥3 chars, requires ≥1 digit)
- `date`: Normalized to `YYYY-MM-DD`
- `money`: Brazilian format normalized to decimal (e.g., `76871.20`)
- `percent`: Normalized to decimal (e.g., `12.5`)
- `int`: Integer number
- `float`: Decimal number
- `enum`: Enumeration with options validation

### Brazilian Types
- `uf`: State code (2 uppercase letters: PR, SP, etc.)
- `cep`: Brazilian ZIP code (8 digits)
- `cpf`: Brazilian CPF with validation
- `cnpj`: Brazilian CNPJ with validation
- `phone_br`: Phone number normalized to E.164
- `placa_mercosul`: Vehicle plate (Mercosul or old format)
- `cnh`: Driver's license number
- `pis_pasep`: PIS/PASEP number
- `chave_nf`: Invoice key (44 digits)
- `rg`: ID number
- `email`: Email address
- `alphanum_code`: Generic alphanumeric code

## Testing

Run smoke tests to verify functionality:

```bash
# Test schema enrichment and validators
python scripts/test_schema_enrichment.py

# Test full pipeline
python scripts/smoke_pipeline.py

# Test on multiple PDFs
python scripts/smoke_oab.py

# Test table detection
python scripts/smoke_tables.py

# Test LLM fallback
python scripts/smoke_llm.py

# Test embeddings
python scripts/smoke_embedding.py

# Test pattern memory
python scripts/smoke_memory.py

# Test on dataset
python scripts/test_dataset.py
```

## Limitations and Trade-offs

### What Works Well

- **Structured layouts**: Documents with clear labels and values (IDs, certificates, forms)
- **Tables**: Both KV-lists and grid tables with visible structure
- **Consistent positioning**: Fields that appear in predictable locations
- **Clear labels**: Labels that match or are semantically similar to schema descriptions
- **Text-based PDFs**: PDFs with extractable text (not pure image scans)

### Edge Cases That Are Difficult

- **Highly complex layouts**: Documents with overlapping elements, unusual column structures
- **Poor OCR quality**: PDFs with low-quality text extraction or OCR errors
- **Handwritten text**: Not supported (requires OCR with handwriting recognition)
- **Ambiguous labels**: When multiple fields could match the same label
- **Very large documents**: Processing time increases linearly with page count

### Trade-offs

- **Performance vs. Precision**: More thorough analysis (embeddings, LLM) increases accuracy but costs time/money
- **Determinism vs. AI**: Deterministic heuristics are fast and free, but LLM can handle edge cases
- **Memory vs. Speed**: Pattern memory improves accuracy over time but requires storage
- **Multi-page vs. Single-page**: Multi-page processing is more robust but slower

### Recommendations

1. **Start simple**: Use single-page mode and disable LLM/embeddings for fast iteration
2. **Enable embeddings**: If labels vary in wording, embeddings improve recall
3. **Use LLM sparingly**: Enable only for difficult cases or when budget allows
4. **Multi-page when needed**: Enable for documents where information may span pages
5. **Pattern memory for production**: Enable when processing many similar documents

## Architecture

The pipeline follows a layout-first approach:

1. **PDF Loading**: Extract blocks with coordinates and styling
2. **Layout Analysis**: Build spatial graph (page → column → section → paragraph → line)
3. **Table Detection**: Detect KV-lists and grid tables
4. **Schema Enrichment**: Infer types, generate synonyms, extract hints
5. **Matching**: Find candidates using:
   - Spatial relationships (same line, below, same column)
   - Table lookups
   - Semantic similarity (embeddings)
   - Pattern memory (learned patterns)
6. **Extraction**: Extract and validate values from candidates
7. **LLM Fallback**: Optional AI-powered extraction for ambiguous cases
8. **Result Fusion**: Combine results across pages (multi-page mode)

See `STATUS.md` and `context.md` for detailed architecture documentation.

## Project Structure

```
.
├── src/
│   ├── app/cli.py              # CLI interface
│   ├── core/                   # Pipeline, models, schema
│   ├── io/                     # PDF loading, cache
│   ├── layout/                 # Layout analysis
│   ├── matching/               # Field matching
│   ├── extraction/             # Value extraction
│   ├── validation/             # Validators
│   ├── tables/                 # Table detection
│   ├── embedding/              # Semantic matching
│   ├── llm/                    # LLM fallback
│   └── memory/                 # Pattern memory
├── configs/                    # Configuration files
├── data/
│   ├── samples/                # Sample PDFs and schemas
│   └── synth/                  # Synthetic PDF generator
├── scripts/                    # Test and utility scripts
└── tests/                      # Unit tests (to be added)
```

## License

This project is part of the Enter AI Fellowship take-home challenge.

## Contributing

This is a take-home project. The codebase follows:
- **Conventional Commits**
- **Python 3.10+** with type hints
- **Docstrings** in main modules
