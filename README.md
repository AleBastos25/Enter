# Document Extraction System

Hybrid layout-first pipeline for extracting structured data from PDFs. Extracts structured information from arbitrary PDF documents using a combination of spatial analysis, table detection, semantic matching and optional LLM fallback.

## Mapped Challenges and Proposed Solutions

### Identified Challenges

1. **Extracting structured data from PDFs with varied layouts**
   - **Problem**: PDFs can have very different layouts (forms, cards, system screens, etc.)
   - **Solution**: Construction of a hierarchical graph that represents the document's spatial structure, assuming conventional reading direction from left to right and top to bottom. The graph uses orthogonal edges (horizontal and vertical) to capture spatial relationships between elements, allowing adaptation to different structures without reconfiguration

2. **Field matching when labels vary**
   - **Problem**: Labels can be written in different ways ("Nome", "Nome do profissional", "Nome completo")
   - **Solution**: Use of semantic embeddings (BAAI/bge-small-en-v1.5) to find fields even when wording varies

3. **Extracting data from tables**
   - **Problem**: Data can be in KV (key-value) or grid tables
   - **Solution**: Automatic table detection with support for both formats

4. **Ambiguous cases and edge cases**
   - **Problem**: Some fields may be difficult to extract with heuristics
   - **Solution**: Optional LLM fallback (GPT-4o-mini) for ambiguous cases, with budget control

5. **Validation of specific types (CPF, CNPJ, dates, etc.)**
   - **Problem**: Extracted data needs to be validated and normalized
   - **Solution**: Validator system with 20+ types, including specific Brazilian types

6. **Performance and cost**
   - **Problem**: LLM and embeddings can be expensive and slow
   - **Solution**: Deterministic approach by default (heuristics and tables first), using AI only when necessary

7. **Architectural complexity and multiple levels of abstraction**
   - **Problem**: The problem requires dealing with multiple levels of abstraction (tokens, blocks, tables, schemas, hints, validators) and input generality
   - **Solution**: Use of object-oriented programming with well-defined class hierarchy (BaseHint, BaseRule, BaseMatcher, etc.), allowing code extensibility and maintainability through clear abstractions

### Solution Architecture

The solution implements a hybrid pipeline in multiple layers:

1. **Layout Analysis**: Builds a hierarchical graph with orthogonal edges that represents the document's spatial structure. The graph is built assuming conventional reading direction (left to right, top to bottom), creating horizontal relationships (east/west) between tokens on the same line and vertical relationships (north/south) between elements on different lines. Typographic hierarchy is analyzed to identify formatting patterns (font size, bold, color) that indicate semantic structure

2. **Table Detection**: Automatically identifies KV (key-value) and grid tables

3. **Schema Enrichment**: Infers types, generates synonyms, extracts hints (typographic and semantic patterns)

4. **Multi-strategy Matching**: 
   - Spatial relationships through the graph (same line, below, same column)
   - Table lookups
   - Semantic similarity (embeddings)
   - Pattern memory (incremental learning)

5. **Extraction and Validation**: Extracts values and validates types using hints and validators

6. **LLM Fallback**: Optional for ambiguous cases

7. **Result Fusion**: Combines results between pages (multi-page mode)

### Solution Differentiators

- **Deterministic by default**: Heuristics and tables before any use of AI
- **Cost-effective**: LLM used only when necessary, with budget control
- **Adaptable**: Works with different document types without reconfiguration
- **Extensible**: Easily extensible validator and hints system
- **Performant**: Fast processing for simple documents, with option for deeper analysis when necessary


## Quick Start

### Installation

## Warning

**Installation Validation:**
- ✅ **Windows**: Instructions validated and tested on the developer's machine
- ⚠️ **Linux and macOS**: Instructions based on documentation and AI assistance (GPT-5). **Not tested in a real environment**. If you encounter issues, please report or adjust according to your distribution/operating system version.

For detailed installation instructions on **Windows, Linux or macOS**, see [INSTALLATION.md](INSTALLATION.md).

**Quick installation:**

```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

# Install Python dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Install Node.js dependencies (for web interface)
cd frontend
npm install
cd ..
```

**Requirements:**
- Python >= 3.10 (recommended: 3.11+)
- Node.js >= 18 (only for web interface)
- pip and npm

### Basic Usage

```bash
# Process PDFs from a folder
python scripts/batch_extract.py --input data/samples --output results.json
```


## How to Use the Solution

The solution offers two ways to use: **terminal version** (CLI) and **web version** (API + Interface).

### Terminal Version (CLI)

The terminal version allows processing multiple PDFs from a folder and generating an official response JSON.

#### Prerequisites

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### Basic Usage

```bash
# Process all PDFs from the samples folder
python scripts/batch_extract.py --input data/samples --output results.json
```

#### Advanced Options

```bash
# Process only PDFs with specific label
python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab

# Silent mode (no progress prints)
python scripts/batch_extract.py --input data/samples --output results.json --quiet

# Process custom folder
python scripts/batch_extract.py --input /path/to/pdfs --output /path/to/output.json
```



### Web Version (API + Interface)

The web version offers a graphical interface and a REST API for data extraction.

#### Start Backend (API)

```bash
# In the project root directory
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# or
python -m backend.src.main
```

The API will be available at `http://localhost:8000`

**Note for Windows:** You can use the `start-ui.bat` script (double-click) or `.\start-ui.ps1` in PowerShell to automatically start the backend and frontend. See [START_UI.md](START_UI.md) for more details.


#### Start Frontend (Web Interface)

```bash
# In the frontend directory
cd frontend
npm install
npm run dev
```

The interface will be available at `http://localhost:3000`

#### Web Interface Usage

1. Access `http://localhost:3000` in your browser
2. Fill in the document **Label** (e.g., `carteira_oab`)
3. Define the extraction **Schema** (JSON with field descriptions)
4. Select one or more PDF files
5. Click **Extract** to process
6. View results in the interface

#### Schema Example for Interface

```json
{
  "nome": "Nome do profissional, normalmente no canto superior esquerdo",
  "inscricao": "Número de inscrição do profissional",
  "seccional": "Seccional do profissional (sigla UF)",
  "situacao": "Situação do profissional, normalmente no canto inferior direito"
}
```

## CLI Script Usage

The `batch_extract.py` script allows processing multiple PDFs from a folder:

```bash
# Process all PDFs from the samples folder
python scripts/batch_extract.py --input data/samples --output results.json

# Process only PDFs with specific label
python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab

# Silent mode
python scripts/batch_extract.py --input data/samples --output results.json --quiet
```

### Script Options

- `--input, -i`: Path to folder containing PDFs (and optionally dataset.json)
- `--output, -o`: Path to output JSON file
- `--label, -l`: Filter only PDFs with this label (optional)
- `--quiet, -q`: Silent mode (does not print progress)

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


## Field Types and Validators

The system supports 20+ field types with automatic validation and normalization:

### Basic Types
- `text`: Simple or multi-line text
- `text_multiline`: Multi-line text (addresses, descriptions)
- `id_simple`: Alphanumeric ID (≥3 characters, requires ≥1 digit)
- `date`: Normalized to `YYYY-MM-DD`
- `money`: Brazilian format normalized to decimal (e.g., `76871.20`)
- `percent`: Normalized to decimal (e.g., `12.5`)
- `int`: Integer number
- `float`: Decimal number
- `enum`: Enumeration with option validation

### Brazilian Types
- `uf`: State code (2 uppercase letters: PR, SP, etc.)
- `cep`: Brazilian CEP (8 digits)
- `cpf`: Brazilian CPF with validation
- `cnpj`: Brazilian CNPJ with validation
- `phone_br`: Phone normalized to E.164
- `placa_mercosul`: Vehicle plate (Mercosul or old format)
- `cnh`: CNH number
- `pis_pasep`: PIS/PASEP number
- `chave_nf`: Invoice key (44 digits)
- `rg`: RG number
- `email`: Email address
- `alphanum_code`: Generic alphanumeric code

## Hints (Typographic Patterns)

The system uses hints to extract typographic and semantic patterns from fields. Hints identify characteristics such as:
- Font size
- Style (bold, italic)
- Text color
- Formatting patterns (dates, monetary values, phones, etc.)

Hints are implemented through specialized classes (DateHint, MoneyHint, PhoneHint, etc.) that detect specific patterns in extracted data.

## Incremental Learning

The system implements an incremental learning mechanism that improves extraction accuracy over time, learning from previously processed documents.

### How It Works

The learning system collects information from each extraction performed and stores learned patterns for each document type (`label`) and field:

1. **Data Collection**: For each extracted field, the system records:
   - **Spatial position** (X, Y coordinates) where the field was found
   - **Token role** (LABEL, VALUE, HEADER, etc.)
   - **Inferred data type** (date, money, text, etc.)
   - **Matching strategy** used (pattern, regex, embedding, etc.)
   - **Number of connections** of the token in the graph
   - **Extraction success** (whether the field was found or not)

2. **Pattern Analysis**: Based on collected occurrences, the system calculates:
   - **Mean position and standard deviation** of each field
   - **Role distribution** most common
   - **Data type distribution** most frequent
   - **Success rate** (how many times the field was found)
   - **Pattern rigidity** (how consistent the field location is)

3. **Learning Application**: During subsequent extractions, the system:
   - **Rejects inconsistent matches**: If a candidate is too far from the expected position, has a role or data type very different from the learned pattern, or if the field was never found in previous documents, it is rejected before being considered as a valid match

### Persistence

Learning is automatically saved after each extraction in:
```
~/.graph_extractor/learning.json
```
(On Windows: `C:\Users\<your_user>\.graph_extractor\learning.json`)

The file is updated incrementally, allowing knowledge to be preserved between system executions.

### Activation/Deactivation

Incremental learning is **enabled by default** and can be controlled:

- **CLI**: Use the `--no-learning` flag to disable
  ```bash
  python scripts/batch_extract.py --input data/samples --output results.json --no-learning
  ```

- **API/UI**: The `use_learning` parameter can be passed in the request (default: `true`)

- **Code**: Pass `use_learning=False` when initializing `GraphSchemaExtractor`

### Benefits

- **Continuous improvement**: Accuracy increases as more documents are processed
- **Adaptation to specific layouts**: The system learns where each field usually appears in documents of the same type
- **Reduction of false positives**: Rejects candidates that don't follow established patterns (requires at least 3 occurrences for positive patterns)
- **Transparent**: Works automatically without need for additional configuration

### Limitations

- Requires multiple extractions of the same document type to be effective (minimum of 3 occurrences to reject positive matches)
- Learned patterns are specific per `label` (document type)
- May reject valid matches if layout changes significantly
- The system only rejects inconsistent matches; there is no prioritization/boost system for matches that follow patterns


## Limitations and Trade-offs

### What Works Well

- **Structured layouts**: Documents with clear labels and values (IDs, certificates, forms)
- **Tables**: KV (key-value) and grid tables with visible structure
- **Consistent positioning**: Fields that appear in predictable locations
- **Clear labels**: Labels that correspond or are semantically similar to schema descriptions
- **Text-based PDFs**: PDFs with extractable text (not pure image scans)

### Difficult Cases

- **Highly complex layouts**: Documents with overlapping elements, unusual column structures
- **Poor OCR quality**: PDFs with low-quality text extraction or OCR errors
- **Ambiguous labels**: When multiple fields can correspond to the same label
- **Very large documents**: Processing time increases linearly with number of pages

### Trade-offs

- **Performance vs. Accuracy**: Deeper analysis (embeddings, LLM) increases accuracy but costs time/money
- **Determinism vs. AI**: Deterministic heuristics are fast and free, but LLM can handle extreme cases
- **Memory vs. Speed**: Pattern memory improves accuracy over time but requires storage
- **Multi-page vs. Single page**: Multi-page processing is more robust but slower

## License

This project is part of the Enter AI Fellowship take-home challenge. (Alexandre Bastos)
