# Correções Generalistas Aplicadas

## Problemas Abstratos Identificados e Soluções Implementadas

### 1. **Labels em Blocos Multi-linha Não Sendo Encontrados**

**Problema:** 
- Blocos com múltiplos labels em linhas diferentes (ex: "Inscrição\nSeccional\nSubseção") não eram encontrados porque o matching procurava o texto completo do bloco.

**Solução Generalista:**
- **Arquivo:** `src/matching/candidates.py` - `_find_label_blocks_lightweight`
- Verificação dupla:
  1. Verifica texto completo do bloco (comportamento original)
  2. Para blocos multi-linha, verifica cada linha individualmente
- Threshold adaptativo: 85% do threshold base para matching de linhas individuais
- Filtro adicional: linhas label-like (≤5 tokens)

**Aplicável a:** Qualquer campo com labels em blocos estruturados/multi-linha

---

### 2. **Extração de Valores de Blocos Multi-linha**

**Problema:**
- Quando labels e values estão em blocos diferentes mas ambos são multi-linha, o sistema não extraía a linha correspondente correta.
- Exemplo: Label "Inscrição" na linha 0 → Value "101943" na linha 0 do bloco de valores.

**Solução Generalista:**
- **Arquivo:** `src/extraction/text_extractor.py` - `extract_from_candidate`
- Matching de índices de linha: encontra qual linha do label block contém o label do campo
- Extrai linha correspondente do value block (mesmo índice)
- Processamento por tipo de campo:
  - Campos curtos (number, id_simple, uf): extrai parte que passa type-gate
  - Campos longos (text): mantém mais contexto
- Fallback: se não encontrar linha correspondente, usa primeira linha do value block

**Aplicável a:** Qualquer campo com estrutura label-value em blocos multi-linha

---

### 3. **Campos Posicionais Sem Labels Explícitos**

**Problema:**
- Campos como `nome` que usam `position_hint` não geravam candidatos suficientes quando não havia labels.

**Solução Generalista:**
- **Arquivo:** `src/matching/candidates.py` - `_generate_position_candidates`
- Matching de quadrante mais flexível (55% em vez de 50%)
- Sistema de scoring por posição (0.0-1.0) baseado em proximidade ao quadrante ideal
- Ordenação de candidatos por score de posição
- Geração de candidatos posicionais mesmo quando há labels (como fallback)

**Aplicável a:** Qualquer campo com `position_hint` definido

---

### 4. **Rejeição de Labels Como Valores**

**Problema:**
- Labels conhecidos estavam sendo extraídos como valores (ex: "Inscrição" extraído como valor de `nome`).

**Solução Generalista:**
- **Arquivo:** `src/extraction/text_extractor.py` - `extract_from_candidate`
- Lista expandida de labels comuns (incluindo variações e abreviações)
- 4 estratégias de rejeição:
  1. Match exato
  2. Match por prefixo (texto é essencialmente só o label)
  3. Sequências de labels (≥70% das palavras são labels)
  4. Texto curto que é exatamente um label
- Lógica mais precisa: só rejeita se for claramente apenas um label, não valores que contêm palavras de label

**Aplicável a:** Qualquer campo que possa extrair labels acidentalmente

---

### 5. **Extração de Partes Específicas de Linhas Multi-valor**

**Problema:**
- Uma linha pode conter múltiplos valores (ex: "101943 PR CONSELHO SECCIONAL") e o sistema precisa extrair apenas a parte relevante.

**Solução Generalista:**
- **Arquivo:** `src/extraction/text_extractor.py` - `extract_from_candidate`
- Para campos de tipo curto (number, id_simple, uf, alphanum_code):
  - Tenta cada parte da linha
  - Seleciona a primeira que passa type-gate
  - Fallback para primeira parte se curta (≤10 chars)
- Para campos de tipo longo (text):
  - Mantém mais contexto
  - Trunca se muito longo (>50 chars → primeiros 5 tokens)

**Aplicável a:** Qualquer campo com valores estruturados em uma linha

---

### 6. **Melhoria na Extração de Text Window no Matcher**

**Problema:**
- Quando `first_below_same_column` encontrava valores multi-linha, não extraía a parte específica.

**Solução Generalista:**
- **Arquivo:** `src/matching/matcher.py` - `match_fields`
- Após encontrar linha correspondente, processa por tipo de campo
- Para tipos curtos, tenta extrair parte específica que passa type-gate
- Mantém fallback para linha completa se necessário

**Aplicável a:** Qualquer relação espacial que encontre blocos multi-linha

---

## Arquivos Modificados

1. **`src/matching/candidates.py`**
   - `_find_label_blocks_lightweight`: Verificação de linhas individuais em blocos multi-linha
   - `_generate_position_candidates`: Matching de posição mais flexível com scoring

2. **`src/extraction/text_extractor.py`**
   - `extract_from_candidate`: Extração de linha correspondente em blocos multi-linha
   - Rejeição melhorada de labels como valores
   - Extração de partes específicas por tipo de campo

3. **`src/matching/matcher.py`**
   - Extração de text_window melhorada para valores multi-linha

---

## Princípios das Soluções

### 1. **Generalidade**
- Nenhuma solução é específica para um PDF ou campo
- Todas usam padrões e estruturas comuns de documentos

### 2. **Robustez**
- Fallbacks múltiplos quando uma estratégia falha
- Thresholds adaptativos baseados em contexto

### 3. **Type-Aware**
- Processamento diferente baseado no tipo do campo
- Type-gate usado para validar e filtrar partes extraídas

### 4. **Multi-linha First**
- Tratamento especial para blocos multi-linha
- Matching de índices de linha quando possível

---

## Benefícios Esperados

1. **Labels em blocos multi-linha:** Mais labels encontrados
2. **Valores estruturados:** Extração precisa de partes específicas
3. **Campos posicionais:** Melhor cobertura de candidatos
4. **Menos falsos positivos:** Labels rejeitados como valores
5. **Valores multi-linha:** Extração da linha/parte correta

---

## Testes Recomendados

Após essas correções, testar com:
- PDFs com blocos multi-linha (labels e values)
- PDFs com campos posicionais (sem labels explícitos)
- PDFs com valores estruturados em uma linha
- PDFs com variações de texto (acentos, normalização)


