# ✅ PROMPT PARA O CURSOR (v1.0)

Quero que você evolua o projeto atual para a **versão v1.0** com as capacidades abaixo, preservando a filosofia **layout-first**, extração **determinística** e uso **controlado** de IA. Faça PRs/commits atômicos e escreva código claro, tipado e testável.

## 0) Contexto (estado atual)

* Já existem: `pdf_loader` (1 página), `layout.builder` (linhas básicas + vizinhança), `matching.matcher` (right-of / below), `extraction.text_extractor` (multi-linha/multi-token), `validation.validators` (11 tipos), `core.pipeline`, `schema.enrich` (tipos/sinônimos + hints).

* Já discutimos correções: `same_block`, `global_enum_scan`, endurecer `id_simple` exigindo dígito, bônus por coluna/seção, enum normalizado, etc.

* Objetivo agora: **v1.0 "quase final"** com:

  1. **Multi-page** + hierarquia page→column→section→paragraph→line;
  2. **Tabelas v1** (KV-list + grid, com/sem linhas vetoriais);
  3. **Semantic matcher (embeddings)** com cache e thresholds;
  4. **LLM fallback leve** (budget/timeout/guard por validadores);
  5. **PatternMemory** (sinônimos/offsets/fingerprint/shape) incremental;
  6. **Validadores BR** (CPF/CNPJ/etc.);
  7. **Policies** de tempo/memória/early-stop;
  8. Configs externas, scripts de smoke e CLI.

## 1) Requisitos funcionais (v1.0)

* Ler **PDFs multi-page**; parar cedo se todos os campos atingirem confiança mínima.

* Construir **layout por página** com `line` + `column` + `section` + **`paragraph`**; vizinhanças consistentes.

* Detectar **tabelas v1**:
  * **KV-list** (rótulo→valor) e **grid** (com/sem linhas vetoriais).
  * Integrar ao matcher: priorizar `same_table_row`.

* Matching híbrido:
  * Substring + sinônimos + **semantic seeds** (embeddings) top-K por campo;
  * Regras espaciais: `same_line_right_of` > `same_table_row` > `same_block` > `first_below_same_column` > `global_enum_scan`.
  * Bônus/penalidades por **coluna/seção/parágrafo/página**.

* **Extract & Validate**:
  * Extrair candidato (linhas/janelas/n-grams); validar/normalizar por tipo; nunca aceitar texto cru de LLM.

* **LLM fallback leve**:
  * Máx **2 chamadas/PDF** (config), **timeout curto**, usar só em janelas pequenas quando score ∈ [min,max].
  * Toda saída passa pelos **validadores**; se falhar, descartar.

* **PatternMemory** por `label` (aprendizado incremental):
  * Aprende **sinônimos observados**, **offsets** (dx,dy + relation), **fingerprints** (grid 4×4 label/valor + seção/coluna), **value shape** (regex-id/enum/len).
  * Usa memória como **bônus** no ranking e **injeção de sinônimos** (limites e decay).

* **Validadores BR** novos: `cpf`, `cnpj`, `phone_br` (E.164), `placa_mercosul`, `pis_pasep`, `cnh` (opcional), `chave_nf`, além de `email` robusto e `alphanum_code`.
  **Endureça `id_simple`**: exigir pelo menos **1 dígito**.

* **Config & Runtime**:
  * `runtime.yaml` (timeouts, limites, early-stop), `tables.yaml`, `embedding.yaml`, `llm.yaml`, `memory.yaml`.
  * Cache de embeddings em disco; eviction de índices por página.

* **CLI & scripts**:
  * `src/app/cli.py` com flags para: multi-page, LLM on/off, embedding on/off, dumps de debug.
  * `scripts/` com smokes: `smoke_pipeline.py`, `smoke_tables.py`, `smoke_embedding.py`, `smoke_llm.py`, `smoke_multipage.py`, `smoke_memory.py`.

## 2) Estrutura de pastas (consolide/complete)

```
src/
  app/cli.py
  core/{__init__.py, models.py, pipeline.py, schema.py, policy.py}
  io/{__init__.py, pdf_loader.py, cache.py}
  layout/{__init__.py, builder.py, heuristics.py}
  matching/{__init__.py, matcher.py}
  extraction/{__init__.py, text_extractor.py}
  validation/{__init__.py, validators.py}
  tables/{__init__.py, detector.py, extractor.py}
  embedding/{__init__.py, client.py, index.py, policy.py}
  llm/{__init__.py, client.py, prompts.py, policy.py}
  memory/{__init__.py, pattern_memory.py, store.py, schema.py, scoring.py}

configs/
  runtime.yaml
  tables.yaml
  embedding.yaml
  llm.yaml
  memory.yaml

scripts/
  smoke_pipeline.py
  smoke_tables.py
  smoke_embedding.py
  smoke_llm.py
  smoke_multipage.py
  smoke_memory.py
```

## 3) Implementações detalhadas

### 3.1 Loader (multi-page) — `io/pdf_loader.py`

* Remover restrição 1 página.
* API:
  ```python
  def load_document(pdf_path: str, *, label=None, doc_id=None) -> Document
  def iter_page_blocks(document: Document) -> Iterator[tuple[int, list[Block]]]
  ```
* Cada `Block` com `page=page_idx`; bbox **normalizada por página** (0..1).
* `Document.meta["page_count"]`.

### 3.2 Layout & Hierarquia — `layout/builder.py`, `layout/heuristics.py`

* `ReadingNode(type="page")` por página.
* `line` nodes a partir das linhas do PyMuPDF (já temos base).
* **Columns**: clustering por `cx` de linhas (gap-based; K≤3; `min_gap_x_norm`, `min_col_width_norm`).
* **Sections**: detecção de "títulos" por `font_size` boost + gap vertical.
* **Paragraphs**: agrupar linhas consecutivas da **mesma coluna/seção** por gap vertical e alinhamento de margem.
* Índices: `column_id_by_block`, `section_id_by_block`, `paragraph_id_by_block`.
* `layout.meta["pdf_lines"]` (opcional): linhas vetoriais normalizadas (`page.get_drawings()`).

### 3.3 Tabelas v1 — `tables/detector.py`, `tables/extractor.py`

* **KV-list**: duas "colunas" implícitas label/valor por linha; usar gaps X e overlap Y; aceitar se `rows ≥ min_rows`.
* **Grid**: com/sem linhas vetoriais; construir grade por interseção de faixas; marcar `header` por boost de `font_size`.
* `TableStructure{ type in {"kv","grid"}, rows, cells, col_count }` por página.
* `extractor.find_cell_by_label`:
  * KV: match no col 0 → retorna célula col 1 na mesma row.
  * Grid: `search_in="header"` (mesma coluna, próxima row) ou `"first_col"` (mesma row, próxima coluna) ou `"any"`.
* Integração matcher: gerar `FieldCandidate(relation="same_table_row")` prioritário.

### 3.4 Matching — `matching/matcher.py`

* Label discovery:
  * substring/sinônimos (schema + **memória** injetada),
  * **semantic seeds** (top-K por campo do índice da página; aplicar thresholds por tipo).
* Candidatos:
  * `same_line_right_of`, `first_below_same_column`, **`same_table_row`**, **`same_block`** (apenas se o bloco tiver token do rótulo), **`global_enum_scan`** para `enum` quando vazio.
* **Gates por tipo**:
  * Tipos que **exigem dígito** (`id_simple`,`cep`,`money`,`date`,`int`,`float`,`percent`):
    * subir `min_cosine` do seed;
    * descartar destino sem **dígitos**.
* Bônus/penalidades:
  * `prefer_same_column`, `prefer_same_section`, **prefer_same_paragraph**, **page-aware** (páginas iniciais + sinais de página).
  * **PatternMemory**: bônus por sinônimo aprendido/offset/fingerprint.
* Score final (exemplo):
  ```
  score = 0.55*type_ok + 0.25*spatial + 0.10*semantic + 0.10*memory_bonus
  ```
  Cap em 1.0. Ordem final por `relation` preferida (ver 3.6).

### 3.5 Extractor — `extraction/text_extractor.py`

* Para cada `FieldCandidate`, gerar candidatos textuais:
  * "após rótulo" (split por sinônimo no `same_block`), primeiras 1–3 linhas, janelas 2–3 linhas, n-grams 1..3 dos primeiros tokens; em **tabela**, usar texto da célula.
* Validar com `validate_and_normalize(field.type, ...)` (enum com `enum_options`).
* Confiança por relação:
  * `same_line_right_of=0.90`, `same_table_row=0.85`, `same_block=0.85`, `first_below_same_column=0.80`, `global_enum_scan=0.75`.
* `trace` inclui `node_id`, `relation`, `page_index`, e (se disponível) `scores.semantic`, `memory={...}` e pequenos "evidences".

### 3.6 Pipeline — `core/pipeline.py`, `core/policy.py`

* `runtime.yaml`: timeouts (doc/página/LLM), limites (páginas, blocos, candidatos), early-stop (min_conf por campo), memory (eviction).
* Loop por páginas:
  1. build layout;
  2. detectar tabelas;
  3. construir/recuperar índice de embeddings **por página** (com cache + eviction);
  4. **page signals**: cosine máx por campo (top-K pequeno); pular página se sem sinais;
  5. matching → extraction → validação;
  6. **fusão de resultados entre páginas** (por campo: preferir relações fortes; depois maior confidence);
  7. early-stop se todos ≥ `min_confidence_per_field`.
* `LLM fallback` (se habilitado via `llm.yaml`):
  * Disparar só se `budget_left` e (sem valor válido **ou** score ∈ [min,max]);
  * prompt curto, **somente JSON**; parse, **validar**, aceitar se ok; `source="llm"` e `confidence ≤ 0.75`.
* **PatternMemory**:
  * Carregar no início (`memory.yaml`); injetar sinônimos no matcher (limite).
  * Após cada extração com `confidence ≥ learn.min_confidence` e `relation` ∈ `accept_relations`, **learn**: salvar sinônimo/offset/fingerprint/shape.
  * `decay` e `pruning` ao salvar; `commit()` no final.

### 3.7 Embeddings — `embedding/*`

* `EmbeddingClient`: adapters local/Noop; **cache** em disco (`.cache/embeddings`), vetores unit-norm.
* `CosineIndex` por página; limita `max_blocks_indexed_per_page` e **evict** páginas antigas (LRU).
* `embedding.yaml`: `enabled`, `provider`, `model`, `dim`, `index.top_k_per_field`, `min_sim_threshold`, `budget` (se remoto), `cache`.

### 3.8 LLM — `llm/*`

* `LLMClient` com `NoopClient` quando sem chave/disabled.
* `policy`: orçamento por PDF, timeout global, trigger `[min_score, max_score]`, char-limits do contexto.
* `prompts`: curto, **retornar só** `{"value":"..."}`; parse defensivo.

### 3.9 PatternMemory — `memory/*`

* `store`: JSON por `label` em `data/artifacts/pattern_memory/{label}.json`.
* `schema`: dataclasses `FieldMemory`, `SynonymObs`, `OffsetObs`, `FingerprintObs`, `ValueShapeObs`.
* `pattern_memory`: API `get_*` e `learn(...)` conforme discutido.
* `scoring`: funções de bônus para matcher.

### 3.10 Validadores — `validation/validators.py`

* **Endurecer `id_simple`**:
  ```python
  ID_SIMPLE_RE = re.compile(r"(?=[A-Za-z0-9.\-/]*\d)[A-Za-z0-9.\-/]{3,}")
  ```
* Adicionar: `cpf`, `cnpj` (com DV), `email`, `phone_br` (normalizar para `+55...`), `placa_mercosul`, `pis_pasep`, `cnh` (opcional), `chave_nf`, `alphanum_code`.
  Todos **extrativos** e **normalizadores**; retornam `(ok, normalized)`.

## 4) Configs — crie com defaults seguros

* `configs/runtime.yaml`, `configs/tables.yaml`, `configs/embedding.yaml`, `configs/llm.yaml`, `configs/memory.yaml` com valores sugeridos nos briefs anteriores.

* Se ausentes, usar **defaults embutidos** (não quebrar execução).

## 5) CLI & Scripts

* `src/app/cli.py`:
  * `--probe`, `--run`, `--label`, `--schema`, `--pdf`, `--multi-page`, `--no-embedding`, `--no-llm`, `--layout-debug`, `--dump-tables`.

* `scripts/`:
  * `smoke_pipeline.py` (end-to-end),
  * `smoke_tables.py`, `smoke_embedding.py`, `smoke_llm.py`, `smoke_multipage.py`, `smoke_memory.py`.
    Mostram contagens e exemplos; não "engessam" por valores específicos do PDF.

## 6) Qualidade, logs e performance

* Logging `INFO/DEBUG` com mensagens úteis: "skip page (no signals)", "early stop", "embedding cache hit/miss", "LLM fallback used", "memory bonuses applied".

* Ordenações estáveis (`sorted` por `(y0,x0)`); seeds/thresholds constantes.

* Evitar N^2 desnecessário; cortar candidatos com limites configuráveis.

## 7) Regressões a evitar (checklist)

* Campo `inscricao` **nunca** aceitar tokens sem dígito.
* `situacao` encontrada em:
  * `same_block` (ex.: "SITUAÇÃO REGULAR"),
  * `same_table_row` quando em tabela,
  * `global_enum_scan` se faltar rótulo (desempate com `position_hint`).
* Multi-page: resultados finais trazem `trace.page_index`.
* Com `embedding.enabled=false` e `llm.enabled=false`: tudo funciona como heurística pura.

## 8) Sequência de commits (sugestão)

1. `feat(io): multi-page loader and iter_page_blocks`
2. `feat(layout): page/column/section/paragraph nodes + indices`
3. `feat(tables): KV-list and grid detection + extractor; pipeline wiring`
4. `feat(embedding): client, cosine index per page, cache + policy`
5. `feat(matching): seeds + same_table_row + same_block (gated) + global_enum_scan + type-aware gates + page/section/paragraph bonuses`
6. `feat(extraction): label-aware split and confidence mapping per relation`
7. `feat(validation): strengthen id_simple and add BR validators (cpf/cnpj/...)`
8. `feat(llm): client/policy/prompts + guarded fallback`
9. `feat(memory): pattern memory store/learn/scoring + matcher integration`
10. `feat(core): runtime policy (timeouts/early-stop/memory) + multi-page fusion`
11. `chore(configs,scripts): add YAMLs and smoke scripts; improve CLI`
12. `docs: update README/STATUS for v1.0`

## 9) Aceitação v1.0 (definição de pronto)

* Roda em PDFs 1+ páginas; **pula páginas** sem sinais; **para cedo** quando tudo >= conf mínima.

* Extrai campos típicos (`inscricao`, `seccional`, `situacao`, `endereco_profissional`) em OAB e telas de sistema:
  * usa `same_line_right_of` quando disponível,
  * usa `same_block`/`same_table_row` quando apropriado,
  * `enum` robusto; `id_simple` sempre com dígito.

* Embeddings melhoram recall (sem piorar precisão); cache reduz latência nas execuções seguintes.

* LLM fallback opcional, orquestrado (máx 2, timeout, guardado por validadores).

* PatternMemory registra e aplica bônus leves; reduz dependência de embedding/LLM em execuções subsequentes.

* Sem crashes quando configs ausentes; defaults embutidos funcionam.

* Scripts de smoke passam; CLI imprime traces claros.

> Implemente tudo acima. Em caso de ambiguidade, prefira **determinismo, guard-rails e baixo custo**. Não acople nada a um PDF específico. Mantenha o código limpo, modular, com docstrings e tipos.

