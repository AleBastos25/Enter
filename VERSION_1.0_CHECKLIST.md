# Problem Brief — Document Extraction Challenge (What to Build & Why)

> This brief describes the **task, rules, inputs, outputs, constraints, and evaluation** of the challenge.
> It deliberately avoids prescribing *how* to implement a solution. It only defines **what** the system must achieve.

---

## 1) Goal

Build a system that, given:

* a **PDF document** (unknown template; may vary widely in layout and style), and
* an **extraction schema** (a dictionary of `field_name → natural-language description`),

returns a **structured JSON** with the best extracted value for each field, plus **confidence** and a compact **trace** that explains where the value came from.

The system must **generalize** across unseen layouts. It should **not** rely on a fixed template per document type.

---

## 2) Context

Real-world PDFs come from many sources:

* ID cards, certificates, receipts, invoices, forms
* “System screens” exported as PDF
* Multi-column pages, tables, badges, stamps, watermarks, etc.

Labels may appear:

* on the **same line** as the value (e.g., `Label: VALUE`)
* **to the right** of the label on the same line
* **below** the label in the same column
* **inside tables**
* **in the same block** without punctuation (e.g., `STATUS ACTIVE`)
* with **abbreviations**, synonyms, or formatting variations

Values may be:

* single tokens (e.g., `PR`)
* alphanumeric IDs (e.g., registration numbers)
* dates, money amounts, percentages
* enums (e.g., `REGULAR`, `PAID`, `PENDING`)
* multi-line text (e.g., addresses)

---

## 3) Inputs

1. **PDF file**

   * 1+ pages.
   * May be a text PDF or a PDF produced from OCR.
   * Quality, fonts, and structure may vary.

2. **Extraction schema** (JSON)

   * A dictionary: `{ "field_name": "natural-language description of what this field means / where it often appears" }`.
   * Descriptions may hint typical **position** (e.g., “usually top-left”), **format** (e.g., “a date”), or **category** (e.g., “status enum”).
   * The schema can differ per file, even for the same document label.

3. (Optional) **Document label** (e.g., `"carteira_oab"`, `"tela_sistema"`)

   * A coarse category to group similar documents.
   * Your system **must not** assume a fixed template even when labels coincide.

---

## 4) Required Output

A JSON object:

```json
{
  "label": "<document_label_or_unknown>",
  "results": {
    "<field_name>": {
      "value": "<normalized string or null>",
      "confidence": <float 0.0–1.0>,
      "source": "<short tag: heuristic | table | llm | none>",
      "trace": {
        "page_index": <int>,
        "node_id": "<internal reference or block/cell id>",
        "relation": "<e.g., same_line_right_of | first_below_same_column | same_block | same_table_row | other>",
        "notes": "<short optional details>"
      }
    },
    "...": { }
  }
}
```

### Output expectations

* **Value normalization** is expected (e.g., dates → `YYYY-MM-DD`, money → numeric with dot decimal, enums standardized to uppercase canonical form).
* **Confidence** reflects your internal belief (comparative between sources/relations), not a formal probability.
* **Trace** must be compact and informative enough to help debugging (page, where it came from, and how it was found).

If a value **cannot be extracted reliably**, return `"value": null` with `"source": "none"` and a trace that clarifies the last decision path.

---

## 5) Rules & Constraints

1. **Generalization over templates**

   * The system should handle **arbitrary** layouts and not overfit to a handful of sample PDFs.
   * Expect **different fonts, cases, positions, and formatting**.

2. **Multiple pages**

   * PDFs may have multiple pages. Your solution must be prepared to process **N pages** and decide when it has **enough** information to stop.

3. **Tables and structured regions**

   * Documents might encode information in **tables** (with or without visible ruling lines) or **KV-lists** (label–value lists).
   * Values may be spread across **cells** or **rows**.

4. **Ambiguity**

   * Labels may be abbreviated or reworded.
   * Multiple blocks may look relevant; choose the **best candidate** and provide a meaningful **confidence**.

5. **Validation & normalization**

   * Many fields have **implied formats** (dates, UF/state abbreviations, CEP/ZIP, money, IDs).
   * Return values **normalized** when a format is expected. If the text does not fit a plausible format, it should not be returned as a confident value.

6. **Determinism & explainability**

   * Two runs on the **same inputs** should produce **the same outputs** (within reasonable nondeterminism tolerances).
   * The **trace** must justify the choice (e.g., “value found to the right of label on the same line on page 1”).

7. **Performance & cost**

   * The pipeline must be **reasonably fast** on a single machine for typical single- or few-page PDFs.
   * If using any external intelligence (e.g., LLM), keep usage minimal and controllable (budgets, timeouts).
   * The system should **not** require internet access to run on the test set.

8. **Safety & privacy**

   * Do not send document content to third-party services unless explicitly allowed.
   * Do not store sensitive content beyond what is necessary for local processing and reproducibility.

---

## 6) Typical Field Types & Examples

> The schema may imply types. Below are examples of **expected formats** that evaluators may check.

* **Text** (single- or multi-line): names, addresses, product names.
* **Enum**: e.g., `REGULAR`, `SUSPENSO`, `CANCELADO`, `PAID`, `PENDING`.
* **Date**: normalized to `YYYY-MM-DD`.
* **Money**: parse `R$ 76.871,20` → `76871.20` (decimal dot, no currency symbol).
* **Percent**: `12,5%` → `12.5`.
* **UF / State code**: `PR`, `SP`, etc. (2-letter uppercase).
* **CEP / ZIP**: 8 digits (Brazil) normalized without punctuation.
* **IDs / Alphanumeric codes**: at least one digit and length ≥ 3; preserve separators if meaningful.
* **Phones / Emails**: normalized (phones E.164 if BR is applicable).

If you support more validators (e.g., CPF/CNPJ/PLATE), normalize to canonical forms.

---

## 7) Evaluation (What matters)

The evaluation focuses on:

* **Coverage**: ratio of fields with a **non-null** value.
* **Format Validity**: % of extracted values that **pass validation/normalization** for their type.
* **Correctness**: manual checks on a subset for semantic correctness (e.g., correct ID number vs random digits).
* **Robustness**: ability to handle layout variation (same field in a different place, alternate label wording, presence/absence of tables).
* **Latency**: time per document (median and tail).
* **Explainability**: whether the **trace** is useful to understand decisions.
* **Cost discipline**: if LLMs are used, calls are **bounded** and **optional** (solution must run without them).

You should expect test PDFs **not present** in the provided small dataset, with schemas that may partially overlap or differ.

---

## 8) Non-Goals

* Pixel-perfect reproduction of the visual layout is **not** required.
* Full table reconstruction is **not** required unless it directly supports field extraction from tables.
* End-to-end OCR is **not** the target of this challenge (assume text is extractable from the PDFs you’ll be evaluated on).

---

## 9) CLI Requirements (to ease evaluation)

Provide a simple command-line interface to run the extractor on one PDF + one schema:

```bash
python -m <your_package>.app.cli --run \
  --label "<label_or_unknown>" \
  --schema path/to/schema.json \
  --pdf path/to/document.pdf \
  [--multi-page] [--no-embedding] [--no-llm] [--debug]
```

* **Input schema**: a JSON file with `{ "field_name": "description", ... }`.
* **Output**: print the JSON described in Section 4 to stdout (and optionally save to a file if a `--out` flag is provided).
* **Debug mode** (optional): dump auxiliary diagnostics (e.g., probed blocks, candidate relations, page indices).

---

## 10) Dataset Provided (for quick smoke tests)

A tiny sample dataset is provided (few PDFs and a `dataset.json`) for basic smoke testing.
**Do not** tune your solution exclusively to these files — evaluators will use **different PDFs** and schemas.

---

## 11) Quality Checklist (what reviewers will look for)

* ✅ Handles **unknown layouts** and **multiple pages**.
* ✅ Extracts values even when labels differ slightly (abbreviations, casing).
* ✅ Works with **values inline with labels**, to the **right**, **below**, or **inside tables**.
* ✅ Returns **normalized** values and **null** when unsure.
* ✅ Produces a **compact, meaningful trace** (page, relation, node/cell reference).
* ✅ Performance is reasonable; any AI usage is **limited and optional**.
* ✅ No hard-coded assumptions about a particular PDF.

---

## 12) Deliverables

* **Source code** in a clean repository (clear structure, readable code, small docs).
* **README** with quickstart and examples.
* **CLI** as specified.
* **A short note** on limitations and trade-offs (what your system handles well vs. edge cases that remain hard).
* **No secrets committed** (keys, tokens). Any advanced features dependent on keys must run **off** by default.

---

## 13) Final Notes

* This problem rewards **robustness**, **interpretability**, and **good engineering** (clear inputs/outputs, predictable behavior).
* Creativity is welcome, but the system must remain **auditable** (we need to see *why* a value was chosen).
* Keep the solution **modular** so future teams can extend validators, add new field types, or plug different matching strategies.

Good luck!
