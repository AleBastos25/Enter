# Status das Correções Aplicadas

## ✅ Correções Implementadas

### 1. Correção de `assign_roles` - Duas Passadas
**Problema:** A regra R-V* estava sendo aplicada antes dos LABELs serem identificados, causando dependência circular.

**Solução:** Implementada passada dupla:
- **Primeira passada:** Identifica HEADER e LABEL (não dependem de outros roles)
- **Segunda passada:** Identifica VALUE (depende de LABELs já identificados)

**Arquivo:** `src/graph/roles_rules.py` (linhas 258-308)

**Status:** ✅ Implementado, mas ainda não resolve completamente (VALUE: 0 ainda)

---

### 2. Melhoria da Regra R-H* (HEADER)
**Problema:** Regra muito permissiva, classificando quase tudo como HEADER.

**Solução:** 
- Aumentado quantil de 90 para 95 (mais restritivo)
- Adicionada verificação de texto curto (≤5 tokens)
- Adicionada verificação para não aceitar blocks com dígitos (valores numéricos)

**Arquivo:** `src/graph/roles_rules.py` (linhas 105-125)

**Status:** ✅ Implementado, mas propagação por estilo ainda sobrescreve

---

### 3. Melhoria da Regra R-V* (VALUE)
**Problema:** Regra muito restritiva, não identificava valores que não estão diretamente conectados a LABELs.

**Solução:**
- Adicionada verificação de neighbors em ambas direções (left/up e right/down)
- Adicionado fallback para campos com tipo forte (number, date, money, alphanum_code)

**Arquivo:** `src/graph/roles_rules.py` (linhas 182-241)

**Status:** ✅ Implementado

---

## 🔴 Problemas Identificados que Ainda Precisam Correção

### 1. Propagação por Estilo Muito Agressiva
**Problema:** `propagate_role_by_style` está sobrescrevendo roles individuais corretos. Se um componente tem um HEADER, todos os blocks do componente se tornam HEADER, mesmo que alguns tenham sido identificados como VALUE individualmente.

**Evidência:** 
- Block "JOANA D'ARC" (deveria ser VALUE) → HEADER
- Block "101943\nPR\nCONSELHO SECCIONAL - PARANÁ" (deveria ser VALUE) → HEADER

**Solução Necessária:**
- Ajustar prioridade na propagação
- Não sobrescrever roles individuais se foram atribuídos com alta confiança
- Permitir que VALUES sejam preservados mesmo em componentes com HEADERs

**Arquivo:** `src/graph/roles_rules.py` - `propagate_role_by_style`

**Prioridade:** 🔴 ALTA

---

### 2. `find_label_value_pairs` Retornando 0 Pairs
**Problema:** A função `find_label_value_pairs` está retornando 0 pairs para todos os campos, mesmo quando há LABELs identificados.

**Evidência:** Debug mostra:
```
[10] Finding label-value pairs...
  ✓ Label-value pairs found
    nome: 0 pairs
    inscricao: 0 pairs
    seccional: 0 pairs
    ...
```

**Possíveis Causas:**
- `find_label_value_pairs` pode não estar encontrando LABELs corretos
- Busca ortogonal pode não estar funcionando
- Type-gate pode estar rejeitando valores válidos
- Roles podem não estar sendo passados corretamente

**Solução Necessária:**
- Verificar se `find_label_value_pairs` está recebendo os roles corretos
- Verificar se a busca ortogonal está encontrando caminhos
- Adicionar logs de debug para entender por que não encontra pairs

**Arquivo:** `src/matching/label_value.py`

**Prioridade:** 🔴 ALTA

---

### 3. Candidate Sets Vazios para Alguns Campos
**Problema:** Alguns campos críticos não têm candidatos gerados:
- `inscricao`: 0 candidates
- `seccional`: 0 candidates

**Evidência:** Debug mostra:
```
[9] Building candidate sets...
  ✓ Candidate sets built: 52 total candidates
    nome: 14 candidates
    inscricao: 0 candidates  ← PROBLEMA
    seccional: 0 candidates  ← PROBLEMA
```

**Possíveis Causas:**
- Labels não estão sendo encontrados para esses campos
- Estratégias de geração de candidatos não estão funcionando
- Type-gate pode estar rejeitando candidatos válidos

**Solução Necessária:**
- Verificar `_find_label_blocks_lightweight` para esses campos
- Verificar estratégias de geração (position-based, pattern-based, etc.)
- Adicionar fallback mais robusto

**Arquivo:** `src/matching/candidates.py`

**Prioridade:** 🟡 MÉDIA

---

## 📊 Resultados Atuais

- **Precisão:** 43.24% (sem melhoria após correções)
- **Campos Corretos:** 16/37
- **Campos com Problema:** 21/37

**Campos que Funcionam:** categoria, telefone_profissional (quando null), pesquisa_por, pesquisa_tipo, produto, quantidade_parcelas, tipo_de_operacao, tipo_de_sistema, total_de_parcelas, valor_parcela, cidade

**Campos que Não Funcionam:** nome, inscricao, seccional, situacao, data_base, data_verncimento, data_referencia, endereco_profissional (parcial)

---

## 🎯 Próximas Ações Prioritárias

1. **Corrigir propagação por estilo** (Prioridade ALTA)
   - Ajustar `propagate_role_by_style` para não sobrescrever roles individuais
   - Permitir mistura de roles em componentes quando apropriado

2. **Corrigir `find_label_value_pairs`** (Prioridade ALTA)
   - Adicionar logs de debug
   - Verificar se roles estão sendo passados corretamente
   - Verificar se busca ortogonal está funcionando

3. **Melhorar geração de candidatos** (Prioridade MÉDIA)
   - Adicionar mais estratégias de fallback
   - Melhorar matching de labels

---

## 📝 Notas

- As correções implementadas são um passo na direção certa, mas não resolveram completamente porque outros problemas estão mascarando os resultados
- A propagação por estilo parece ser o problema mais crítico agora
- `find_label_value_pairs` precisa ser investigado mais profundamente

