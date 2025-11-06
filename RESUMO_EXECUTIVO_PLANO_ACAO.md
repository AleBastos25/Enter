# Resumo Executivo - Plano de Ação v3.0

## 📌 Objetivo

Aumentar a precisão de extração de **43.24%** para **>80%** através de identificação sistemática e correção de erros na migração v3.0.

## 🎯 Estratégia em 4 Fases

### FASE 1: DIAGNÓSTICO (Semana 1)
**Objetivo:** Identificar causas raiz dos problemas

**Ações Principais:**
1. Criar ferramentas de debug (`scripts/debug_pipeline_v3.py`)
2. Verificar cada componente v3.0 individualmente:
   - Grafo ortogonal
   - Roles (HEADER, LABEL, VALUE)
   - Label-Value pairs
   - Candidate generation
   - Assignment
   - Text extraction
3. Comparar com comportamento esperado

**Entregas:**
- Script de debug funcionando
- Relatórios de análise por componente
- Identificação clara de causas raiz

---

### FASE 2: CORREÇÃO (Semana 2)
**Objetivo:** Corrigir problemas identificados

**Problemas Críticos a Corrigir:**

1. **21 campos retornando `null`**
   - Integrar `find_label_value_pairs` no pipeline
   - Corrigir geração de candidatos
   - Corrigir busca ortogonal
   - Corrigir assignment

2. **Extração parcial (`endereco_profissional`)**
   - Corrigir `join_multiline_values`
   - Corrigir ROI extraction

3. **Valor incorreto (`selecao_de_parcelas`)**
   - Melhorar constraints de exclusividade
   - Melhorar type-gate para enum

**Entregas:**
- Correções implementadas
- Testes passando para casos críticos

---

### FASE 3: VALIDAÇÃO (Semana 3)
**Objetivo:** Validar correções e garantir precisão >80%

**Ações:**
1. Testes unitários para componentes críticos
2. Testes de integração end-to-end
3. Validação de precisão com ground truth

**Métricas de Sucesso:**
- Precisão geral > 80%
- Precisão por campo > 70%
- Precisão por PDF > 70%

---

### FASE 4: OTIMIZAÇÃO (Contínua)
**Objetivo:** Melhorar performance e precisão adicional

**Ações:**
- Otimizar busca ortogonal
- Ajustar thresholds baseado em feedback
- Melhorar regras de roles

---

## 🔍 Problemas Identificados (Resumo)

| Problema | Impacto | Prioridade | Status |
|---------|---------|-----------|--------|
| 21 campos retornando `null` | Alto | 🔴 Crítica | Investigando |
| Extração parcial (`endereco_profissional`) | Médio | 🟡 Média | Investigando |
| Valor incorreto (`selecao_de_parcelas`) | Médio | 🟡 Média | Investigando |
| Campos com precisão parcial | Baixo | 🟢 Baixa | Documentado |

---

## 📋 Próximos Passos Imediatos

1. **HOJE:**
   - [ ] Executar `scripts/debug_pipeline_v3.py` em `oab_1.pdf`
   - [ ] Analisar output para identificar onde o pipeline falha
   - [ ] Verificar se `find_label_value_pairs` está sendo chamado

2. **ESTA SEMANA:**
   - [ ] Completar diagnóstico de todos os componentes
   - [ ] Identificar causas raiz específicas
   - [ ] Priorizar correções

3. **PRÓXIMA SEMANA:**
   - [ ] Implementar correções críticas
   - [ ] Validar correções
   - [ ] Executar testes batch completos

---

## 📁 Arquivos Criados

1. **`PLANO_ACAO_IDENTIFICACAO_CORRECAO.md`** - Plano completo detalhado
2. **`scripts/debug_pipeline_v3.py`** - Script de debug para investigação
3. **`RESUMO_EXECUTIVO_PLANO_ACAO.md`** - Este documento

---

## 🚀 Como Começar

### Passo 1: Executar Debug
```bash
python scripts/debug_pipeline_v3.py \
  --pdf data/samples/oab_1.pdf \
  --label carteira_oab \
  --dataset data/samples/dataset.json \
  --output debug_oab_1.json
```

### Passo 2: Analisar Output
```bash
# Ver JSON gerado
cat debug_oab_1.json | python -m json.tool

# Comparar com ground truth
python scripts/compare_with_ground_truth.py \
  --results test_results.json \
  --ground-truth ground_truth.json \
  --print
```

### Passo 3: Focar no Problema
- Identificar qual etapa está falhando
- Verificar se candidatos estão sendo gerados
- Verificar se assignment está escolhendo corretamente

---

## 📊 Métricas de Acompanhamento

### Antes (Atual)
- Precisão geral: **43.24%**
- Campos corretos: **16/37**
- Campos com problema: **21**

### Meta (Após Correções)
- Precisão geral: **>80%**
- Campos corretos: **>29/37**
- Campos com problema: **<8**

---

## ⚠️ Riscos e Mitigações

| Risco | Mitigação |
|-------|-----------|
| Correções podem quebrar código que funciona | Testar incrementalmente, validar após cada mudança |
| Causas raiz podem ser múltiplas | Focar em uma de cada vez, documentar cada descoberta |
| Tempo limitado | Priorizar problemas críticos primeiro |

---

## 📞 Contato e Referências

- **Plano Completo:** `PLANO_ACAO_IDENTIFICACAO_CORRECAO.md`
- **Resultados do Teste:** `TEST_RESULTS_V3.md`
- **Ground Truth:** `ground_truth.json`
- **Script de Comparação:** `scripts/compare_with_ground_truth.py`

