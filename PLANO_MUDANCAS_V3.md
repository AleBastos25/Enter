# Plano de Mudanças para Implementação da Arquitetura v3.0

> **Objetivo:** Alinhar a codebase com a arquitetura v3.0 descrita em `v2.md`, mantendo o código de visualização HTML existente e adicionando campos de estilo/layout aos nós do grafo.

---

## 📋 Resumo Executivo

A v3.0 requer:
1. **TextUnits (TUs)** como unidade básica (mais granular que Blocks)
2. **Style Signatures** completas nos nós do grafo
3. **Grafo Ortogonal** com direções ↑↓←→ (já implementado em `build_token_graph.py`)
4. **Classificação de Papéis** (HEADER/LABEL/VALUE) por regras determinísticas
5. **Propagação de Estilo** entre TUs conectados
6. **Emparelhamento LABEL→VALUE** com Pareto + tie-breakers
7. **LLM Chooser** apenas quando necessário
8. **Memória de Invariantes** por tipo de documento

**Status Atual:**
- ✅ Grafo ortogonal já implementado (`build_token_graph.py`)
- ✅ Visualização HTML funcionando (`visualize_token_graph.py`)
- ✅ Style signatures parcialmente implementadas (`src/layout/style_signature.py`)
- ✅ Role classification parcial (`src/layout/role_classifier.py`)
- ✅ Pareto filtering implementado (`src/matching/pareto.py`)
- ✅ LLM chooser implementado (`src/llm/chooser.py`)
- ⚠️ Falta: TextUnit como modelo de dados principal
- ⚠️ Falta: Integração completa no pipeline
- ⚠️ Falta: Campos de estilo/layout nos nós do grafo gerado

---

## 🎯 Mudanças Necessárias

### Fase 1: Modelo de Dados TextUnit

#### 1.1 Criar `src/graph/text_unit.py`
**Objetivo:** Definir TextUnit como unidade básica com estilo completo.

```python
@dataclass(frozen=True)
class TextUnit:
    """Unidade mínima de texto homogênea em estilo e espaçamento."""
    id: int
    text: str
    bbox: Tuple[float, float, float, float]  # [0,1] normalizado
    style_signature: StyleSignature
    font_family: Optional[str] = None
    font_size: float
    bold: bool = False
    italic: bool = False
    color: Optional[str] = None
    alignment: Literal["left", "center", "right"] = "left"
    line_index: int = 0  # Índice da linha (para ordenação)
    block_id: Optional[int] = None  # Referência ao Block original (se aplicável)
```

**Ações:**
- [ ] Criar arquivo `src/graph/text_unit.py`
- [ ] Definir dataclass `TextUnit`
- [ ] Adicionar função `blocks_to_text_units(blocks: List[Block]) -> List[TextUnit]`
- [ ] Integrar com `StyleSignature` existente

#### 1.2 Atualizar `src/core/models.py`
**Objetivo:** Adicionar TextUnit aos modelos principais.

**Ações:**
- [ ] Adicionar `TextUnit` ao `__all__`
- [ ] Importar `TextUnit` de `src.graph.text_unit`

---

### Fase 2: Grafo Ortogonal com Metadados

#### 2.1 Atualizar `scripts/build_token_graph.py`
**Objetivo:** Adicionar campos de estilo e layout aos nós do grafo.

**Mudanças necessárias:**
- [ ] Adicionar campo `style_signature` a cada nó (usar `StyleSignature` de `src/layout/style_signature.py`)
- [ ] Adicionar campo `role` (HEADER/LABEL/VALUE/OTHER) a cada nó
- [ ] Adicionar campo `font_size`, `bold`, `italic`, `color` a cada nó
- [ ] Adicionar campo `line_index` para ordenação
- [ ] Adicionar campo `component_id` (componente de estilo)
- [ ] Manter compatibilidade com `visualize_token_graph.py` (não quebrar o HTML)

**Estrutura do nó atual:**
```python
{
    "id": int,
    "text": str,
    "bbox": [x0, y0, x1, y1],
    "block_id": int,
    "font_size": float,
    "bold": bool
}
```

**Estrutura do nó após mudanças:**
```python
{
    "id": int,
    "text": str,
    "bbox": [x0, y0, x1, y1],
    "block_id": int,
    "font_size": float,
    "bold": bool,
    "italic": bool,
    "color": Optional[str],
    "style_signature": {
        "font_family_id": int,
        "font_size_bin": int,
        "is_bold": bool,
        "is_italic": bool,
        "color_cluster": int,
        "caps_ratio_bin": int,
        "letter_spacing_bin": int
    },
    "role": "HEADER" | "LABEL" | "VALUE" | "OTHER" | None,
    "line_index": int,
    "component_id": int
}
```

**Ações:**
- [ ] Modificar `extract_tokens_with_coords()` para extrair mais metadados de estilo
- [ ] Adicionar cálculo de `StyleSignature` em `build_token_graph()`
- [ ] Adicionar campos de estilo aos nós retornados
- [ ] Testar que `visualize_token_graph.py` ainda funciona (campos extras são ignorados pelo JS)

#### 2.2 Criar `src/graph/orthogonal_edges.py`
**Objetivo:** Módulo dedicado para construção do grafo ortogonal (refatorar de `build_token_graph.py`).

**Interface:**
```python
def build_orthogonal_graph(
    text_units: List[TextUnit],
    thresholds: Optional[SpacingThresholds] = None
) -> OrthogonalGraph:
    """Constrói grafo ortogonal G(V,E) com arestas ↑↓←→.
    
    Args:
        text_units: Lista de TextUnits.
        thresholds: Limiares de espaçamento (ou calculados automaticamente).
    
    Returns:
        OrthogonalGraph com nós e arestas direcionais.
    """
```

**Ações:**
- [ ] Criar arquivo `src/graph/orthogonal_edges.py`
- [ ] Mover lógica de construção de grafo de `build_token_graph.py`
- [ ] Adicionar cálculo automático de limiares (τ_same_line, τ_same_column, τ_multiline)
- [ ] Usar estatística resistente (mediana + MAD)
- [ ] Retornar estrutura `OrthogonalGraph` com metadados completos

#### 2.3 Criar `src/graph/components.py`
**Objetivo:** Agrupamento de TUs em componentes de estilo.

**Interface:**
```python
def group_by_style(
    graph: OrthogonalGraph
) -> List[StyleComponent]:
    """Agrupa TUs conectados ortogonalmente com mesmo StyleSignature.
    
    Returns:
        Lista de StyleComponent (cada um com lista de TU ids e papel único).
    """
```

**Ações:**
- [ ] Criar arquivo `src/graph/components.py`
- [ ] Implementar agrupamento por estilo
- [ ] Conectar TUs ortogonalmente adjacentes com S idêntico
- [ ] Atribuir papel único por prioridade (HEADER > LABEL > VALUE)

---

### Fase 3: Classificação de Papéis e Propagação

#### 3.1 Atualizar `src/layout/roles_rules.py` (criar se não existir)
**Objetivo:** Implementar todas as regras R-H*, R-L*, R-V* do v2.md.

**Regras a implementar:**
- **R-H1:** Fonte ≥ quantil 90 da seção
- **R-H2:** Linha centralizada ou isolada
- **R-H3:** TU pai com ≥2 filhos ↓ de estilos diferentes
- **R-L1:** Termina com separador (`:`, `-`, `.`, `/`)
- **R-L2:** ≤3 tokens, sem dígitos
- **R-L3:** Vizinho (→ ou ↓) passa type-gate
- **R-L4:** Contém token do `Lexicon(field)`
- **R-V1:** Passa `TypeGate(field)`
- **R-V2:** Está (→ ou ↓) de um LABEL
- **R-V3:** Não termina com separador

**Ações:**
- [ ] Criar/atualizar `src/graph/roles_rules.py`
- [ ] Implementar função `assign_roles(graph, schema_lexicons) -> graph_with_roles`
- [ ] Aplicar regras R-H*, R-L*, R-V*
- [ ] Integrar com `src/layout/role_classifier.py` existente

#### 3.2 Atualizar `src/layout/role_classifier.py`
**Objetivo:** Integrar com TextUnits e grafo ortogonal.

**Ações:**
- [ ] Modificar `classify_role_initial()` para aceitar `TextUnit` em vez de `Block`
- [ ] Adicionar suporte a grafo ortogonal (direções ↑↓←→)
- [ ] Integrar com `propagate_role_by_style()` existente

---

### Fase 4: Emparelhamento LABEL→VALUE

#### 4.1 Criar `src/matching/label_value.py`
**Objetivo:** Busca ortogonal determinística de pares LABEL→VALUE.

**Interface:**
```python
def find_label_value_pairs(
    graph: OrthogonalGraph,
    field: SchemaField,
    lexicon: Set[str],
    type_gate: Callable[[str, str], bool]
) -> List[Tuple[int, int]]:
    """Encontra pares (label_tu_id, value_tu_id) para um campo.
    
    Estratégia:
    1. Encontrar LABELs candidatos (Categoria A/B/C)
    2. Percorrer grafo ortogonal em ordem fixa (→, ↓, ↑, ←)
    3. Coletar VALUES que passam type-gate
    4. Aplicar filtro de Pareto
    5. Aplicar tie-breakers
    6. Chamar LLM chooser se necessário
    
    Returns:
        Lista de tuplas (label_id, value_id).
    """
```

**Ações:**
- [ ] Criar arquivo `src/matching/label_value.py`
- [ ] Implementar busca ortogonal (BFS restrita, 1-3 saltos)
- [ ] Integrar com `src/matching/pareto.py` existente
- [ ] Integrar com `src/matching/tie_breakers.py` existente
- [ ] Integrar com `src/llm/chooser.py` existente

#### 4.2 Atualizar `src/matching/pareto.py`
**Objetivo:** Garantir que funciona com TextUnits e grafo ortogonal.

**Ações:**
- [ ] Verificar compatibilidade com `TextUnit`
- [ ] Adicionar suporte a direções ortogonais (→, ↓, ↑, ←)
- [ ] Testar com grafos gerados por `build_token_graph.py`

#### 4.3 Atualizar `src/matching/tie_breakers.py`
**Objetivo:** Implementar tie-breakers determinísticos conforme v2.md.

**Ordem de tie-breakers:**
1. Direção preferida (`→` > `↓` > `↑` > `←`)
2. Menos saltos
3. Menor distância Manhattan (Δx + Δy)
4. Menor `line_index`

**Ações:**
- [ ] Verificar se `tie_breakers.py` existe
- [ ] Implementar/atualizar tie-breakers conforme especificação
- [ ] Integrar com `label_value.py`

---

### Fase 5: Schema e Lexicons

#### 5.1 Atualizar `src/core/schema.py`
**Objetivo:** Adicionar geração de lexicons e type-gates conforme v2.md.

**Interface:**
```python
def build_lexicon(field: SchemaField) -> Set[str]:
    """Constrói léxico exato para um campo.
    
    Inclui:
    - Variações da chave (nº, no, num, com/sem :)
    - Tokens curtos da descrição (não stopwords)
    - Opções explícitas (enum)
    """
```

**Ações:**
- [ ] Adicionar função `build_lexicon(field) -> Set[str]`
- [ ] Adicionar função `build_type_gate(field) -> Callable`
- [ ] Integrar com `src/validation/type_gates.py` (criar se não existir)

#### 5.2 Criar `src/validation/type_gates.py`
**Objetivo:** Type-gates genéricos e determinísticos.

**Interface:**
```python
def type_gate_generic(text: str, field_type: str) -> bool:
    """Valida se texto é compatível com tipo do campo.
    
    Tipos suportados:
    - date_like: Datas em vários formatos
    - money_like: Valores monetários
    - text: Texto genérico
    - id_simple: IDs numéricos/alphanuméricos
    - enum: Valores de enum
    """
```

**Ações:**
- [ ] Criar arquivo `src/validation/type_gates.py`
- [ ] Implementar type-gates genéricos
- [ ] Integrar com `src/validation/validators.py` existente

---

### Fase 6: LLM Chooser e Memória

#### 6.1 Atualizar `src/llm/chooser.py`
**Objetivo:** Garantir compatibilidade com TextUnits e grafo ortogonal.

**Ações:**
- [ ] Verificar que funciona com estrutura de grafo ortogonal
- [ ] Adicionar suporte a direções (→, ↓, ↑, ←) no prompt
- [ ] Testar cache e política de temperatura

#### 6.2 Atualizar `src/memory/temperature.py`
**Objetivo:** Calcular temperatura do documento conforme v2.md.

**Fórmula:**
```
T = (# invariantes verificados) / (# invariantes aplicáveis)
```

**Uso:**
- T ≥ 0.8 → nenhuma chamada LLM (100% determinístico)
- 0.4 ≤ T < 0.8 → 1 chamada máxima
- T < 0.4 → até 3 chamadas

**Ações:**
- [ ] Verificar implementação atual
- [ ] Ajustar conforme especificação v2.md
- [ ] Integrar com pipeline

#### 6.3 Atualizar `src/memory/pattern_memory.py`
**Objetivo:** Armazenar invariantes por tipo de documento.

**Tipos de invariantes:**
- Vocabulário de LABEL
- Direção típica (→ ou ↓)
- Offset (dx, dy) médios
- StyleSignature dominante
- Shape de valor (regex inferida)

**Ações:**
- [ ] Verificar implementação atual
- [ ] Adicionar suporte a invariantes conforme v2.md
- [ ] Integrar com pipeline

---

### Fase 7: Pipeline Principal

#### 7.1 Atualizar `src/core/pipeline.py`
**Objetivo:** Integrar todas as mudanças no pipeline principal.

**Novo fluxo:**
```
PDF
 → TextUnits (TUs) [NOVO]
   → Style Signatures [EXISTE, ATUALIZAR]
     → Graph G(V,E) (ortogonal ↑ ↓ ← →) [EXISTE, ATUALIZAR]
       → Roles (HEADER/LABEL/VALUE) [EXISTE, ATUALIZAR]
         → Style Propagation [EXISTE, ATUALIZAR]
           → Schema Anchoring [NOVO]
             → LABEL→VALUE Pairing (Pareto + tie-breakers) [EXISTE, ATUALIZAR]
               → LLM Chooser (apenas se necessário) [EXISTE, ATUALIZAR]
                 → Output + Proof [NOVO]
                   → Invariant Memory Update [EXISTE, ATUALIZAR]
```

**Ações:**
- [ ] Adicionar etapa de conversão Blocks → TextUnits
- [ ] Integrar construção de grafo ortogonal
- [ ] Integrar classificação de papéis
- [ ] Integrar emparelhamento LABEL→VALUE
- [ ] Integrar LLM chooser com política de temperatura
- [ ] Adicionar geração de provas (proof)
- [ ] Integrar atualização de memória

#### 7.2 Criar `src/core/proof.py`
**Objetivo:** Gerar provas auditáveis conforme v2.md.

**Estrutura de prova:**
```python
{
    "field": "inscricao",
    "value": "101943",
    "source": "graph",
    "proof": {
        "label_component": {...},
        "value_component": {...},
        "search": {...},
        "pareto": {...},
        "tie_break": "...",
        "llm_used": false,
        "memory": {...}
    }
}
```

**Ações:**
- [ ] Criar arquivo `src/core/proof.py`
- [ ] Implementar `build_proof()` conforme especificação
- [ ] Integrar com pipeline

---

### Fase 8: Manutenção da Visualização

#### 8.1 Garantir compatibilidade com `visualize_token_graph.py`
**Objetivo:** Manter o HTML funcionando após mudanças.

**Ações:**
- [ ] Testar que `build_token_graph.py` ainda gera estrutura compatível
- [ ] Verificar que campos extras não quebram o JavaScript
- [ ] Adicionar campos opcionais de estilo na visualização (se desejado)
- [ ] Documentar estrutura do grafo gerado

#### 8.2 Atualizar `scripts/visualize_token_graph.py` (opcional)
**Objetivo:** Adicionar visualização de estilo/role se desejado.

**Ações:**
- [ ] Adicionar cores diferentes por role (HEADER/LABEL/VALUE)
- [ ] Adicionar tooltip com style_signature
- [ ] Adicionar filtro por role na interface

---

## 📁 Estrutura de Arquivos (Após Mudanças)

```
src/
 ├── app/
 │   └── cli.py
 ├── core/
 │   ├── pipeline.py           # [ATUALIZAR] Pipeline completo v3
 │   ├── schema.py             # [ATUALIZAR] Schema + lexicons + type-gates
 │   ├── policy.py             # [EXISTE]
 │   ├── proof.py              # [NOVO] Geração de provas
 │   └── models.py             # [ATUALIZAR] Adicionar TextUnit
 ├── graph/
 │   ├── text_unit.py          # [NOVO] TextUnit dataclass
 │   ├── orthogonal_edges.py   # [NOVO] G(V,E) ortogonal ↑ ↓ ← →
 │   ├── style_signature.py    # [EXISTE, MANTER]
 │   ├── roles_rules.py        # [NOVO] R-H*, R-L*, R-V* + propagação
 │   └── components.py         # [NOVO] Agrupamento por estilo
 ├── matching/
 │   ├── label_value.py        # [NOVO] Busca ortogonal e emparelhamento
 │   ├── pareto.py             # [EXISTE, ATUALIZAR]
 │   ├── tie_breakers.py       # [EXISTE, ATUALIZAR]
 │   └── assignment.py         # [EXISTE]
 ├── llm/
 │   └── chooser.py            # [EXISTE, ATUALIZAR]
 ├── io/
 │   └── pdf_loader.py         # [EXISTE]
 ├── validation/
 │   ├── type_gates.py         # [NOVO] Date/money/text/... genéricos
 │   └── validators.py         # [EXISTE]
 ├── extraction/
 │   └── join_multiline.py     # [NOVO] Concatenação de values ↓ mesmo estilo
 └── utils/
     ├── geometry.py           # [NOVO] Funções Δx, Δy, sobreposição
     └── proof_builder.py      # [NOVO] Montagem do bloco de auditoria

scripts/
 ├── build_token_graph.py      # [ATUALIZAR] Adicionar campos de estilo
 └── visualize_token_graph.py # [MANTER] Compatibilidade garantida
```

---

## ✅ Checklist de Implementação

### Prioridade Alta (Core)
- [ ] **Fase 1:** Criar `TextUnit` model
- [ ] **Fase 2.1:** Atualizar `build_token_graph.py` com campos de estilo
- [ ] **Fase 2.2:** Criar `orthogonal_edges.py`
- [ ] **Fase 3.1:** Criar `roles_rules.py` com todas as regras
- [ ] **Fase 4.1:** Criar `label_value.py` para emparelhamento
- [ ] **Fase 5.1:** Atualizar `schema.py` com lexicons
- [ ] **Fase 7.1:** Atualizar `pipeline.py` com novo fluxo

### Prioridade Média (Integração)
- [ ] **Fase 2.3:** Criar `components.py` para agrupamento
- [ ] **Fase 3.2:** Atualizar `role_classifier.py`
- [ ] **Fase 4.2:** Atualizar `pareto.py`
- [ ] **Fase 4.3:** Atualizar `tie_breakers.py`
- [ ] **Fase 5.2:** Criar `type_gates.py`
- [ ] **Fase 6.1:** Atualizar `chooser.py`
- [ ] **Fase 7.2:** Criar `proof.py`

### Prioridade Baixa (Melhorias)
- [ ] **Fase 6.2:** Ajustar `temperature.py`
- [ ] **Fase 6.3:** Atualizar `pattern_memory.py`
- [ ] **Fase 8.2:** Melhorar visualização HTML (opcional)

---

## 🔍 Testes e Validação

### Testes Unitários
- [ ] Testar criação de TextUnits a partir de Blocks
- [ ] Testar cálculo de StyleSignatures
- [ ] Testar construção de grafo ortogonal
- [ ] Testar classificação de papéis (R-H*, R-L*, R-V*)
- [ ] Testar propagação de estilo
- [ ] Testar emparelhamento LABEL→VALUE
- [ ] Testar filtro de Pareto
- [ ] Testar tie-breakers
- [ ] Testar LLM chooser
- [ ] Testar geração de provas

### Testes de Integração
- [ ] Testar pipeline completo com PDF real
- [ ] Testar que visualização HTML ainda funciona
- [ ] Testar que memória de invariantes funciona
- [ ] Testar política de temperatura

### Testes de Regressão
- [ ] Comparar resultados com versão anterior
- [ ] Verificar que não quebrou funcionalidades existentes

---

## 📝 Notas Importantes

1. **Compatibilidade:** Manter compatibilidade com `visualize_token_graph.py` é crítico. Campos extras no JSON são ignorados pelo JavaScript, então é seguro adicionar.

2. **Grafo Existente:** O código em `build_token_graph.py` já cria grafos ortogonais corretamente. Precisamos apenas adicionar metadados aos nós.

3. **Style Signatures:** Já existe implementação em `src/layout/style_signature.py`. Reutilizar e adaptar.

4. **Pareto e Tie-breakers:** Já existem implementações. Verificar e ajustar conforme necessário.

5. **LLM Chooser:** Já existe. Garantir integração com novo fluxo.

6. **Memória:** Já existe sistema de memória. Ajustar para invariantes conforme v2.md.

---

## 🚀 Ordem de Implementação Recomendada

1. **Semana 1:** Fases 1, 2.1, 2.2 (Modelo de dados e grafo)
2. **Semana 2:** Fases 3.1, 3.2, 4.1 (Papéis e emparelhamento)
3. **Semana 3:** Fases 4.2, 4.3, 5.1, 5.2 (Pareto, tie-breakers, schema)
4. **Semana 4:** Fases 6.1, 7.1, 7.2 (LLM, pipeline, provas)
5. **Semana 5:** Fases 6.2, 6.3, 8.1, 8.2 (Memória, visualização, testes)

---

## 📚 Referências

- `v2.md`: Especificação completa da arquitetura v3.0
- `STATUS.md`: Status atual do sistema
- `scripts/build_token_graph.py`: Implementação atual do grafo
- `scripts/visualize_token_graph.py`: Visualização HTML (manter)

---

**Última atualização:** 2025-11-XX
**Versão do plano:** 1.0

