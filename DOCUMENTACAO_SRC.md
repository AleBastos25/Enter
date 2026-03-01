# Complete Code Logic Documentation - `src` Folder

This document explains in detail all the logic, heuristics, data flow, pipeline, cache, embeddings and operation of the structured data extraction system from PDFs.

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture and Pipeline](#architecture-and-pipeline)
3. [`graph_builder` Module](#graph_builder-module)
4. [`graph_extractor` Module](#graph_extractor-module)
5. [`matching` Module](#matching-module)
6. [Cache and Embeddings System](#cache-and-embeddings-system)
7. [Incremental Learning](#incremental-learning)
8. [Complete Data Flow](#complete-data-flow)

---

## System Overview

The system is a **hybrid layout-first pipeline** for extracting structured data from PDFs. It combines:

- **Spatial analysis**: Builds a hierarchical graph that represents the document structure
- **Table detection**: Automatically identifies KV (key-value) and grid tables
- **Multi-strategy matching**: Uses regex, patterns, embeddings and LLM
- **Incremental learning**: Improves accuracy over time
- **Type validation**: 20+ field types with automatic normalization

### Design Principles

1. **Deterministic by default**: Heuristics and tables before any use of AI
2. **Cost-effective**: LLM used only when necessary, with budget control
3. **Adaptable**: Works with different document types without reconfiguration
4. **Extensible**: Easily extensible validator and hints system

---

## Architecture and Pipeline

### Main Pipeline

```
PDF → Token Extraction → Graph Construction → Role Classification → 
→ Table Detection → Multi-strategy Matching → Validation → Output
```

### Main Components

1. **TokenExtractor** (`graph_builder/extractor.py`): Extracts tokens from PDF
2. **GraphBuilder** (`graph_builder/builder.py`): Builds graph with orthogonal edges
3. **RoleClassifier** (`graph_builder/classifier.py`): Classifies tokens into LABEL, VALUE, HEADER
4. **GraphSchemaExtractor** (`graph_extractor/extractor.py`): Main orchestrator
5. **Matchers** (`graph_extractor/matchers/`): Regex, Pattern, Embedding
6. **DocumentLearner** (`graph_extractor/learner.py`): Incremental learning

---

## `graph_builder` Module

### 1. Token Extraction (`extractor.py`)

#### Extraction Process

1. **PDF Opening**: Uses PyMuPDF (fitz) to open the PDF and extract the first page
2. **Structured Text Extraction**: Uses `page.get_text("dict")` to get hierarchical structure:
   - Blocks → Lines → Spans
   - Each span contains: text, bbox, flags (bold/italic), color, font size

#### Extraction Heuristics

**Separation by Colon (`:`)**:
- Detects patterns like "Label: Value"
- Separates recursively to handle multiple colons: "Cidade: Mozarlândia U.F.: GO"
- Automatically assigns roles: token ending with `:` → LABEL, token after `:` → VALUE

**Merging Overlapping Tokens**:
- Tokens with > 80% area overlap are merged
- Tokens in consecutive lines in the same column (X overlap > 70%, Y overlap > 20%) are merged if they seem to form a coherent phrase
- After merging, checks if the resulting token has a colon in the middle and separates again

**BBox Normalization**:
- Coordinates are normalized to [0, 1] (relative to page size)
- Applies right padding (configurable, currently 0%)

#### Data Structure

```python
Token:
  - id: int
  - text: str
  - bbox: BBox (x0, y0, x1, y1 normalized)
  - font_size: float
  - bold: bool
  - italic: bool
  - color: str
  - block_id: int
  - role: Optional[str]  # LABEL, VALUE, HEADER
  - separated_pair: bool  # True if separated from a single span
```

### 2. Graph Construction (`builder.py`)

#### Graph Structure

The graph represents the document's spatial structure using **orthogonal edges**:
- **Horizontal edges**: `east` (left → right), `west` (right → left)
- **Vertical edges**: `south` (top → bottom), `north` (bottom → top)

#### Construction Process

**Phase 1: Line Grouping**
- Groups tokens by Y position (bbox center)
- Threshold: `threshold_same_line` (default: 0.005 = 0.5% of page height)
- Uses larger threshold for initial grouping (0.01) to tolerate small differences

**Phase 2: Horizontal Edges**
- For each line, sorts tokens by X (left → right)
- Creates `east` edge between consecutive tokens if:
  - They are on the same line (Y difference < threshold)
  - Horizontal gap < 3x average width (or 6x if exact same line)

**Phase 3: Vertical Edges**
- Calculates vertical spacing distribution between consecutive lines
- Uses 25th percentile (Q25) to identify "normal" gaps (ignores large outliers)
- Threshold: 2.5x base spacing OR 4.2% of page height (whichever is more restrictive)
- For each token, finds the best candidate below considering:
  - X overlap (minimum 10% of minimum width)
  - Y overlap (preferred)
  - Center alignment (difference < 60% of maximum width)
  - Vertical distance (maximum 30% of page height)

#### Vertical Connection Heuristics

1. **Candidate Priority**:
   - Candidates with Y overlap have priority
   - If there's a candidate with Y overlap, stops searching
   - Candidates without Y overlap are only accepted if they are adjacent lines

2. **Distribution Filtering**:
   - Calculates median and Q25 of vertical spacings
   - If median > 0.03, uses Q25 as base (more restrictive)
   - Rejects gaps > 2.5x base spacing

3. **Absolute Threshold**:
   - Vertical distance cannot be > 4.2% of page height
   - Ensures that even when median is high, large gaps are removed

### 3. Role Classification (`classifier.py`)

#### Rule System

The classifier uses a rule system with priorities and dependencies:

**Initial Rules** (low priority):
- `InitialLabelRule`: Tokens ending with `:` → LABEL
- `InitialValueRule`: Tokens after LABEL → VALUE
- `InitialHeaderRule`: Large, bold tokens at the top → HEADER

**Refinement Rules** (medium priority):
- `LabelOnlyConnectionsRule`: LABELs only connect with VALUEs
- `ValueLabelUniquenessRule`: VALUEs have only one LABEL
- `TypographicHierarchyRule`: Preserves typographic hierarchy
- `NumericCodeLabelRule`: Numeric codes can be LABELs
- `DateLabelCleanupRule`: Cleans labels that are dates

**Guarantee Rules** (high priority):
- `ValueLabelGuaranteeRule`: Ensures VALUEs have LABELs
- `ValueMustHaveLabelRule`: VALUE always has LABEL (HIGH PRIORITY)
- `LabelSingleValueRule`: Removes extra edges from LABEL to VALUE

**Final Rules** (maximum priority):
- `HeaderNoNorthWestRule`: Removes edges from HEADER to north/west (execute at the end)
- `AdjacentHeadersToLabelValueRule`: Converts adjacent HEADERs into LABEL + VALUE

#### Table Detection

**TableDetector** identifies two types of tables:

1. **Vertical Tables** (KV - Key-Value):
   - First column = LABELs
   - Second column = VALUEs
   - Detects pattern of two label columns (when both columns are labels)

2. **Horizontal Tables** (Grid):
   - First row = LABELs
   - Second row = VALUEs
   - Detects pattern of two label rows

**Double Label Pattern Detection Heuristics**:
- Last row/column has two values (numbers, dates, monetary values)
- Any row/column has two values of the same type
- Language patterns that indicate both are labels (e.g., "produto refinanciamento" and "sistema consignado")

#### Table Role Application

- Table roles have **maximum priority** and cannot be overridden
- Applied BEFORE classification rules
- Restored at the end (after all rules)

### 4. Adjacency Matrix (`adjacency.py`)

**AdjacencyMatrix** maintains bidirectional relationships:
- For each edge `(A, B, "east")`, creates:
  - `A.east = [B]`
  - `B.west = [A]`

**Operations**:
- `get_neighbors(token_id, direction)`: Gets neighbors in a direction
- `has_connection(from_id, to_id, relation)`: Checks specific connection
- `are_neighbors(token_id1, token_id2)`: Checks if they are neighbors in any direction

---

## `graph_extractor` Module

### 1. Main Extractor (`extractor.py`)

#### Extraction Flow

```python
extract(label, extraction_schema, pdf_path):
  1. Build graph (TokenExtractor → GraphBuilder → RoleClassifier)
  2. Initialize NodeUsageManager (tracks used nodes)
  3. PHASE 1: Regex Matching (for all fields at once)
  4. PHASE 2: Pattern + Embedding Matching (for remaining fields)
  5. Post-processing
  6. Assemble result
```

#### Phase 1: Regex Matching

**Process**:
1. For each schema field:
   - **Skips regex for name fields** (use mandatory embedding)
   - Filters nodes with at least 30% words in common with schema
   - Applies regex matching
   - Separates perfect matches (identical regex) from partial ones
   - Processes perfect matches first

**Filtering Heuristics**:
- Normalizes text (lowercase, removes accents)
- Removes stop words
- Calculates percentage of words in common: `common_words / schema_words`
- Threshold: 30% words in common

**Quality Validation**:
- Validates if the match makes sense before returning
- Validates data type (if field has specific hints)
- Rejects matches that don't correspond to learned pattern (if learning is active)

#### Phase 2: Pattern + Embedding Matching

**Matching Cascade**:

1. **Regex Matching** (if not done in Phase 1):
   - Tries regex again (for fields that didn't pass in Phase 1)
   - Separates perfect matches from partial ones
   - Validates quality and type

2. **Pattern Matching** (hints):
   - Uses hints to find typographic patterns
   - Perfect matches (score >= 0.9) have priority
   - If multiple perfect matches, uses embedding to break tie

3. **Embedding Matching**:
   - Generates embeddings from expanded query (with synonyms)
   - Calculates cosine similarity with candidates
   - Applies boost if there are keywords in the label
   - Minimum threshold: 0.3 (configurable)

4. **Tiebreaking**:
   - If multiple matches with close scores (difference < threshold):
     - Tries heuristics first
     - If heuristics don't resolve, uses LLM (if available)

#### Special Treatment of Name Fields

**Identification**:
- Checks if `NameHint` is present AND there are no other more specific hints
- If there's `AddressHint` (priority=1) and `NameHint` (priority=2), it's not a name

**Process**:
1. Filters candidates that can be names:
   - Are not addresses (using `AddressHint.detect()`)
   - Pass `NameHint.detect()` validation
   - Don't have many symbols or numbers
   - Are not known acronyms

2. Applies scoring heuristic:
   - 2+ words: +10 points
   - 1 word: +5 points
   - No numbers: +5 points
   - No strange symbols: +3 points
   - First letter uppercase in each word: +2 points
   - Minimum threshold: 10 points

### 2. Matchers (`matchers/`)

#### RegexMatcher (`regex_matcher.py`)

**Process**:
1. Generates regex from field description
2. Tries exact match (identical regex) → `MatchType.PERFECT`
3. Tries partial match (partial regex) → `MatchType.PARTIAL`
4. Returns `MatchResult` with score and type

**Heuristics**:
- Exact regex has priority over partial
- If perfect match, returns associated VALUE (if any)
- If partial match, validates type before returning

#### PatternMatcher (`pattern_matcher.py`)

**Process**:
1. Finds relevant hints for the field
2. For each hint, checks if token matches the pattern
3. Calculates score based on:
   - Pattern match (0.0 to 1.0)
   - Data type (if it matches expected type)
   - Spatial position (if it's close to label)

**Available Hints**:
- `DateHint`: Detects dates
- `MoneyHint`: Detects monetary values
- `PhoneHint`: Detects phones
- `CPFCNPJHint`: Detects CPF/CNPJ
- `AddressHint`: Detects addresses
- `NameHint`: Detects names
- `TextHint`: Generic text

#### EmbeddingMatcher (`embedding_matcher.py`)

**Process**:
1. **Query Expansion**:
   - Extracts keywords from description
   - Generates synonyms and abbreviations (e.g., "vencimento" → "venc", "vcto")
   - Repeats important words to give more weight
   - Combines everything into expanded query

2. **Embedding Generation**:
   - Uses FastEmbed (`BAAI/bge-small-en-v1.5` by default)
   - Generates embedding from expanded query
   - Generates embeddings of candidates (with cache)

3. **Similarity Calculation**:
   - Cosine similarity between normalized embeddings
   - Normalizes to [0, 1] using `(cos + 1) / 2`

4. **Keyword Boost**:
   - If there's an associated label, checks how many keywords appear in the label
   - Boost: 5% per normal match, 10% extra per important synonym
   - Limit: 35% total boost

**Embedding Cache**:
- In-memory cache: `{text_key: embedding}`
- `text_key = text.strip().lower()`
- Avoids recalculations for repeated texts

**Synonym Generation**:
- Removes accents for variations
- Generates abbreviations by consonants (e.g., "vencimento" → "vcto")
- Special cases: "vencimento" → "vcto", "referência" → "ref", "telefone" → "tel"
- General abbreviations: first 3-4 letters, first letter + main consonants

### 3. Tiebreakers (`tiebreaker/`)

#### HeuristicTieBreaker (`heuristic_tiebreaker.py`)

**Heuristics**:
1. **Relation Preference**:
   - `same_line` > `same_block` > `south_of` > `semantic`

2. **Type Preference**:
   - Perfect matches (regex/pattern) > partial matches > embeddings

3. **Position Preference**:
   - Tokens closer to top-left have priority

4. **Role Preference**:
   - VALUE > HEADER > LABEL (for values)

#### LLMTieBreaker (`llm_tiebreaker.py`)

**Process**:
1. Builds prompt with:
   - Field description
   - List of candidates with context (text, position, role)
   - Instructions to choose the best one

2. Calls LLM (GPT-4o-mini by default):
   - Temperature: 0.0 (deterministic)
   - Max tokens: 200
   - Format: JSON with choice and reason

3. Validates response:
   - Checks if choice is valid
   - Returns `MatchResult` of chosen candidate

**Budget Control**:
- Used only when heuristics don't resolve
- Can be disabled (`use_llm_tiebreaker=False`)

### 4. Node Manager (`node_manager.py`)

**NodeUsageManager** tracks which nodes were used:

**Features**:
- `mark_as_used(node_id, field_name, extracted_value)`: Marks node as used
- `is_available(node_id)`: Checks if node is available
- `can_reuse_partially(node_id, new_value)`: Checks if can partially reuse

**Partial Reuse**:
- Allows reusing nodes that contain multiple values
- Detects patterns like: "R$ 1.000,00 - R$ 2.000,00"
- Checks if new value is different from already extracted ones

**Tracking**:
- `_used_nodes`: Set of completely used nodes
- `_partial_usage`: Dict of nodes with partial usage `{node_id: {field_name: value}}`
- `_node_to_fields`: Dict of which fields used which nodes

---

## Cache and Embeddings System

### Embedding Cache

**Implementation**:
- In-memory cache in `EmbeddingMatcher`
- Key: `text.strip().lower()`
- Value: `numpy.ndarray` (normalized embedding)

**Advantages**:
- Avoids recalculations for repeated texts
- Significantly improves performance
- Cache is cleared only explicitly (`clear_cache()`)

**Limitations**:
- Cache is per instance (not shared between executions)
- Does not persist between program executions

### Embedding Generation

**Model**: FastEmbed `BAAI/bge-small-en-v1.5`
- 384-dimensional embeddings
- Normalized (unit vectors)
- Lazy loading (loaded only when necessary)

**Process**:
1. Loads model (lazy loading)
2. Generates embedding from text
3. Normalizes to unit vector
4. Stores in cache
5. Returns embedding

**Batch Processing**:
- `batch_embed(texts)`: Generates embeddings in batch (more efficient)
- Processes multiple texts at once
- Stores all in cache

---

## Incremental Learning

### DocumentLearner (`learner.py`)

#### Data Structure

**FieldOccurrence**:
- `x, y`: Spatial position (normalized coordinates)
- `role`: Token role (LABEL, VALUE, HEADER)
- `data_type`: Inferred data type
- `strategy`: Matching strategy used
- `connections`: Number of token connections in graph
- `found`: Whether field was found (True) or not (False)

**FieldPattern**:
- `field_name`: Field name
- `label_type`: Document type (label)
- `occurrences`: List of historical occurrences

**DocumentTypeLearning**:
- `label_type`: Document type
- `field_patterns`: Dict of patterns by field
- `document_count`: Number of processed documents

#### Learning Process

**Data Collection**:
1. After each extraction, records:
   - Spatial position of found field
   - Token role
   - Data type
   - Strategy used
   - Number of connections
   - Extraction success (found=True/False)

**Pattern Analysis**:
- Calculates position statistics (mean, standard deviation)
- Calculates role distribution
- Calculates data type distribution
- Calculates success rate (found_rate)
- Calculates pattern rigidity (inverse of variance)

**Learning Application**:
- **Rejection of Inconsistent Matches**:
  - If field was never found (found_rate=0) in 2+ documents → rejects any match
  - If field was found most of the time (>=80%) and pattern is rigid (>=0.7), but current match doesn't correspond → rejects
  - Checks position, role, data type, connections

**Pattern Rigidity**:
- Calculates rigidity (0 = very variable, 1 = very rigid) based on:
  - Position variance (normalized)
  - Role consistency (probability of most common role)
  - Type consistency (probability of most common type)
  - Connection variance

#### Persistence

**File**: `~/.graph_extractor/learning.json` (Windows: `C:\Users\<usuario>\.graph_extractor\learning.json`)

**Format**:
```json
{
  "type_learnings": {
    "label_type": {
      "label_type": "carteira_oab",
      "document_count": 10,
      "field_patterns": {
        "nome": {
          "field_name": "nome",
          "label_type": "carteira_oab",
          "occurrences": [...]
        }
      }
    }
  }
}
```

**Saving**:
- Saves after each learning (incremental persistence)
- Indented JSON format for readability

**Loading**:
- Loads automatically on initialization
- Singleton shared between UI and CLI

#### Limitations

- Requires multiple extractions of the same document type to be effective
- Minimum of 3 occurrences to reject positive matches
- Learned patterns are specific per `label` (document type)
- May reject valid matches if layout changes significantly
- Only rejects inconsistent matches (no prioritization/boost system)

---

## Complete Data Flow

### 1. Input: PDF + Schema

**Input**:
- `pdf_path`: Path to PDF file
- `label`: Document type (e.g., "carteira_oab")
- `extraction_schema`: Dict `{field: description}`

**Example**:
```python
{
  "nome": "Nome do profissional, normalmente no canto superior esquerdo",
  "inscricao": "Número de inscrição do profissional",
  "seccional": "Seccional do profissional (sigla UF)",
  "situacao": "Situação do profissional, normalmente no canto inferior direito"
}
```

### 2. Token Extraction

**Process**:
1. Opens PDF with PyMuPDF
2. Extracts first page
3. Gets hierarchical structure: blocks → lines → spans
4. For each span:
   - Normalizes bbox to [0, 1]
   - Extracts metadata (font, bold, italic, color)
   - Separates by colon if necessary
   - Merges overlapping tokens
5. Returns list of `Token`

**Output**: List of `Token` with coordinates, style and text

### 3. Graph Construction

**Process**:
1. Groups tokens by lines (similar Y)
2. Creates horizontal edges (east/west) between tokens on same line
3. Creates vertical edges (south) between tokens on different lines
4. Returns `Graph` with nodes and edges

**Output**: `Graph` with:
- `nodes`: List of `Token`
- `edges`: List of `Edge` (from_id, to_id, relation)

### 4. Role Classification

**Process**:
1. Detects tables (TableDetector)
2. Applies table-based classification (high priority)
3. Executes classification rules in priority order
4. Restores table roles (maximum priority)
5. Applies roles to tokens

**Output**: Dict `{token_id: role}` and list of `Table`

### 5. Multi-strategy Matching

**Phase 1: Regex Matching** (fast):
1. For each field:
   - Filters nodes with 30%+ words in common
   - Applies regex matching
   - Separates perfect matches from partial ones
   - Processes perfect matches first
   - Validates quality and type
   - Learns from result

**Phase 2: Pattern + Embedding Matching** (for remaining fields):
1. Regex Matching (if not done in Phase 1)
2. Pattern Matching (hints)
3. Embedding Matching (semantic similarity)
4. Tiebreaking (heuristics → LLM)

**Output**: Dict `{field_name: FieldMatch}`

### 6. Validation and Normalization

**Process**:
1. For each `FieldMatch`:
   - Validates type using validators (if field has specific hints)
   - Normalizes value (dates, monetary values, etc.)
   - Checks if match makes sense (using learning if active)

**Available Validators**:
- `date`: Normalizes to `YYYY-MM-DD`
- `money`: Normalizes to decimal (e.g., `76871.20`)
- `cpf`, `cnpj`: Validates and normalizes
- `phone_br`: Normalizes to E.164
- `uf`: Validates state code (2 uppercase letters)
- And 15+ more types...

### 7. Post-processing

**Process**:
1. Converts match dictionary to list (maintains original order)
2. Assembles final result:
   - `fields`: Dict `{field: value}` (None if not found)
   - `field_matches`: List of `FieldMatch` with details
   - `metadata`: Statistics (time, strategies, nodes used)

**Output**: `ExtractionResult` with:
- `label`: Document type
- `fields`: Dict of extracted fields
- `field_matches`: Detailed list of matches
- `metadata`: Extraction metadata

### 8. Learning (if active)

**Process**:
1. For each extracted field:
   - Records occurrence with:
     - Spatial position (x, y)
     - Token role
     - Data type
     - Strategy used
     - Number of connections
     - Success (found=True/False)
2. Saves learning to JSON file

**Output**: Updated `learning.json` file

---

## Detailed Heuristics

### Token Extraction Heuristics

1. **Separation by Colon**:
   - Detects pattern "text: text"
   - Separates recursively for multiple colons
   - Automatically assigns roles

2. **Token Merging**:
   - Overlap > 80% → merge
   - Consecutive lines in same column (X overlap > 70%, Y overlap > 20%) → merge if they seem to form phrase

3. **Coordinate Normalization**:
   - Normalizes to [0, 1] (relative to page size)
   - Facilitates comparison between documents of different sizes

### Graph Construction Heuristics

1. **Line Grouping**:
   - Threshold: 0.5% of page height (default)
   - Uses larger threshold (1%) for initial grouping

2. **Horizontal Edges**:
   - Maximum gap: 3x average width (or 6x if exact same line)
   - Sorts tokens by X (left → right)

3. **Vertical Edges**:
   - Uses spacing distribution (Q25) to identify normal gaps
   - Threshold: 2.5x base spacing OR 4.2% of height (more restrictive)
   - Prioritizes candidates with Y overlap
   - Requires minimum X overlap of 10% OR center alignment

### Role Classification Heuristics

1. **Priority Rules**:
   - Initial rules (low) → Refinement rules (medium) → Guarantee rules (high) → Final rules (maximum)
   - Table roles have maximum priority

2. **Table Detection**:
   - Vertical tables: col 0 = LABELs, col 1 = VALUEs
   - Horizontal tables: row 0 = LABELs, row 1 = VALUEs
   - Detects pattern of two columns/rows of labels

### Matching Heuristics

1. **Word Similarity Filtering**:
   - Threshold: 30% words in common
   - Normalizes text (lowercase, removes accents)
   - Removes stop words

2. **Strategy Priority**:
   - Perfect regex > Partial regex > Perfect pattern > Partial pattern > Embedding

3. **Keyword Boost**:
   - 5% per normal match
   - 10% extra per important synonym
   - Limit: 35% total boost

4. **Tiebreaking**:
   - Heuristics first (relation, type, position, role)
   - LLM only if heuristics don't resolve

### Learning Heuristics

1. **Match Rejection**:
   - Field never found (2+ documents) → rejects any match
   - Field found most of the time (>=80%) + rigid pattern (>=0.7) + match doesn't correspond → rejects

2. **Pattern Rigidity**:
   - Calculates variance of position, role, type, connections
   - Normalizes and combines into rigidity score (0-1)

---

## Performance Considerations

### Optimizations

1. **Embedding Cache**:
   - Avoids recalculations for repeated texts
   - Significantly improves performance

2. **Lazy Loading**:
   - Embedding model loaded only when necessary
   - Reduces initialization time

3. **Batch Processing**:
   - Embeddings generated in batch when possible
   - More efficient than processing one by one

4. **Early Stopping**:
   - Stops searching when finds perfect match
   - Reduces number of operations

### Limitations

1. **Processing Time**:
   - Increases linearly with number of pages
   - Embeddings can be slow (depends on model)

2. **Memory**:
   - Complete graph kept in memory
   - Embedding cache can grow

3. **Cost**:
   - LLM used only when necessary
   - Embeddings are free (local model)

---

## Extensibility

### Add New Field Type

1. Create validator in `graph_extractor/hints/`
2. Register hint in `hints/base.py`
3. Add type in validators if necessary

### Add New Classification Rule

1. Create class inheriting from `BaseRule` in `graph_builder/rules/`
2. Implement `apply(context)` and `can_apply(executed_rules)`
3. Register in `RoleClassifier._register_default_rules()`

### Add New Matcher

1. Create class inheriting from `BaseMatcher` in `graph_extractor/matchers/`
2. Implement `match(field_name, field_description, candidates, graph)`
3. Add to pipeline in `GraphSchemaExtractor._extract_field_with_pattern_embedding()`

---

## Conclusion

This system implements a robust and extensible pipeline for extracting structured data from PDFs, combining spatial analysis, table detection, multi-strategy matching and incremental learning. The modular architecture allows easy extension and maintenance, while optimized heuristics ensure good performance and accuracy.
