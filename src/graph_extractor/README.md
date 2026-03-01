# Graph-based Schema Extractor

Schema extraction system based on hierarchical token graph. Uses a cascade of matching strategies to find values corresponding to each field in the extraction schema.

## Features

- **Hierarchical graph**: Builds token graph with spatial relationships (orthogonal edges)
- **Matching cascade**: Pattern → Regex → Embeddings → Tiebreaking
- **Hints/Patterns**: Hint system to identify specific types (date, money, address, etc.)
- **Semantic embeddings**: Uses FastEmbed for semantic matching
- **Intelligent tiebreaking**: Heuristics + LLM to break ties between candidates
- **Node management**: Avoids reusing already extracted nodes

## Basic Usage

```python
from src.graph_extractor import GraphSchemaExtractor

# Initialize extractor
extractor = GraphSchemaExtractor(
    embedding_model="BAAI/bge-small-en-v1.5",
    min_embedding_similarity=0.3,
    tiebreak_threshold=0.05,
    llm_model="gpt-5-mini",
    use_llm_tiebreaker=True
)

# Define schema
schema = {
    "nome": "Nome do profissional",
    "inscricao": "Número de inscrição do profissional",
    "seccional": "Seccional do profissional",
}

# Extract information
result = extractor.extract(
    label="carteira_oab",
    extraction_schema=schema,
    pdf_path="data/samples/oab_1.pdf"
)

# Access results
print(result["fields"])
print(result["metadata"])
```

## Architecture

### Matching Cascade

1. **Pattern Matching (Hints)**
   - Applies relevant hints for the field
   - Detects patterns (date, money, CPF/CNPJ, phone, address, text)
   - Score based on perfect/partial match

2. **Regex Matching**
   - Text normalization (removes accents, lowercase)
   - Perfect match: field name found in token
   - Regex match: uses patterns from hints
   - Partial match: keywords found

3. **Embedding Matching**
   - Generates embeddings using FastEmbed
   - Calculates cosine similarity between field description and tokens
   - Compares with combined LABEL+VALUE or just VALUE

4. **Tiebreaking**
   - **Heuristics**: Token type, document order, text size, LABEL-VALUE distance
   - **LLM**: Used when heuristics don't resolve (GPT-5-mini by default)

### Hint System

Pre-defined hints to identify specific patterns:

- **DateHint**: Detects dates in various formats
- **MoneyHint**: Detects monetary values (R$, $, €, etc.)
- **CPFCNPJHint**: Detects CPF/CNPJ
- **PhoneHint**: Detects phone numbers
- **AddressHint**: Detects addresses and aggregates multiple VALUEs
- **TextHint**: Fallback for generic text

### Node Management

- Tracks already used nodes to avoid duplication
- Supports partial reuse (e.g., "R$ 1.000,00 - R$ 2.000,00")
- Marks nodes as used after extraction

## Output Format

```json
{
  "label": "carteira_oab",
  "fields": {
    "nome": "JOÃO DA SILVA",
    "inscricao": "101943",
    "seccional": "SP"
  },
  "metadata": {
    "total_fields": 3,
    "extracted_fields": 3,
    "success_rate": 1.0,
    "nodes_used": [5, 12, 18],
    "nodes_used_count": 3,
    "extraction_time": 2.5,
    "strategies_breakdown": {
      "nome": "pattern_perfect",
      "inscricao": "regex_perfect",
      "seccional": "embedding"
    }
  }
}
```

## Matching Strategies

- `pattern_perfect`: Perfect match via hints
- `pattern_perfect_tiebreak`: Multiple perfect matches, tiebreaking needed
- `regex_perfect`: Perfect match via regex
- `regex_perfect_tiebreak`: Multiple perfect matches, tiebreaking needed
- `regex_partial`: Partial match via regex
- `embedding`: Match by semantic similarity
- `embedding_tiebreak`: Match by embeddings with tiebreaking
- `none`: No match found

## Dependencies

- `fastembed>=0.2.0`: For fast semantic embeddings
- `openai>=1.0.0`: For LLM tiebreaker (optional)
- `numpy>=1.20.0`: For similarity calculations
- Components from `graph_builder`: TokenExtractor, GraphBuilder, RoleClassifier

## Configuration

### Extractor Parameters

- `embedding_model`: FastEmbed model (default: "BAAI/bge-small-en-v1.5")
- `min_embedding_similarity`: Minimum similarity for embeddings (0.0 to 1.0, default: 0.3)
- `tiebreak_threshold`: Threshold to consider tie (default: 0.05)
- `llm_model`: LLM model for tiebreaker (default: "gpt-5-mini")
- `use_llm_tiebreaker`: If True, uses LLM when heuristics don't resolve (default: True)

### API Key (LLM Tiebreaker)

Configure the OpenAI API key:

```bash
# Environment variable
export OPENAI_API_KEY=sk-...

# Or in configs/secrets.yaml
OPENAI_API_KEY: sk-...
```

## Limitations

- PDFs must have OCR done (embedded text)
- Processes only first page of PDF
- Performance depends on number of nodes in graph
- LLM tiebreaker adds cost and latency

## Complete Example

See `test_graph_extractor.py` for a complete usage example.
