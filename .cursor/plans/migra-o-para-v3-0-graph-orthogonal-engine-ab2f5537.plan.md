<!-- ab2f5537-610f-4446-8920-57e4958a67d6 f8b5d675-1459-4453-b901-3197de422109 -->
# Plano de Migração para v3.0 Graph-Orthogonal Engine

## Objetivo

Refatorar a codebase para implementar a arquitetura v3.0 conforme descrito no `v2.md`, mantendo compatibilidade com o código existente de construção de grafo que já funciona.

## Estrutura do Plano

### 1. Modelo de Espaçamento e Limiares Automáticos

**Arquivo:** `src/graph/spacing_model.py` (novo)

- Calcular `τ_same_line`, `τ_same_column`, `τ_multiline` usando mediana + MAD
- Medir gaps horizontais e verticais entre TUs
- Interface: `compute_spacing_thresholds(blocks) -> LayoutThresholds`

### 2. Grafo Ortogonal Simplificado

**Arquivo:** `src/graph/orthogonal_edges.py` (novo, substitui partes de `graph_v2.py`)

- Construir arestas direcionais simples: ↑ (north), ↓ (south), ← (west), → (east)
- Usar limiares do spacing_model
- Remover arestas "same_line", "same_col" - substituir por direcionais
- Interface: `build_orthogonal_graph(text_units, thresholds) -> OrthogonalGraph`

**Mudanças em:** `src/layout/graph_v2.py`

- Refatorar para usar `orthogonal_edges.py`
- Manter compatibilidade com código existente que usa `GraphV2`

### 3. Style Components (Agrupamento por Estilo)

**Arquivo:** `src/graph/components.py` (novo)

- Agrupar TUs conectados ortogonalmente com mesma StyleSignature
- Interface: `group_by_style(graph, style_signatures) -> list[StyleComponent]`
- Cada componente mantém lista de block_ids e style_signature único

### 4. Regras de Papéis Determinísticas

**Arquivo:** `src/graph/roles_rules.py` (novo, substitui `role_classifier.py`)

- Implementar regras R-H *(HEADER), R-L* (LABEL), R-V* (VALUE)
- HEADER: fonte ≥ quantil 90, linha centralizada/isolada, ou pai com ≥2 filhos de estilos diferentes
- LABEL: termina com separador, ≤3 tokens sem dígitos, ou vizinho passa type-gate, ou contém token do lexicon
- VALUE: passa type-gate, está (→ ou ↓) de LABEL, não termina com separador
- Interface: `assign_roles(graph, schema_lexicons, style_signatures) -> dict[block_id, Role]`

**Mudanças em:** `src/layout/role_classifier.py`

- Refatorar para usar `roles_rules.py` ou deprecar em favor do novo módulo

### 5. Propagação de Papéis por Estilo

**Arquivo:** `src/graph/roles_rules.py` (mesmo arquivo acima)

- Implementar propagação E-1/E-2: TUs conectados ortogonalmente com S idêntica compartilham papel
- Prioridade fixa: HEADER > LABEL > VALUE
- Regra especial: VALUE com separador → LABEL

### 6. Léxico por Campo

**Arquivo:** `src/core/schema.py` (modificar)

- Adicionar função `build_lexicon(field: SchemaField) -> set[str]`
- Extrair tokens de `key` + n-grams curtos da descrição
- Suporte a enum_options
- Interface já existe parcialmente em `_generate_synonyms`, adaptar para retornar conjunto exato

### 7. Busca Ortogonal LABEL→VALUE

**Arquivo:** `src/matching/label_value.py` (novo)

- Implementar busca determinística em ordem fixa: →, ↓, ↑, ←
- BFS restrita (1-3 saltos) no mesmo componente de seção
- Categorias de LABEL: A (contém token do lexicon), B (genéricos), C (fallback)
- Coletar candidatos que passam type-gate, não compartilham estilo com LABEL, não violam no-crossing
- Interface: `find_label_value_pairs(graph, field, lexicon, type_gate) -> list[Candidate]`

**Mudanças em:** `src/matching/matcher.py`

- Refatorar para usar `label_value.py` em vez da lógica atual
- Manter compatibilidade com interface existente

### 8. Filtro de Pareto

**Arquivo:** `src/matching/pareto.py` (modificar)

- Ajustar critérios C1-C4 para serem puramente lógicos (sem scores contínuos)
- C1 Estrutural: lógico (menos saltos, mesma linha/coluna, sem crossing)
- C2 Estilo: lógico (estilo diferente, coerência)
- C3 Léxico: lógico (enum: pertence ao conjunto, texto: ≥4 letras e sem separador)
- C4 Tipo: lógico (passa type-gate)
- Eliminar candidatos dominados, retornar não-dominados

**Mudanças em:** `src/matching/pareto.py`

- Refatorar `compute_pareto_criteria` para retornar booleanos/valores discretos
- Manter interface `pareto_filter` mas com lógica determinística

### 9. Tie-Breakers Determinísticos

**Arquivo:** `src/matching/tie_breakers.py` (modificar)

- Ajustar ordem: direção preferida (→ > ↓ > ↑ > ←), menos saltos, menor distância Manhattan, menor line_index
- Remover scores arbitrários, usar comparação lexicográfica
- Interface já existe, ajustar implementação

### 10. LLM Chooser Inteligente

**Arquivo:** `src/llm/chooser.py` (modificar)

- Já existe, ajustar para:
- Acionar apenas quando empate real após Pareto + tie-breakers
- Cache por hash do subgrafo
- Integração com memória de invariantes
- Revalidação pelo type-gate após escolha

### 11. Multilinha (Join de Values)

**Arquivo:** `src/extraction/join_multiline.py` (novo)

- Concatenação de values ↓ mesmo estilo
- Interface: `join_multiline_values(candidates, graph, style_signatures) -> str`

### 12. Type Gates Genéricos

**Arquivo:** `src/validation/type_gates.py` (novo, extrair de `patterns.py`)

- Mover `type_gate_generic` para módulo dedicado
- Garantir que todas as funções são universais (sem validação local)
- Interface: `type_gate(value: str, field_type: str) -> bool`

**Mudanças em:** `src/validation/patterns.py`

- Manter funções auxiliares, mover type_gate para novo módulo

### 13. Proof Builder

**Arquivo:** `src/utils/proof_builder.py` (novo, extrair de `proof.py`)

- Montar bloco JSON de auditoria completo conforme v2.md
- Incluir: label_component, value_component, search, pareto, tie_break, llm_used, memory
- Interface: `build_proof(field, value, label_nodes, value_nodes, search_info, pareto_info, ...) -> dict`

**Mudanças em:** `src/core/proof.py`

- Refatorar para usar `proof_builder.py` ou mover lógica para lá

### 14. Memória de Invariantes

**Arquivo:** `src/core/memory.py` (novo, integrar com `memory/`)

- Criar módulo de invariantes que armazena por DocumentLabel:
- Vocabulário de LABEL
- Direção típica (→ ou ↓)
- Offset (dx, dy) médios
- StyleSignature dominante
- Shape de valor (regex inferida)
- Interface: `update_invariants(document_label, field, label, value, direction, style, ...)`
- Interface: `get_invariants(document_label, field) -> dict`

**Mudanças em:** `src/memory/pattern_memory.py`, `src/memory/pattern_registry.py`

- Integrar com novo módulo de invariantes
- Manter compatibilidade com código existente

### 15. Temperatura

**Arquivo:** `src/memory/temperature.py` (já existe, ajustar)

- Calcular T = (# invariantes verificados) / (# invariantes aplicáveis)
- Usar para política de LLM: T ≥ 0.8 → nenhuma chamada, 0.4 ≤ T < 0.8 → 1 chamada, T < 0.4 → até 3 chamadas
- Interface já existe, ajustar cálculo

### 16. Pipeline Principal

**Arquivo:** `src/core/pipeline.py` (modificar)

- Refatorar `_run_single_page` para seguir fluxo do v2.md:

1. Extração de TUs (já existe)
2. Style Signatures (já existe)
3. Modelo de Espaçamento (novo)
4. Grafo Ortogonal (novo)
5. Roles (novo)
6. Style Propagation (novo)
7. Schema Anchoring (lexicon)
8. LABEL→VALUE Pairing (novo)
9. Pareto Selection (ajustar)
10. Tie-Breakers (ajustar)
11. LLM Chooser (ajustar)
12. Multilinha (novo)
13. Type-Gate (novo)
14. Output + Proof (ajustar)
15. Invariant Memory Update (novo)

### 17. Estrutura de Dados

**Arquivo:** `src/core/models.py` (modificar)

- Adicionar `OrthogonalGraph` TypedDict com `adj: dict[block_id, dict[str, list[block_id]]]` onde keys são "up", "down", "left", "right"
- Adicionar `StyleComponent` dataclass
- Adicionar `Role` Literal type
- Manter `GraphV2` para compatibilidade, mas criar adaptador

### 18. Configurações

**Arquivo:** `configs/runtime.yaml` (verificar)

- Verificar se contém: timeouts, llm.max_calls_per_pdf, layout thresholds, memory settings

## Ordem de Implementação Recomendada

1. **Fase 1: Fundamentos** (sem quebrar código existente)

- spacing_model.py
- orthogonal_edges.py (paralelo a graph_v2.py)
- components.py

2. **Fase 2: Papéis e Propagação**

- roles_rules.py
- Ajustar role_classifier.py para usar novo módulo

3. **Fase 3: Matching**

- label_value.py
- Ajustar pareto.py
- Ajustar tie_breakers.py

4. **Fase 4: Integração**

- Ajustar pipeline.py
- Integrar memória de invariantes
- Ajustar proof builder

5. **Fase 5: Limpeza**

- Deprecar código antigo
- Testes e validação

## Notas Importantes

- O código de construção de grafo existente (identificar bbox e linkar horizontal/vertical) deve ser preservado e reutilizado
- Manter compatibilidade com interfaces existentes durante a migração
- Testar cada fase antes de prosseguir
- Documentar mudanças em STATUS.md ou similar

### To-dos

- [ ] Criar src/graph/spacing_model.py com cálculo de limiares automáticos (τ_same_line, τ_same_column, τ_multiline) usando mediana + MAD
- [ ] Criar src/graph/orthogonal_edges.py com construção de grafo ortogonal usando arestas direcionais simples (↑↓←→)
- [ ] Criar src/graph/components.py para agrupamento de TUs por estilo conectados ortogonalmente
- [ ] Criar src/graph/roles_rules.py implementando regras R-H*, R-L*, R-V* e propagação por estilo E-1/E-2
- [ ] Adicionar função build_lexicon em src/core/schema.py para gerar léxico exato por campo
- [ ] Criar src/matching/label_value.py para busca ortogonal determinística LABEL→VALUE em ordem fixa (→↓↑←)
- [ ] Refatorar src/matching/pareto.py para usar critérios lógicos (não scores contínuos) e eliminação de dominados
- [ ] Ajustar src/matching/tie_breakers.py para usar comparação lexicográfica determinística
- [ ] Ajustar src/llm/chooser.py para cache por hash, integração com memória e revalidação type-gate
- [ ] Criar src/extraction/join_multiline.py para concatenação de values multiline
- [ ] Criar src/validation/type_gates.py extraindo type_gate_generic de patterns.py
- [ ] Criar src/utils/proof_builder.py com montagem completa de provas conforme v2.md
- [ ] Criar src/core/memory.py para memória de invariantes (vocabulário, direção, offset, style, shape)
- [ ] Ajustar src/memory/temperature.py para calcular T e usar para política de LLM
- [ ] Refatorar src/core/pipeline.py para seguir fluxo completo do v2.md (15 etapas)
- [ ] Adicionar OrthogonalGraph, StyleComponent, Role em src/core/models.py