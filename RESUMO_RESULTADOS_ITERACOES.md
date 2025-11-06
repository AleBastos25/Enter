# Resumo dos Resultados - Iterações de Melhoria

## 📊 Status Atual

**Precisão Global**: 60% (9/15 campos corretos)

### Resumo por PDF

| PDF | Precisão | Corretos | Incorretos | Total |
|-----|----------|----------|------------|-------|
| tela_sistema_1.pdf | 57.14% | 4 | 3 | 7 |
| tela_sistema_2.pdf | 60.00% | 3 | 2 | 5 |
| tela_sistema_3.pdf | 66.67% | 2 | 1 | 3 |

### Estatísticas por Campo

| Campo | Total | Corretos | Incorretos | Taxa de Acerto |
|-------|-------|----------|------------|----------------|
| data_base | 1 | 1 | 0 | 100% ✅ |
| data_referencia | 1 | 1 | 0 | 100% ✅ |
| quantidade_parcelas | 1 | 1 | 0 | 100% ✅ |
| tipo_de_operacao | 1 | 1 | 0 | 100% ✅ |
| tipo_de_sistema | 1 | 1 | 0 | 100% ✅ |
| cidade | 1 | 1 | 0 | 100% ✅ |
| pesquisa_por | 1 | 1 | 0 | 100% ✅ |
| pesquisa_tipo | 1 | 1 | 0 | 100% ✅ |
| total_de_parcelas | 1 | 1 | 0 | 100% ✅ |
| data_verncimento | 1 | 0 | 1 | 0% ❌ |
| produto | 1 | 0 | 1 | 0% ❌ |
| sistema | 2 | 0 | 2 | 0% ❌ |
| valor_parcela | 1 | 0 | 1 | 0% ❌ |
| selecao_de_parcelas | 1 | 0 | 1 | 0% ❌ |

## ❌ Problemas Identificados

### 1. Campos Extraindo Títulos/Headers

**Problema**: `produto` e `sistema` estão extraindo "Detalhamento de saldos por parcelas:" quando deveriam ser `null` ou "CONSIGNADO".

**Campos Afetados**:
- `produto` (tela_sistema_1.pdf): Esperado `null`, Extraído `"Detalhamento de saldos por parcelas:"`
- `sistema` (tela_sistema_1.pdf): Esperado `"CONSIGNADO"`, Extraído `"Detalhamento de saldos por parcelas:"`

**Correções Aplicadas**:
- ✅ Validação para rejeitar textos que terminam com ":" e são longos (>10 caracteres)
- ✅ Validação para rejeitar textos contendo palavras-chave de títulos (detalhamento, resumo, etc.)
- ✅ Validação aplicada em múltiplos pontos do pipeline (antes de adicionar a `cand_texts`)

**Status**: ⚠️ Ainda não completamente resolvido - o texto ainda está sendo extraído

### 2. Campos Extraindo Valores de Outros Campos

**Problema**: Campos similares estão extraindo o mesmo valor.

**Campos Afetados**:
- `data_verncimento` (tela_sistema_1.pdf): Esperado `"2025-10-12"`, Extraído `"2025-09-05"` (mesmo valor de `data_base`)
- `selecao_de_parcelas` (tela_sistema_3.pdf): Esperado `null`, Extraído `"2021-02-04"` (mesmo valor de `data_referencia`)

**Correções Aplicadas**:
- ✅ Melhor detecção de valores duplicados entre campos
- ✅ Priorização de labels específicos para campos similares (ex: "vencimento" para `data_verncimento`)
- ✅ Sinônimos mais específicos para campos de data (`data_base`, `data_verncimento`, `data_referencia`)
- ✅ Validação para rejeitar valores duplicados quando tipos são diferentes

**Status**: ⚠️ Ainda não completamente resolvido

### 3. Campos Opcionais Extraindo Valores Incorretos

**Problema**: Campos que deveriam ser `null` estão extraindo valores incorretos.

**Campos Afetados**:
- `sistema` (tela_sistema_2.pdf): Esperado `null`, Extraído `"2.372,64"`
- `valor_parcela` (tela_sistema_2.pdf): Esperado `null`, Extraído `"2372.64"`

**Correções Aplicadas**:
- ✅ Validação de confiança mínima (0.6) para campos opcionais
- ✅ Rejeição de valores que parecem ser de outro tipo (ex: data para campo money)
- ✅ Validação de enum para campos tipo enum

**Status**: ⚠️ Ainda não completamente resolvido

## ✅ Melhorias Implementadas

### 1. Validação de Enum
- Validação rigorosa para campos enum - só aceita valores que estão na lista de opções
- Extração de opções enum do schema (incluindo "sistema": ["CONSIGNADO", "INTEGRADO", ...])
- Matching parcial para encontrar enum values dentro de textos maiores

### 2. Detecção de Títulos/Headers
- Rejeição de textos que terminam com ":" e são longos (>10 caracteres)
- Detecção de palavras-chave de títulos (detalhamento, resumo, informações, etc.)
- Validação aplicada em múltiplos pontos do pipeline

### 3. Melhor Matching de Labels
- Priorização de labels específicos para campos similares
- Sinônimos mais específicos para campos de data
- Melhor detecção de labels em blocos multi-linha

### 4. Validação de Tipos
- Rejeição de valores que parecem ser de outro tipo (ex: data para campo text, money para campo text)
- Validação de confiança mínima para campos opcionais
- Penalização de candidatos com relações indiretas para campos opcionais

### 5. Detecção de Valores Duplicados
- Detecção de valores duplicados entre campos diferentes
- Rejeição de duplicatas quando tipos são diferentes
- Threshold mais restritivo (20% melhor) para substituir valores duplicados

## 📈 Progresso das Iterações

| Iteração | Precisão | Mudança |
|----------|----------|---------|
| Inicial | 40.54% | - |
| 5 | 60% | +19.46% |
| 6 | 60% | 0% |
| 7 | 60% | 0% |
| 8 | 60% | 0% |
| 9 | 60% | 0% |
| 10 | 60% | 0% |
| 11 | 60% | 0% |

## 🔍 Análise Detalhada dos Erros

### tela_sistema_1.pdf

**Campos Corretos** (4/7):
- ✅ `data_base`: "2025-09-05"
- ✅ `quantidade_parcelas`: null
- ✅ `tipo_de_operacao`: null
- ✅ `tipo_de_sistema`: null

**Campos Incorretos** (3/7):
- ❌ `data_verncimento`: Esperado "2025-10-12", Extraído "2025-09-05"
- ❌ `produto`: Esperado null, Extraído "Detalhamento de saldos por parcelas:"
- ❌ `sistema`: Esperado "CONSIGNADO", Extraído "Detalhamento de saldos por parcelas:"

### tela_sistema_2.pdf

**Campos Corretos** (3/5):
- ✅ `cidade`: null
- ✅ `pesquisa_por`: null
- ✅ `pesquisa_tipo`: null

**Campos Incorretos** (2/5):
- ❌ `sistema`: Esperado null, Extraído "2.372,64"
- ❌ `valor_parcela`: Esperado null, Extraído "2372.64"

### tela_sistema_3.pdf

**Campos Corretos** (2/3):
- ✅ `data_referencia`: "2021-02-04"
- ✅ `total_de_parcelas`: null

**Campos Incorretos** (1/3):
- ❌ `selecao_de_parcelas`: Esperado null, Extraído "2021-02-04"

## 🎯 Próximos Passos Recomendados

1. **Análise Profunda dos PDFs**: 
   - Verificar por que "Detalhamento de saldos por parcelas:" está sendo extraído
   - Verificar onde está o label "vencimento" ou "vcto" no PDF

2. **Melhorar Matching de Labels Específicos**:
   - Garantir que `data_verncimento` encontra o label correto (não o mesmo de `data_base`)
   - Melhorar detecção de labels em casos onde há múltiplos campos similares

3. **Ajustar Thresholds de Confiança**:
   - Revisar threshold mínimo (0.6) para campos opcionais
   - Considerar thresholds específicos por tipo de campo

4. **Melhorar Enum Scan**:
   - Garantir que "CONSIGNADO" seja encontrado para o campo `sistema`
   - Verificar se o enum scan está funcionando corretamente

## 📝 Arquivos Modificados

### Correções Aplicadas
- `src/core/schema.py`: Adicionado enum options para "sistema", sinônimos específicos para campos de data
- `src/extraction/text_extractor.py`: Validação de títulos/headers, validação de enum, rejeição de valores incorretos
- `src/matching/matcher.py`: Melhor detecção de labels em blocos multi-linha
- `src/matching/assign.py`: Detecção melhorada de valores duplicados
- `src/matching/label_value.py`: Priorização de labels específicos
- `src/core/pipeline.py`: Validação de confiança para campos opcionais

### Arquivos de Teste
- `test_iteration_11.json`: Resultados da última iteração
- `comparison_iteration_11.json`: Comparação detalhada com ground truth


