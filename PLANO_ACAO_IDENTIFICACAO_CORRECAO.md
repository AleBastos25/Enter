# Plano de Ação - Identificação e Correção de Erros v3.0

## 📊 Situação Atual

- **Precisão Geral:** 43.24% (16/37 campos)
- **Status:** CRÍTICO - Abaixo de 50%
- **Campos com Problemas:** 21 campos retornando `null` ou valores incorretos
- **Objetivo:** Aumentar precisão para >80%

## 🎯 Estratégia Geral

1. **Fase 1: Diagnóstico** - Identificar causas raiz dos problemas
2. **Fase 2: Correção Incremental** - Corrigir por ordem de impacto
3. **Fase 3: Validação** - Testar e validar correções
4. **Fase 4: Otimização** - Melhorar casos edge

---

## FASE 1: DIAGNÓSTICO DETALHADO

### 1.1 Instrumentação de Debug

**Objetivo:** Criar ferramentas para inspecionar o fluxo completo do pipeline

#### Tarefas:
- [ ] **Criar script de debug detalhado** (`scripts/debug_pipeline_v3.py`)
  - Logar cada etapa do pipeline
  - Salvar estado intermediário (candidates, assignment, etc.)
  - Gerar relatório HTML/JSON com visualização

- [ ] **Adicionar logs estruturados no pipeline**
  - Logar entrada/saída de cada função crítica
  - Salvar em arquivo JSON para análise posterior
  - Incluir: `build_candidate_sets`, `solve_assignment`, `find_label_value_pairs`, `extract_from_candidate`

- [ ] **Criar visualizador de grafo ortogonal**
  - Mostrar grafo ortogonal construído
  - Destacar labels encontrados e values associados
  - Mostrar caminhos de busca LABEL→VALUE

**Arquivos a criar/modificar:**
- `scripts/debug_pipeline_v3.py` (novo)
- `src/core/pipeline.py` (adicionar logging)
- `scripts/visualize_orthogonal_graph.py` (novo)

**Critério de sucesso:** Conseguir visualizar o fluxo completo para um PDF específico

---

### 1.2 Análise por Componente

**Objetivo:** Verificar cada componente v3.0 individualmente

#### 1.2.1 Verificar Grafo Ortogonal

**Teste:**
```python
# scripts/test_orthogonal_graph.py
- Verificar se orthogonal_graph está sendo construído
- Verificar se arestas estão corretas (up, down, left, right)
- Comparar com grafo esperado para oab_1.pdf
```

**Checklist:**
- [ ] `compute_spacing_thresholds` está calculando limiares corretos?
- [ ] `build_orthogonal_graph` está criando arestas corretas?
- [ ] Arestas estão conectando blocks corretos?
- [ ] Grafo está sendo anexado ao layout?

**Arquivos a verificar:**
- `src/graph/spacing_model.py`
- `src/graph/orthogonal_edges.py`
- `src/core/pipeline.py` (linha ~158-164)

---

#### 1.2.2 Verificar Roles (R-H*, R-L*, R-V*)

**Teste:**
```python
# scripts/test_roles.py
- Verificar se roles estão sendo atribuídos corretamente
- Verificar propagação por estilo (E-1/E-2)
- Comparar com roles esperados
```

**Checklist:**
- [ ] `assign_roles` está atribuindo HEADER, LABEL, VALUE corretamente?
- [ ] Propagação por estilo está funcionando?
- [ ] Roles estão sendo anexados ao layout (`block_roles`)?

**Arquivos a verificar:**
- `src/graph/roles_rules.py`
- `src/core/pipeline.py` (verificar se roles são computados)

---

#### 1.2.3 Verificar Label-Value Pairs

**Teste:**
```python
# scripts/test_label_value.py
- Para cada campo, verificar se labels são encontrados
- Verificar se busca ortogonal encontra values
- Verificar se type-gate está passando/falhando corretamente
```

**Checklist:**
- [ ] `build_lexicon` está gerando léxico correto?
- [ ] `find_label_value_pairs` está encontrando pairs?
- [ ] Busca ortogonal (→, ↓, ↑, ←) está funcionando?
- [ ] Type-gate está rejeitando candidatos inválidos?

**Arquivos a verificar:**
- `src/core/schema.py` (`build_lexicon`)
- `src/matching/label_value.py` (`find_label_value_pairs`)
- `src/validation/type_gates.py`

**Campos prioritários para teste:**
- `nome` (oab_1.pdf) - deve encontrar "JOANA D'ARC"
- `inscricao` (oab_1.pdf) - deve encontrar "101943"
- `seccional` (oab_1.pdf) - deve encontrar "PR"
- `situacao` (oab_1.pdf) - deve encontrar "REGULAR"

---

#### 1.2.4 Verificar Candidate Generation

**Teste:**
```python
# scripts/test_candidates.py
- Verificar se candidate_sets está sendo populado
- Verificar cada estratégia de geração (label-based, pattern-based, etc.)
- Verificar se candidates passam type-gate
```

**Checklist:**
- [ ] `build_candidate_sets` está gerando candidatos?
- [ ] Cada estratégia (label, pattern, position, table) está funcionando?
- [ ] Candidatos estão sendo filtrados corretamente?
- [ ] Candidatos estão associados aos campos corretos?

**Arquivos a verificar:**
- `src/matching/candidates.py`
- `src/core/pipeline.py` (linha ~234-240)

---

#### 1.2.5 Verificar Assignment

**Teste:**
```python
# scripts/test_assignment.py
- Verificar se assignment está resolvendo corretamente
- Verificar se constraints estão sendo aplicadas
- Verificar se conflicts estão sendo resolvidos
```

**Checklist:**
- [ ] `solve_assignment` está retornando picks corretos?
- [ ] Score matrix está sendo construída corretamente?
- [ ] Constraints (type-gate, footer, exclusivity) estão funcionando?
- [ ] Fallback para `match_fields` está sendo usado quando necessário?

**Arquivos a verificar:**
- `src/matching/assign.py`
- `src/llm/scorer.py`
- `src/core/pipeline.py` (linha ~280-393)

---

#### 1.2.6 Verificar Extração de Texto

**Teste:**
```python
# scripts/test_text_extraction.py
- Verificar se extract_from_candidate está extraindo corretamente
- Verificar join_multiline_values
- Verificar ROI extraction para same_block
```

**Checklist:**
- [ ] `extract_from_candidate` está extraindo texto correto?
- [ ] Join de valores multiline está funcionando?
- [ ] ROI extraction está funcionando para same_block?
- [ ] Normalização está funcionando?

**Arquivos a verificar:**
- `src/extraction/text_extractor.py`
- `src/extraction/join_multiline.py`
- `src/core/pipeline.py` (linha ~469-507)

---

### 1.3 Comparação com Comportamento Esperado

**Objetivo:** Comparar com ground truth e identificar gaps

#### Tarefas:
- [ ] **Criar script de análise comparativa** (`scripts/analyze_failures.py`)
  - Para cada campo com erro, identificar:
    - Quantos candidatos foram gerados?
    - Qual candidato foi escolhido?
    - Por que não foi escolhido o candidato correto?
    - Qual foi o score de cada candidato?

- [ ] **Análise de casos específicos:**
  - `nome` em oab_1.pdf: Por que não encontra "JOANA D'ARC"?
  - `inscricao` em oab_1.pdf: Por que não encontra "101943"?
  - `situacao` em oab_1.pdf: Por que não encontra "REGULAR"?
  - `endereco_profissional`: Por que falta "SÃO PAULO - SP"?

---

## FASE 2: CORREÇÃO INCREMENTAL

### 2.1 Correções Críticas (Prioridade ALTA)

#### Problema 1: Campos retornando `null` (21 campos)

**Hipóteses:**
1. `find_label_value_pairs` não está sendo chamado ou não encontra pairs
2. `build_candidate_sets` não está gerando candidatos
3. `solve_assignment` não está escolhendo candidatos
4. `extract_from_candidate` está falhando na extração

**Plano de Correção:**

**2.1.1 Verificar se `find_label_value_pairs` está sendo usado**

- [ ] Verificar se `find_label_value_pairs` está sendo chamado no pipeline
- [ ] Se não estiver, adicionar chamada antes de `build_candidate_sets`
- [ ] Integrar resultados de `find_label_value_pairs` em `candidate_sets`

**Arquivos:**
- `src/core/pipeline.py` - Verificar se está sendo usado
- `src/matching/candidates.py` - Integrar label_value pairs

**2.1.2 Corrigir geração de candidatos**

- [ ] Verificar se `_find_label_blocks_lightweight` está encontrando labels
- [ ] Melhorar matching de labels (Jaccard/Levenshtein pode ser muito restritivo)
- [ ] Adicionar fallback para campos sem labels explícitos (ex: `nome`)

**Arquivos:**
- `src/matching/candidates.py` - `_find_label_blocks_lightweight`
- `src/matching/candidates.py` - `_generate_position_candidates`

**2.1.3 Corrigir busca ortogonal**

- [ ] Verificar se `_orthogonal_search` está seguindo direções corretas
- [ ] Verificar se limitações de hops (1-3) não estão muito restritivas
- [ ] Verificar se type-gate não está rejeitando candidatos válidos

**Arquivos:**
- `src/matching/label_value.py` - `_orthogonal_search`
- `src/validation/type_gates.py` - `type_gate`

**2.1.4 Corrigir assignment**

- [ ] Verificar se score matrix está sendo construída corretamente
- [ ] Verificar se constraints não estão muito restritivas
- [ ] Adicionar fallback mais robusto quando assignment falha

**Arquivos:**
- `src/matching/assign.py` - `solve_assignment`
- `src/llm/scorer.py` - `score_matrix`
- `src/core/pipeline.py` - Fallback para match_fields

---

#### Problema 2: Extração parcial (`endereco_profissional`)

**Hipótese:** Join de valores multiline não está funcionando ou ROI extraction está cortando texto

**Plano de Correção:**

- [ ] Verificar `join_multiline_values` - está sendo chamado?
- [ ] Verificar ROI extraction para same_block - está incluindo todo o texto?
- [ ] Adicionar lógica para buscar valores adjacentes na mesma linha/coluna

**Arquivos:**
- `src/extraction/join_multiline.py`
- `src/extraction/text_extractor.py` - `_extract_text_window`
- `src/core/pipeline.py` - Aplicar join antes de extrair

---

#### Problema 3: Campo com valor incorreto (`selecao_de_parcelas`)

**Hipótese:** Assignment está atribuindo candidato errado ou type-gate está aceitando valor incorreto

**Plano de Correção:**

- [ ] Verificar constraints de exclusividade no assignment
- [ ] Melhorar type-gate para enum fields (rejeitar valores que não estão em enum_options)
- [ ] Adicionar validação pós-extraction para campos enum

**Arquivos:**
- `src/matching/assign.py` - Exclusivity constraints
- `src/validation/type_gates.py` - Enum validation
- `src/core/pipeline.py` - Post-extraction validation

---

### 2.2 Correções Moderadas (Prioridade MÉDIA)

#### Problema 4: Campos com precisão parcial (`subsecao`, `sistema`)

**Plano de Correção:**

- [ ] Analisar casos específicos onde funciona vs não funciona
- [ ] Ajustar thresholds de matching
- [ ] Melhorar regras de roles para categorizar melhor

**Arquivos:**
- `src/matching/candidates.py` - Ajustar thresholds
- `src/graph/roles_rules.py` - Melhorar regras

---

## FASE 3: VALIDAÇÃO

### 3.1 Testes Unitários

**Objetivo:** Criar testes para componentes críticos

#### Tarefas:
- [ ] **Testes para `find_label_value_pairs`**
  - Testar com diferentes tipos de layouts
  - Testar com diferentes direções (→, ↓, ↑, ←)
  - Testar com diferentes limitações de hops

- [ ] **Testes para `build_candidate_sets`**
  - Testar cada estratégia de geração
  - Testar com campos sem labels
  - Testar com campos de diferentes tipos

- [ ] **Testes para `solve_assignment`**
  - Testar com diferentes score matrices
  - Testar com constraints
  - Testar com conflicts

**Arquivos a criar:**
- `tests/test_label_value.py`
- `tests/test_candidates.py`
- `tests/test_assignment.py`

---

### 3.2 Testes de Integração

**Objetivo:** Testar pipeline completo com casos reais

#### Tarefas:
- [ ] **Teste end-to-end para oab_1.pdf**
  - Verificar se todos os campos são extraídos
  - Comparar com ground truth
  - Analisar traces

- [ ] **Teste end-to-end para tela_sistema_1.pdf**
  - Verificar campos de data
  - Verificar campos de enum

- [ ] **Teste batch completo**
  - Executar em todos os PDFs
  - Comparar com ground truth
  - Gerar relatório de precisão

---

### 3.3 Validação de Precisão

**Objetivo:** Garantir que precisão aumenta após correções

#### Métricas:
- [ ] Precisão geral > 80%
- [ ] Precisão por campo > 70% (exceto campos edge)
- [ ] Precisão por PDF > 70%

**Comando:**
```bash
python scripts/compare_with_ground_truth.py --results test_results.json --ground-truth ground_truth.json --print
```

---

## FASE 4: OTIMIZAÇÃO

### 4.1 Melhorias de Performance

- [ ] Otimizar busca ortogonal (limitar área de busca)
- [ ] Cache de resultados intermediários
- [ ] Paralelização de processamento quando possível

---

### 4.2 Melhorias de Precisão

- [ ] Ajustar thresholds baseado em feedback
- [ ] Melhorar regras de roles com mais casos de teste
- [ ] Melhorar type-gates com mais padrões

---

## 📋 CHECKLIST GERAL

### Diagnóstico
- [ ] Script de debug criado e funcionando
- [ ] Logs estruturados implementados
- [ ] Visualizador de grafo ortogonal criado
- [ ] Testes unitários para cada componente criados
- [ ] Análise comparativa executada

### Correção
- [ ] `find_label_value_pairs` integrado e funcionando
- [ ] Geração de candidatos corrigida
- [ ] Busca ortogonal corrigida
- [ ] Assignment corrigido
- [ ] Extração parcial corrigida
- [ ] Valores incorretos corrigidos

### Validação
- [ ] Testes unitários passando
- [ ] Testes de integração passando
- [ ] Precisão geral > 80%
- [ ] Relatório de comparação gerado

---

## 🎯 PRIORIZAÇÃO

### Semana 1: Diagnóstico
- Focar em identificar causas raiz
- Criar ferramentas de debug
- Executar análises comparativas

### Semana 2: Correções Críticas
- Corrigir campos retornando `null`
- Corrigir extração parcial
- Corrigir valores incorretos

### Semana 3: Validação e Otimização
- Validar correções
- Ajustar thresholds e regras
- Otimizar performance

---

## 📝 NOTAS

- **Testar incrementalmente:** Não fazer todas as correções de uma vez
- **Validar após cada correção:** Executar testes após cada mudança
- **Documentar mudanças:** Adicionar comentários e logs
- **Manter compatibilidade:** Não quebrar código existente que funciona

---

## 🔗 ARQUIVOS RELACIONADOS

- `TEST_RESULTS_V3.md` - Resultados do teste
- `comparison_report.json` - Relatório detalhado
- `ground_truth.json` - Ground truth para comparação
- `scripts/compare_with_ground_truth.py` - Script de comparação

