# Análise Detalhada dos Erros - Ground Truth vs Output Atual

## Resumo Executivo

- **Total de PDFs**: 6
- **PDFs com erros**: 5
- **Total de erros**: 24
  - **Extração faltando (missing_extraction)**: 20 erros
  - **Extração extra (extra_extraction)**: 1 erro
  - **Valor errado (wrong_value)**: 3 erros

---

## 🔴 ERRO CRÍTICO #1: Campo `nome` extraindo texto de labels

### Erros Observados:
- **oab_1.pdf**: `nome` = "Inscrição" (esperado: "JOANA D'ARC")
- **oab_2.pdf**: `nome` = "Inscrição" (esperado: "LUIS FILIPE ARAUJO AMARAL")
- **oab_3.pdf**: `nome` = "Subseção" (esperado: "SON GOKU")

### Causa Provável:
O sistema está encontrando o label "Inscrição" ou "Subseção" como candidato para o campo `nome`, e a lógica de rejeição de label-only não está funcionando corretamente.

**Localização do problema**:
1. **`src/matching/matcher.py`**: A função `_find_label_blocks()` pode estar encontrando labels incorretos como candidatos
2. **`src/extraction/text_extractor.py`**: A função `extract_from_candidate()` tem lógica para rejeitar labels, mas pode não estar sendo aplicada corretamente
3. **`src/matching/matcher.py`**: A função `_extract_text_window()` pode estar retornando o texto do label em vez do valor

### Análise Técnica:
- O campo `nome` provavelmente não tem labels explícitos no documento (é um campo de posição)
- O sistema está encontrando outros labels (como "Inscrição", "Subseção") como candidatos
- A validação de label-only não está detectando que "Inscrição" e "Subseção" são labels, não valores

### Solução Necessária:
1. Melhorar a detecção de label-only para rejeitar palavras que são claramente labels de outros campos
2. Adicionar uma lista de labels conhecidos que nunca devem ser extraídos como valores
3. Melhorar o matching de posição para campos sem labels explícitos (como `nome`)

---

## 🔴 ERRO CRÍTICO #2: Campos não sendo extraídos (20 erros)

### Campos Afetados:

#### **carteira_oab** (oab_1.pdf, oab_2.pdf, oab_3.pdf):
- `inscricao`: Não extraído (esperado: "101943")
- `seccional`: Não extraído (esperado: "PR")
- `subsecao`: Não extraído (esperado: "CONSELHO SECCIONAL - PARANÁ")
- `categoria`: Não extraído (esperado: "SUPLEMENTAR")
- `situacao`: Não extraído (esperado: "REGULAR")
- `endereco_profissional`: Não extraído (esperado: endereço completo)

#### **tela_sistema** (tela_sistema_1.pdf):
- `data_base`: Não extraído (esperado: "2025-09-05")
- `data_verncimento`: Não extraído (esperado: "2025-10-12")
- `sistema`: Não extraído (esperado: "CONSIGNADO")

#### **tela_sistema_3.pdf**:
- `data_referencia`: Não extraído (esperado: "2021-02-04")

### Causas Prováveis:

#### 2.1. Labels não sendo encontrados
**Problema**: A função `_find_label_blocks()` pode não estar encontrando os labels corretos no documento.

**Localização**: `src/matching/matcher.py` - função `_find_label_blocks()`

**Possíveis causas**:
- Normalização de texto removendo acentos pode estar causando problemas de matching
- Threshold de matching muito alto (min_match=0.6 pode ser muito restritivo)
- Sinônimos não sendo gerados corretamente para os campos

#### 2.2. Neighborhood não encontrando valores
**Problema**: Mesmo quando labels são encontrados, o sistema não está encontrando valores nas relações espaciais.

**Localização**: `src/matching/matcher.py` - seção de neighborhood matching

**Possíveis causas**:
- Relações `same_line_right_of` ou `first_below_same_column` não estão sendo construídas corretamente
- Layout graph não está detectando corretamente as relações espaciais
- Valores estão em posições não cobertas pelas relações padrão

#### 2.3. Type gate rejeitando candidatos válidos
**Problema**: Candidatos válidos podem estar sendo rejeitados pelo type gate.

**Localização**: `src/validation/patterns.py` - função `type_gate_generic()`

**Possíveis causas**:
- Type gate muito restritivo para campos numéricos (`inscricao`)
- Type gate não reconhecendo formatos de enum (`categoria`, `situacao`)
- Type gate não reconhecendo formatos de data

#### 2.4. Validação falhando
**Problema**: Candidatos encontrados podem estar falhando na validação final.

**Localização**: `src/extraction/text_extractor.py` - função `extract_from_candidate()`

**Possíveis causas**:
- Validação de tipo muito restritiva
- Normalização de valores removendo informações importantes
- Validação de enum não encontrando valores (para `categoria`, `situacao`)

---

## 🟡 ERRO #3: Campo `selecao_de_parcelas` extraindo valor quando deveria ser null

### Erro Observado:
- **tela_sistema_3.pdf**: `selecao_de_parcelas` = "2021-02-04" (esperado: `null`)

### Causa Provável:
O sistema está encontrando a data "2021-02-04" (que é o valor esperado para `data_referencia`) e atribuindo incorretamente ao campo `selecao_de_parcelas`.

**Possíveis causas**:
1. **Matching incorreto**: O sistema pode estar encontrando um label que parece corresponder a `selecao_de_parcelas` próximo à data
2. **Type gate muito permissivo**: O campo `selecao_de_parcelas` pode estar aceitando qualquer data como válida
3. **Enum scan incorreto**: Se `selecao_de_parcelas` é um enum, o scan global pode estar encontrando valores incorretos

### Solução Necessária:
1. Verificar se o campo `selecao_de_parcelas` está configurado corretamente como enum
2. Melhorar a validação de enum para rejeitar valores que não estão na lista de opções
3. Adicionar validação específica para campos que devem ser null quando não há seleção

---

## 📊 Análise por Tipo de Campo

### Campos Numéricos (`inscricao`)
- **Taxa de erro**: 100% (3/3 PDFs)
- **Problema**: Labels podem estar sendo encontrados, mas valores não estão sendo extraídos
- **Possível causa**: Type gate ou validação rejeitando números, ou neighborhood não encontrando valores ao lado dos labels

### Campos Enum (`categoria`, `situacao`)
- **Taxa de erro**: 100% (3/3 PDFs para categoria, 3/3 para situacao)
- **Problema**: Enum scan não está encontrando valores
- **Possível causa**: 
  - Enum options não sendo inferidos corretamente do schema
  - Enum scan não encontrando valores no documento
  - Validação de enum muito restritiva

### Campos de Texto (`nome`, `endereco_profissional`, `subsecao`)
- **Taxa de erro**: Variável
- **Problema**: 
  - `nome`: Extraindo labels de outros campos
  - `endereco_profissional`: Não extraído (pode ser multi-linha)
  - `subsecao`: Não extraído (funcionou em oab_3.pdf parcialmente)
- **Possível causa**: 
  - Campos de texto precisam de estratégias diferentes (posição, multi-linha)
  - Labels podem não estar sendo encontrados

### Campos de Data (`data_base`, `data_verncimento`, `data_referencia`)
- **Taxa de erro**: 100% (3/3 PDFs)
- **Problema**: Datas não estão sendo extraídas
- **Possível causa**: 
  - Labels não sendo encontrados
  - Formatos de data não sendo reconhecidos pelo type gate
  - Neighborhood não encontrando valores próximos aos labels

### Campos de Sistema (`sistema`)
- **Taxa de erro**: 100% (1/1 PDF)
- **Problema**: Enum "CONSIGNADO" não está sendo encontrado
- **Possível causa**: Enum scan não funcionando ou type gate rejeitando

---

## 🔍 Recomendações de Debug

### 1. Adicionar logs detalhados
Adicionar logs em:
- `_find_label_blocks()`: Para ver quais labels estão sendo encontrados
- `match_fields()`: Para ver quais candidatos estão sendo gerados
- `extract_from_candidate()`: Para ver quais candidatos estão sendo validados

### 2. Verificar schema enrichment
Verificar se:
- Sinônimos estão sendo gerados corretamente
- Enum options estão sendo inferidos do schema
- Types estão sendo inferidos corretamente

### 3. Verificar layout graph
Verificar se:
- Blocks estão sendo extraídos corretamente
- Neighborhood está sendo construído corretamente
- Relações espaciais estão sendo detectadas

### 4. Testar com debug mode
Rodar o pipeline com `debug=True` para ver:
- Quais candidatos estão sendo gerados
- Quais estão passando validação
- Quais estão sendo rejeitados e por quê

---

## 📝 Próximos Passos

1. **Prioridade ALTA**: Corrigir extração de labels como valores (erro #1)
2. **Prioridade ALTA**: Investigar por que labels não estão sendo encontrados (erro #2.1)
3. **Prioridade MÉDIA**: Melhorar neighborhood matching (erro #2.2)
4. **Prioridade MÉDIA**: Ajustar type gate e validação (erro #2.3, #2.4)
5. **Prioridade BAIXA**: Corrigir extração incorreta de `selecao_de_parcelas` (erro #3)


