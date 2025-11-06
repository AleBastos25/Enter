# Análise de Causas Raiz dos Erros

Baseado no debug profundo realizado, aqui estão as causas raiz identificadas para cada tipo de erro:

---

## 🔴 ERRO #1: Campo `nome` extraindo labels ("Inscrição", "Subseção")

### Evidências do Debug:
- **oab_1.pdf**: Bloco [0] = "JOANA D'ARC" (correto), mas sistema extraiu "Inscrição"
- **oab_2.pdf**: Bloco [0] = "LUIS FILIPE ARAUJO AMARAL" (correto), mas sistema extraiu "Inscrição"  
- **oab_3.pdf**: Bloco [0] = "SON GOKU" (correto), mas sistema extraiu "Subseção"

### Causa Raiz Identificada:

**Problema Principal**: O sistema está encontrando labels de outros campos ("Inscrição", "Subseção") como candidatos para o campo `nome` e aceitando-os.

**Análise Técnica**:
1. O campo `nome` não tem labels explícitos no documento (é um campo de posição - "normalmente no canto superior esquerdo")
2. O sistema está fazendo matching de labels e encontrando "Inscrição" e "Subseção" como candidatos
3. A lógica de rejeição de label-only não está funcionando porque:
   - "Inscrição" não está na lista de sinônimos de `nome` (sinônimos = ['nome', 'name'])
   - O sistema não está detectando que "Inscrição" é um label de outro campo
   - O type gate está aceitando "Inscrição" como texto válido

**Onde está o problema**:
- `src/matching/matcher.py`: `_find_label_blocks()` pode estar encontrando labels incorretos
- `src/extraction/text_extractor.py`: `extract_from_candidate()` tem lógica de rejeição de label-only, mas pode não estar sendo aplicada corretamente
- O campo `nome` deveria usar position_hint="top-left", mas pode não estar funcionando

**Solução Necessária**:
1. Adicionar lista de labels conhecidos que nunca devem ser extraídos como valores
2. Melhorar matching de posição para campos sem labels explícitos
3. Reforçar rejeição de label-only para campos de texto

---

## 🔴 ERRO #2: Campos não sendo extraídos (20 erros)

### Evidências do Debug:

#### Campos Numéricos (`inscricao`):
- **Blocos extraídos**: [2] = "101943\nPR\nCONSELHO SECCIONAL - PARANÁ" em oab_1.pdf
- **Problema**: O valor "101943" está no bloco, mas não está sendo extraído

#### Campos Enum (`categoria`, `situacao`):
- **Blocos extraídos**: [3] = "SUPLEMENTAR" em oab_1.pdf (categoria está visível!)
- **Problema**: Enum scan não está encontrando valores mesmo quando estão visíveis nos blocos

#### Campos de Texto (`seccional`, `subsecao`, `endereco_profissional`):
- **Blocos extraídos**: Valores estão presentes nos blocos
- **Problema**: Labels estão sendo encontrados, mas valores não estão sendo extraídos via neighborhood

### Causas Raiz Identificadas:

#### 2.1. Labels não sendo encontrados corretamente
**Evidência**: 
- Bloco [1] = "Inscrição\nSeccional\nSubseção" (múltiplos labels em um bloco)
- O sistema pode não estar fazendo split corretamente de labels que estão no mesmo bloco

**Onde está o problema**:
- `src/matching/matcher.py`: `_find_label_blocks()` pode não estar encontrando labels quando estão em blocos multi-linha
- Normalização pode estar removendo acentos de forma que labels não são encontrados (ex: "Inscrição" vs "Inscriçao")

#### 2.2. Neighborhood não encontrando valores
**Evidência**:
- Bloco [1] = "Inscrição\nSeccional\nSubseção" (labels)
- Bloco [2] = "101943\nPR\nCONSELHO SECCIONAL - PARANÁ" (valores)
- Os valores estão no bloco seguinte, mas o sistema não está encontrando via `first_below_same_column`

**Onde está o problema**:
- `src/layout/builder.py`: Relações `below_on_same_column` podem não estar sendo construídas corretamente
- `src/matching/matcher.py`: Neighborhood matching pode não estar funcionando quando valores estão em blocos multi-linha

#### 2.3. Type gate rejeitando candidatos válidos
**Evidência**:
- `inscricao` (type=id_simple) com valor "101943" pode estar sendo rejeitado
- `seccional` (type=uf) com valor "PR" pode estar sendo rejeitado

**Onde está o problema**:
- `src/validation/patterns.py`: `type_gate_generic()` pode estar muito restritivo
- Validação pode estar rejeitando valores quando há múltiplos valores no mesmo bloco

#### 2.4. Enum scan não funcionando
**Evidência**:
- `categoria` = "SUPLEMENTAR" está visível no bloco [3] em oab_1.pdf
- Enum options estão corretos: ['ADVOGADO', 'ADVOGADA', 'SUPLEMENTAR', ...]
- Mas o sistema não está encontrando "SUPLEMENTAR"

**Onde está o problema**:
- `src/matching/matcher.py`: Global enum scan pode não estar funcionando
- Validação de enum pode estar falhando (case-insensitive, accent-insensitive)

---

## 🟡 ERRO #3: `selecao_de_parcelas` extraindo data quando deveria ser null

### Causa Raiz:
- O sistema está encontrando a data "2021-02-04" e atribuindo incorretamente ao campo `selecao_de_parcelas`
- Este campo deveria ser um enum com opções ["VENCIDO", "PAGO", "PENDENTE"]
- O type gate está aceitando qualquer data como válida para este campo

**Onde está o problema**:
- `src/validation/patterns.py`: Validação de enum não está rejeitando valores que não estão na lista
- `src/matching/matcher.py`: Enum scan pode estar aceitando valores incorretos

---

## 📊 Resumo por Problema Técnico

### 1. Blocos Multi-linha com Múltiplos Labels
**Problema**: Blocos como "Inscrição\nSeccional\nSubseção" não estão sendo processados corretamente
**Impacto**: Labels não são encontrados, valores não são extraídos
**Solução**: Melhorar parsing de blocos multi-linha para identificar múltiplos labels

### 2. Neighborhood não Funcionando para Blocos Multi-linha
**Problema**: Quando valores estão em blocos com múltiplas linhas, neighborhood não está encontrando
**Impacto**: Valores não são extraídos mesmo quando estão próximos aos labels
**Solução**: Melhorar neighborhood matching para blocos multi-linha

### 3. Rejeição de Label-only não Funcionando
**Problema**: Labels de outros campos estão sendo aceitos como valores
**Impacto**: Campos extraem labels em vez de valores
**Solução**: Melhorar detecção de label-only e adicionar lista de labels conhecidos

### 4. Enum Scan não Funcionando
**Problema**: Valores de enum visíveis nos blocos não estão sendo encontrados
**Impacto**: Campos enum retornam null
**Solução**: Melhorar global enum scan e validação de enum

### 5. Type Gate Muito Restritivo ou Permissivo
**Problema**: 
- Muito restritivo: rejeita valores válidos (ex: números, UF)
- Muito permissivo: aceita valores incorretos (ex: data em campo enum)
**Impacto**: Valores não são extraídos ou valores incorretos são aceitos
**Solução**: Ajustar type gate para cada tipo de campo

---

## 🎯 Prioridades de Correção

1. **ALTA**: Corrigir extração de labels como valores (erro #1)
2. **ALTA**: Melhorar parsing de blocos multi-linha com múltiplos labels
3. **ALTA**: Melhorar neighborhood matching para blocos multi-linha
4. **MÉDIA**: Corrigir enum scan para encontrar valores visíveis
5. **MÉDIA**: Ajustar type gate para cada tipo de campo
6. **BAIXA**: Melhorar rejeição de valores incorretos em campos enum


