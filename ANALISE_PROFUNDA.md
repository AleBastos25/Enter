# Análise Profunda da Lógica de Extração de Documentos

## Resumo dos Testes

**Resultados:**
- Total: 23/37 campos encontrados (62%)
- Confiança média: 0.83
- Campos problemáticos identificados:
  - `inscricao` em `oab_1.pdf` e `oab_2.pdf`: extrai "2300" (número do endereço) em vez do número correto
  - `cidade` em `tela_sistema_2.pdf`: extrai CEP "76709970" em vez do nome da cidade
  - Vários campos não encontrados (null)

---

## Arquitetura do Sistema

### Fluxo Principal

```
1. PDF Loading → Blocks
2. Layout Analysis → LayoutGraph (neighborhood, columns, sections)
3. Table Detection → Tables
4. Embedding Index → Semantic Seeds (block_id, cosine_score)
5. Matching → FieldCandidates (node_id, relation, scores)
6. Extraction → (value, confidence, trace)
7. LLM Fallback → (se necessário)
8. Pattern Memory Learning → (se confiança ≥ 0.85)
```

---

## Análise Detalhada por Componente

### 1. MATCHING (src/matching/matcher.py)

#### **Estratégias de Matching (ordem de prioridade)**

1. **Table Lookup** (prioridade 0)
   - Busca label em tabelas
   - Extrai valor da mesma linha
   - Score base: 0.85

2. **Spatial Neighborhood** (prioridade 1-4)
   - `same_line_right_of`: score base 1.0
   - `same_block`: score base 0.85
   - `first_below_same_column`: score base 0.7
   - Bônus: mesma coluna (+0.08), mesma seção (+0.05), mesmo parágrafo (+0.03)
   - Penalidade: cross-column (-0.06), cross-section (-0.04)

3. **Semantic Seeds** (embeddings)
   - Threshold: 0.45 (geral), 0.60 (tipos numéricos)
   - Top-K: 4 blocos por campo
   - Usado como "label blocks" adicionais se não encontrados por substring

4. **Position-based** (fallback)
   - Usado quando não há label blocks e há `position_hint`
   - Score base: 0.80

5. **Global Enum Scan** (para campos enum)
   - Varre todos os blocos procurando opções válidas
   - Score base: 0.75

#### **Scoring Final**

```python
score = 0.60 * type_score + 0.30 * spatial_score + 0.10 * semantic_boost
```

- `type_score`: 0.0 ou 1.0 (validação passou/falhou)
- `spatial_score`: 0.0-1.0 (inclui memory bonus)
- `semantic_boost`: min(1.0, semantic_score / 0.85)

**Ordenação:**
1. Prioridade da relação (table > same_line > same_block > below > enum_scan)
2. Memory bonus (preferir candidatos com memória)
3. Score combinado (decrescente)

#### **Pontos Fortes**
✅ Múltiplas estratégias redundantes (tabela, espacial, semântica)
✅ Bônus de memória para aprendizado incremental
✅ Filtros type-aware (exigem dígitos para tipos numéricos)
✅ Preferência por mesma coluna/seção (contexto estrutural)

#### **Pontos Fracos**
❌ **Label matching muito restritivo**: `_find_label_blocks` usa substring matching, pode falhar se label está escrito diferente
❌ **Semantic seeds não são usados como candidatos diretos**: apenas adicionados como "label blocks", ainda dependem de neighborhood
❌ **Score de tipo binário (0/1)**: não diferencia entre "provavelmente correto" e "definitivamente correto"
❌ **Semantic boost tem peso baixo (10%)**: embeddings têm pouco impacto no score final
❌ **Falta verificação de ambiguidade**: se múltiplos campos têm mesmo candidato com alta confiança, não há resolução

---

### 2. EXTRACTION (src/extraction/text_extractor.py)

#### **Geração de Candidatos de Texto**

1. **Same Block**:
   - Usa `local_context` se fornecido (de embeddings/LLM)
   - Tenta `_split_by_label` para extrair parte após label
   - Verifica neighbor direito na mesma linha

2. **First Below Same Column**:
   - Lógica especial para multi-line: tenta corresponder linha do label com linha do valor
   - Exemplo: "Inscrição\nSeccional" → "101943\nPR" (linha 0 → linha 0, linha 1 → linha 1)

3. **Candidatos Genéricos**:
   - Linhas individuais (primeiras 3)
   - Janelas de 2-3 linhas
   - Tokens individuais e janelas de 2-3 tokens

#### **Validação e Scoring**

1. Remove labels conhecidos (se texto é só label, rejeita)
2. Valida tipo (`validate_and_normalize`)
3. Score baseado em relação:
   - `same_line_right_of`: 0.90
   - `same_block`, `same_table_row`: 0.85
   - `first_below_same_column`: 0.80
   - `global_enum_scan`: 0.75
4. Type boost (UF, id_simple): ajustes pequenos (+0.15, -0.10)

#### **Pontos Fortes**
✅ Lógica multi-line inteligente para correspondência linha-a-linha
✅ Múltiplos candidatos de texto (linhas, janelas, tokens)
✅ Filtragem de labels conhecidos

#### **Pontos Fracos**
❌ **`_first_line` usado em muitos lugares**: perde informação de blocos multi-line
❌ **Extração de "same_block" pode pegar label**: mesmo com `_split_by_label`, se falhar, pode extrair o label
❌ **Sem uso de contexto semântico na extração**: `local_context` só usado para `same_block`, não para outros tipos
❌ **Score de confiança fixo por relação**: não considera qualidade do texto extraído
❌ **Falta validação de plausibilidade**: não verifica se valor faz sentido para o campo (ex: "2300" não parece inscrição)

---

### 3. EMBEDDINGS (src/core/pipeline.py)

#### **Processo**

1. **Indexação de Blocos**:
   - Preprocessa texto (lowercase, strip accents, collapse spaces, truncate 300 chars)
   - Cache por `(doc_id, block_id, model_name)`
   - Batch processing (64 blocos por vez)

2. **Query por Campo**:
   - Query = `field.name + field.description[:100] + synonyms[:3]`
   - Mesmo preprocessamento
   - Cache por `(field_name, query_text, model_name)`

3. **Busca**:
   - Top-K: 4 blocos por campo
   - Threshold: 0.45 (geral), 0.60 (tipos numéricos)
   - Retorna `(block_id, cosine_score)`

#### **Uso dos Semantic Seeds**

```python
# Adicionados como "label blocks" se não encontrados por substring
for seed_block_id, cosine_score in field_seeds:
    if seed_block_id not in label_block_ids:
        label_block_ids.append(seed_block_id)
```

**Problema**: Seeds são tratados como "labels", mas podem ser os próprios valores! O sistema ainda tenta encontrar neighbors desses blocos, quando deveria considerar usar o bloco diretamente.

#### **Pontos Fortes**
✅ Cache eficiente (evita re-embedding)
✅ Batch processing para performance
✅ Thresholds adaptativos por tipo de campo

#### **Pontos Fracos**
❌ **Semantic seeds não geram candidatos diretos**: apenas adicionados como label blocks
❌ **Query não inclui contexto de valor**: apenas campo name/description, não exemplos de valores esperados
❌ **Threshold pode ser muito alto**: 0.45-0.60 pode perder matches válidos
❌ **Sem uso de embeddings para disambiguar**: se múltiplos candidatos, não usa similaridade semântica entre campo e valor extraído

---

### 4. LLM FALLBACK (src/core/pipeline.py)

#### **Trigger Conditions**

1. `value is None`: sempre tenta se budget permitir
2. `confidence < 0.75`: valor encontrado mas confiança baixa
3. `score em zona cinza (0.50-0.80)`: mesmo com valor, pode melhorar

#### **Context Building**

```python
context_text = candidate_text + neighbors
# candidate_text: primeira linha do bloco (até 300 chars)
# neighbors: linhas acima/abaixo, left/right, table row
```

#### **Pontos Fortes**
✅ Múltiplas condições de trigger
✅ Contexto rico (candidate + neighbors)
✅ Budget controlado (max 2 chamadas por PDF)

#### **Pontos Fracos**
❌ **Context pode ser insuficiente**: apenas primeira linha do bloco, pode perder informação importante
❌ **Não usa multiple candidates**: apenas top candidate, poderia tentar múltiplos
❌ **Confiança fixa para LLM (0.70-0.75)**: não considera qualidade da resposta
❌ **Não verifica se LLM melhorou**: se LLM retornar valor diferente, não compara com heuristic

---

### 5. PATTERN MEMORY (src/memory/pattern_memory.py)

#### **Aprendizado**

- Aprende apenas de extrações com confiança ≥ 0.85
- Aprende sinônimos, offsets, fingerprints, value shapes
- Decay: 0.98 por semana lógica
- Pruning: remove entradas com peso < 0.15

#### **Uso**

- Bônus de sinônimos: +0.06
- Bônus de offset: +0.07
- Bônus de fingerprint: +0.05
- Injeção de sinônimos: até 6 sinônimos aprendidos por campo

#### **Pontos Fortes**
✅ Aprendizado incremental
✅ Múltiplos tipos de padrões (sinônimos, offsets, fingerprints)
✅ Decay e pruning para evitar obsolescência

#### **Pontos Fracos**
❌ **Aprende apenas de alta confiança**: pode não aprender de correções do LLM
❌ **Não aprende de erros**: se valor está errado, não há feedback negativo
❌ **Memory bonus pequeno**: máximo ~0.18, pode não ser suficiente para superar candidatos espaciais fortes

---

## Problemas Identificados nos Testes

### 1. `inscricao` extrai "2300" (endereço) em vez do número correto

**Análise:**
- Bloco de endereço: "AVENIDA PAULISTA, Nº 2300 andar Pilotis..."
- Sistema encontra label "Inscrição" corretamente
- Usa `same_block` ou `first_below_same_column`
- Extrai "2300" do endereço porque está no mesmo bloco ou próximo

**Causa Raiz:**
- `_split_by_label` pode falhar se label não está no mesmo bloco
- Não há verificação de plausibilidade: "2300" não parece número de inscrição (típico: 6 dígitos, alfanumérico)
- Semantic seeds não são usados como candidatos diretos: se embedding encontrar bloco com "101943", não é usado diretamente

**Solução Proposta:**
1. Usar semantic seeds como candidatos diretos (não apenas como label blocks)
2. Validação de plausibilidade baseada em tipo: inscrição deve ter formato específico
3. LLM deveria ser acionado quando confiança < 0.85 (não só < 0.75)

### 2. `cidade` extrai CEP em vez do nome

**Análise:**
- Bloco: "Cidade: Mozarlândia U.F .: GO CEP: 76709970"
- Sistema extrai "76709970" (CEP) em vez de "Mozarlândia"

**Causa Raiz:**
- `_split_by_label` pode pegar parte errada do texto
- Não há parsing estruturado de blocos com múltiplos campos
- Embeddings podem estar encontrando o bloco certo, mas extração pega parte errada

**Solução Proposta:**
1. Parsing estruturado de padrões comuns ("Cidade: X U.F: Y CEP: Z")
2. LLM deveria ser acionado para campos text quando há ambiguidade
3. Usar embeddings para verificar: embedding do valor extraído deve ser similar ao embedding esperado do campo

### 3. Campos não encontrados (null)

**Análise:**
- Vários campos retornam null mesmo com informações no PDF

**Causa Raiz:**
- Label matching falha (substring não encontra)
- Semantic seeds vazios (threshold muito alto ou query não match)
- LLM não acionado (budget esgotado ou condições não atendidas)

**Solução Proposta:**
1. Reduzir threshold de embeddings (0.35 em vez de 0.45)
2. Melhorar query de embeddings (incluir exemplos de valores)
3. Aumentar budget de LLM ou melhorar trigger conditions

---

## Recomendações de Melhorias

### 1. **Usar Semantic Seeds como Candidatos Diretos**

**Problema**: Atualmente, semantic seeds são apenas adicionados como "label blocks", mas podem ser os próprios valores.

**Solução**:
```python
# Em match_fields, após gerar semantic_seeds:
for field in schema_fields:
    field_seeds = semantic_seeds.get(field.name, [])
    for seed_block_id, cosine_score in field_seeds:
        if cosine_score > 0.70:  # Alta confiança semântica
            # Adicionar como candidato direto (sem precisar de label)
            candidates.append(FieldCandidate(
                field=field,
                node_id=seed_block_id,
                source_label_block_id=seed_block_id,
                relation="semantic_direct",
                scores={"semantic": cosine_score, "type": 1.0},
            ))
```

### 2. **Validação de Plausibilidade por Tipo**

**Problema**: Sistema não verifica se valor faz sentido para o campo.

**Solução**:
```python
def _validate_plausibility(field: SchemaField, value: str) -> float:
    """Retorna score de plausibilidade (0.0-1.0)."""
    if field.type == "id_simple":
        # Inscrição OAB: típico 6 dígitos ou alfanumérico curto
        if len(value) < 3 or len(value) > 10:
            return 0.3  # Pouco plausível
        if re.match(r"^\d{4,}$", value):  # 4+ dígitos
            return 0.8  # Plausível
    elif field.type == "text" and field.name == "cidade":
        # Cidade: não deve ser só números
        if re.match(r"^\d+$", value):
            return 0.2  # CEP, não cidade
        if len(value) < 3:
            return 0.3
    return 1.0  # Padrão: plausível
```

### 3. **Melhorar Query de Embeddings**

**Problema**: Query apenas usa name/description, não exemplos de valores.

**Solução**:
```python
# Adicionar exemplos de valores esperados à query
if pattern_memory:
    value_examples = pattern_memory.get_value_examples(field.name, max_k=3)
    if value_examples:
        query_parts.extend([f"exemplo: {ex}" for ex in value_examples])
```

### 4. **Usar Embeddings para Disambiguar**

**Problema**: Se múltiplos candidatos, não usa similaridade semântica para escolher.

**Solução**:
```python
# Em extract_from_candidate, após gerar candidatos:
for txt in cand_texts:
    # ... validação existente ...
    
    # Calcular similaridade semântica entre valor extraído e campo esperado
    if embed_client and field.description:
        value_emb = embed_client.embed([txt_clean])[0]
        field_emb = embed_client.embed([field.description])[0]
        semantic_sim = cosine_similarity(value_emb, field_emb)
        # Boost score baseado em similaridade
        score += 0.15 * semantic_sim
```

### 5. **Parsing Estruturado de Blocos Multi-Campo**

**Problema**: Blocos como "Cidade: X U.F: Y CEP: Z" não são parseados corretamente.

**Solução**:
```python
def _parse_structured_block(block_text: str, field: SchemaField) -> Optional[str]:
    """Tenta extrair valor de padrões estruturados comuns."""
    patterns = [
        (r"cidade\s*:?\s*([^UuFfCcEePp]+?)(?:\s*(?:U\.?F\.?|UF|CEP))", "cidade"),
        (r"inscri[çc][ãa]o\s*:?\s*([A-Z0-9]{3,10})", "inscricao"),
        # ... mais padrões
    ]
    for pattern, field_type in patterns:
        if field_type in field.name.lower():
            match = re.search(pattern, block_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
    return None
```

### 6. **Aumentar Peso de Embeddings no Score**

**Problema**: Semantic boost tem apenas 10% de peso.

**Solução**:
```python
# Aumentar peso de embeddings para 20-30%
score = 0.50 * type_score + 0.30 * spatial_score + 0.20 * semantic_boost
```

### 7. **Melhorar Trigger de LLM**

**Problema**: LLM não aciona para valores incorretos com alta confiança.

**Solução**:
```python
# Adicionar verificação de plausibilidade
plausibility = _validate_plausibility(field, value)
if plausibility < 0.5 and llm_policy.budget_left():
    should_use_llm = True
```

### 8. **Context Richer para LLM**

**Problema**: Context apenas primeira linha do bloco.

**Solução**:
```python
# Incluir múltiplas linhas e contexto estrutural
context_parts = [
    f"Block text: {dst_block.text[:500]}",
    f"Neighbors: {neighbors}",
    f"Field description: {field.description}",
]
```

---

## Conclusão

O sistema tem uma arquitetura sólida com múltiplas estratégias redundantes, mas há espaço para melhorias:

1. **Embeddings subutilizados**: deveriam gerar candidatos diretos, não apenas label blocks
2. **Falta validação de plausibilidade**: valores podem ser tecnicamente válidos mas semanticamente incorretos
3. **LLM pouco utilizado**: condições de trigger podem ser melhoradas
4. **Extração pode melhorar**: parsing estruturado e uso de contexto semântico

As mudanças propostas devem melhorar a precisão de ~62% para ~75-80% sem aumentar significativamente a complexidade.

