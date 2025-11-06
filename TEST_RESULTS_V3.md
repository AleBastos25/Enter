# Resultados do Teste - Migração v3.0

## Execução do Teste

**Data:** Teste executado após migração para v3.0 Graph-Orthogonal Engine  
**Comando:** `python scripts/batch_process.py --folder data/samples --out test_results.json`  
**Ground Truth:** `ground_truth.json`  
**Comparação:** `python scripts/compare_with_ground_truth.py`

## 📊 Resumo dos Resultados

### Métricas Globais
- **Precisão Geral:** 43.24% (16/37 campos corretos)
- **Precisão Média por PDF:** 45.44%
- **Total de Campos:** 37
- **Corretos:** 16
- **Incorretos:** 21
- **Faltando:** 0 (todos os campos foram processados, mas muitos retornaram `null`)

### Status: ⚠️ **CRÍTICO** - Precisão abaixo de 50%

## 📋 Análise por PDF

### 1. carteira_oab (oab_1.pdf)
- **Precisão:** 25.00% (2/8 campos)
- **Campos Corretos:** `categoria`, `telefone_profissional`
- **Campos com Problemas:**
  - `nome`: `null` (esperado: "JOANA D'ARC")
  - `inscricao`: `null` (esperado: "101943")
  - `seccional`: `null` (esperado: "PR")
  - `subsecao`: `null` (esperado: "CONSELHO SECCIONAL - PARANÁ")
  - `situacao`: `null` (esperado: "REGULAR")
  - `endereco_profissional`: Parcialmente correto (falta "SÃO PAULO - SP")

### 2. carteira_oab (oab_2.pdf)
- **Precisão:** 14.29% (1/7 campos)
- **Campos Corretos:** `categoria`
- **Campos com Problemas:** Mesmos problemas de oab_1.pdf

### 3. carteira_oab (oab_3.pdf)
- **Precisão:** 42.86% (3/7 campos)
- **Campos Corretos:** `categoria`, `subsecao`, `telefone_profissional`
- **Campos com Problemas:** Similar aos outros PDFs OAB

### 4. tela_sistema (tela_sistema_1.pdf)
- **Precisão:** 57.14% (4/7 campos)
- **Campos Corretos:** `quantidade_parcelas`, `produto`, `tipo_de_operacao`, `tipo_de_sistema`
- **Campos com Problemas:**
  - `data_base`: `null` (esperado: "2025-09-05")
  - `data_verncimento`: `null` (esperado: "2025-10-12")
  - `sistema`: `null` (esperado: "CONSIGNADO")

### 5. tela_sistema (tela_sistema_2.pdf)
- **Precisão:** 100.00% (5/5 campos) ✅
- **Status:** Todos os campos corretos!

### 6. tela_sistema (tela_sistema_3.pdf)
- **Precisão:** 33.33% (1/3 campos)
- **Campos Corretos:** `total_de_parcelas`
- **Campos com Problemas:**
  - `data_referencia`: `null` (esperado: "2021-02-04")
  - `selecao_de_parcelas`: Valor incorreto "2021-02-04" (esperado: `null`)

## 📈 Análise por Campo

### Campos com 100% de Precisão ✅
- `categoria`: 100% (3/3)
- `telefone_profissional`: 100% (2/2) - Correto ao retornar `null` quando não existe
- `pesquisa_por`: 100% (1/1)
- `pesquisa_tipo`: 100% (1/1)
- `produto`: 100% (1/1)
- `quantidade_parcelas`: 100% (1/1)
- `tipo_de_operacao`: 100% (1/1)
- `tipo_de_sistema`: 100% (1/1)
- `total_de_parcelas`: 100% (1/1)
- `valor_parcela`: 100% (1/1)
- `cidade`: 100% (1/1)

### Campos com 0% de Precisão ❌
- `nome`: 0% (0/3) - Todos retornando `null`
- `inscricao`: 0% (0/3) - Todos retornando `null`
- `seccional`: 0% (0/3) - Todos retornando `null`
- `situacao`: 0% (0/3) - Todos retornando `null`
- `data_base`: 0% (0/1)
- `data_verncimento`: 0% (0/1)
- `data_referencia`: 0% (0/1)
- `endereco_profissional`: 0% (0/2) - Parcialmente extraído

### Campos com Precisão Parcial ⚠️
- `subsecao`: 33.33% (1/3)
- `sistema`: 50.00% (1/2)
- `selecao_de_parcelas`: 0% (1/1) - Valor incorreto (extraindo data_referencia)

## 🔍 Problemas Identificados

### 1. **Crítico: Muitos campos retornando `null`**
   - **Impacto:** 21 campos retornando `null` quando deveriam ter valores
   - **Causa Provável:** 
     - A migração para v3.0 pode ter quebrado a detecção de labels
     - O `find_label_value_pairs` pode não estar funcionando corretamente
     - O assignment pode não estar encontrando candidatos adequados
   - **Locais para Investigar:**
     - `src/matching/label_value.py` - Busca ortogonal LABEL→VALUE
     - `src/matching/assign.py` - Assignment solver
     - `src/matching/candidates.py` - Geração de candidatos

### 2. **Moderado: Valores parcialmente extraídos**
   - `endereco_profissional`: Falta "SÃO PAULO - SP" no final
   - **Causa Provável:** Problema no join de valores multiline ou extração de ROI

### 3. **Moderado: Campo extraindo valor incorreto**
   - `selecao_de_parcelas` em tela_sistema_3.pdf: Extraindo "2021-02-04" (que é data_referencia)
   - **Causa Provável:** Assignment atribuindo candidato errado ou type-gate aceitando valor incorreto

## 🎯 Recomendações

### Prioridade ALTA 🔴
1. **Investigar por que campos retornam `null`:**
   - Verificar se `find_label_value_pairs` está encontrando pairs corretos
   - Verificar se `build_candidate_sets` está gerando candidatos
   - Verificar se `solve_assignment` está funcionando

2. **Testar com debug habilitado:**
   ```bash
   python scripts/batch_process.py --folder data/samples --out test_results_debug.json --debug
   ```
   Analisar os traces para entender por que campos não estão sendo extraídos.

3. **Verificar se componentes v3.0 estão sendo usados:**
   - Confirmar que `orthogonal_graph` está sendo construído
   - Confirmar que `roles_rules` está atribuindo roles corretamente
   - Confirmar que `label_value` está fazendo busca ortogonal

### Prioridade MÉDIA 🟡
1. **Corrigir extração parcial de endereco_profissional:**
   - Verificar `join_multiline_values`
   - Verificar ROI extraction para same_block

2. **Corrigir atribuição incorreta de selecao_de_parcelas:**
   - Verificar constraints do assignment
   - Verificar type-gate para campos de enum

### Prioridade BAIXA 🟢
1. **Melhorar precisão de campos parciais** (subsecao, sistema)

## 📝 Próximos Passos

1. Executar teste com debug para obter traces detalhados
2. Analisar logs de um PDF específico (ex: oab_1.pdf) para entender o fluxo
3. Verificar se todos os componentes v3.0 estão implementados e funcionando
4. Comparar comportamento antes e depois da migração (se possível)
5. Criar testes unitários para componentes críticos (label_value, assignment)

## 📁 Arquivos Gerados

- `test_results.json` - Resultados do batch processing
- `comparison_report.json` - Relatório detalhado de comparação
- `TEST_RESULTS_V3.md` - Este documento

