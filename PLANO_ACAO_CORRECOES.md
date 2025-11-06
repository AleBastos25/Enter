# Plano de Ação - Correções de Extração e Formato de Output

## 📊 Análise dos Problemas

**Taxa de acerto atual: 18.9% (7/37 campos corretos)**

### Problemas Identificados

#### 1. **Formato de Output** (CRÍTICO)
- **Problema**: O formato gerado não corresponde ao esperado
  - **Atual**: `{"folder_path": "...", "results": [{"label": "...", "results": {"field": {"value": ..., "confidence": ..., "source": ..., "trace": {...}}}}]}`
  - **Esperado**: `[{"pdf": "...", "label": "...", "result": {"field": value}}]`
- **Impacto**: Formato incompatível com expectativa do usuário
- **Prioridade**: 🔴 ALTA

#### 2. **Campos Não Extraídos (null)** (CRÍTICO)
- **`inscricao`**: null em `oab_1.pdf` e `oab_2.pdf` (mas OK em `oab_3.pdf`)
- **`categoria`**: null em todos os PDFs OAB (deveria ser "SUPLEMENTAR")
- **`situacao`**: null em todos os PDFs OAB (deveria ser "SITUAÇÃO REGULAR")
- **`seccional`**: null em `oab_3.pdf` (mas OK nos outros)
- **`pesquisa_por`**: null (deveria ser "CLIENTE")
- **`pesquisa_tipo`**: null (deveria ser "CPF")
- **`valor_parcela`**: null (deveria ser "2372.64")
- **`cidade`**: null (deveria ser "Mozarlândia")
- **Impacto**: Muitos campos importantes não sendo extraídos
- **Prioridade**: 🔴 ALTA

#### 3. **Valores Incorretos/Incompletos** (CRÍTICO)
- **`subsecao`**: Extrai label "Inscrição"/"Subseção" em vez do valor real "CONSELHO SECCIONAL - PARANÁ"
- **`endereco_profissional`**: Contém prefixos "Profissional" ou "Endereço Profissional" que não deveriam estar
- **`sistema` em tela_sistema_2.pdf**: Contém texto extra "VIr. Parc. 2.372,64" (deveria ser só "CONSIGNADO")
- **Impacto**: Valores poluídos ou incorretos
- **Prioridade**: 🔴 ALTA

#### 4. **Extrações Trocadas/Confusas** (CRÍTICO)
- **`data_base` e `data_verncimento`**: Valores incorretos (extraindo mesma data)
- **`produto`**: Extrai data "12/10/2025" quando deveria ser null
- **`sistema` em tela_sistema_1.pdf**: Extrai data "12/10/2025" quando deveria ser "CONSIGNADO"
- **`selecao_de_parcelas`**: Extrai data "2021-02-04" quando deveria ser null
- **Impacto**: Campos extraindo valores de outros campos
- **Prioridade**: 🔴 ALTA

---

## 🎯 Plano de Ação

### Fase 1: Formato de Output (PRIORIDADE MÁXIMA)

#### Tarefa 1.1: Converter formato de output no `batch_process.py`
- **Arquivo**: `scripts/batch_process.py`
- **Ação**: Adicionar função `_convert_to_canonical_format()` que:
  - Recebe o resultado do pipeline
  - Extrai apenas `value` de cada campo (ignora `confidence`, `source`, `trace`)
  - Converte para formato `[{"pdf": "...", "label": "...", "result": {"field": value}}]`
- **Critério de Aceite**: Output gerado corresponde exatamente ao formato esperado
- **Complexidade**: 🟢 BAIXA (transformação de dados)

### Fase 2: Correções de Extração (ABSTRAÇÃO GENÉRICA)

#### Tarefa 2.1: Melhorar matching de campos numéricos (`inscricao`)
- **Problema**: `inscricao` não encontrado em alguns PDFs
- **Análise Necessária**: 
  - Verificar por que funciona em `oab_3.pdf` mas não em `oab_1.pdf` e `oab_2.pdf`
  - Verificar se label blocks estão sendo encontrados
  - Verificar se neighborhood está funcionando
- **Solução Genérica**:
  - Melhorar detecção de labels para campos numéricos (ex: "Inscrição Nº" vs "Inscrição")
  - Expandir estratégias de neighborhood para campos que podem estar abaixo do label
  - Melhorar type_gate para aceitar números mesmo com formatação
- **Arquivos**: `src/matching/matcher.py`, `src/validation/patterns.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.2: Melhorar matching de campos enum (`categoria`, `situacao`)
- **Problema**: Campos enum não estão sendo extraídos
- **Análise Necessária**:
  - Verificar se `enum_options` estão sendo corretamente inferidos do schema
  - Verificar se `global_enum_scan` está funcionando
  - Verificar se matching case-insensitive está funcionando
- **Solução Genérica**:
  - Garantir que `global_enum_scan` procura por valores enum em todos os blocos (não apenas próximo ao label)
  - Melhorar matching case-insensitive e accent-insensitive para enums
  - Adicionar fallback: se não encontrar label, procurar valor enum diretamente
  - Melhorar detecção de valores enum mesmo quando não há label explícito
- **Arquivos**: `src/matching/matcher.py`, `src/core/schema.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.3: Corrigir extração de `subsecao` (extraindo label em vez de valor)
- **Problema**: Extrai "Inscrição"/"Subseção" (label) em vez do valor real
- **Análise Necessária**:
  - Verificar por que `semantic_direct` está pegando o bloco errado
  - Verificar se `same_block` está extraindo label em vez de valor
- **Solução Genérica**:
  - Melhorar `_decide_keep_label()` para rejeitar casos onde o texto é só label
  - Melhorar filtro de "common_labels" em `extract_from_candidate()`
  - Adicionar verificação: se `text_window` é só label (sem valor após), buscar próximo bloco
  - Melhorar detecção de quando um bloco contém label+valor vs só label
- **Arquivos**: `src/extraction/text_extractor.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.4: Remover prefixos de labels de valores extraídos (`endereco_profissional`)
- **Problema**: Valores contêm prefixos "Profissional", "Endereço Profissional"
- **Análise Necessária**:
  - Verificar se `keep_label` está retornando `True` quando deveria ser `False`
  - Verificar se há lógica para remover labels conhecidos
- **Solução Genérica**:
  - Melhorar `_decide_keep_label()` para detectar quando label é prefixo comum
  - Adicionar remoção de prefixos conhecidos após extração (genérico, baseado em pattern)
  - Melhorar `_split_by_label()` para funcionar melhor com labels longos
  - Adicionar detecção de quando texto começa com label conhecido e remover
- **Arquivos**: `src/extraction/text_extractor.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.5: Extrair apenas valor principal de campos com múltiplos valores (`sistema` em tela_sistema_2)
- **Problema**: `sistema` extrai "CONSIGNADO VIr. Parc. 2.372,64" em vez de só "CONSIGNADO"
- **Análise Necessária**:
  - Verificar se o bloco contém múltiplos valores concatenados
  - Verificar se há separadores que podem ser usados para extrair apenas o primeiro valor
- **Solução Genérica**:
  - Adicionar lógica para detectar quando `text_window` contém múltiplos valores (baseado em pattern)
  - Para campos enum/text, extrair apenas primeira palavra/palavras até encontrar separador forte
  - Melhorar parsing estruturado para detectar quando há múltiplos campos no mesmo bloco
- **Arquivos**: `src/extraction/text_extractor.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.6: Corrigir extrações trocadas entre campos (`data_base`/`data_verncimento`, `produto`/`sistema`)
- **Problema**: Campos extraindo valores de outros campos
- **Análise Necessária**:
  - Verificar se múltiplos campos estão competindo pelo mesmo bloco
  - Verificar se deduplication está funcionando corretamente
  - Verificar se matching está priorizando campos errados
- **Solução Genérica**:
  - Melhorar deduplication: se dois campos extraem o mesmo valor, verificar qual é mais compatível com o tipo
  - Adicionar validação de tipo mais rigorosa antes de aceitar candidato
  - Melhorar `used_blocks` tracking: não permitir que campos diferentes usem o mesmo bloco se tipos são incompatíveis
  - Adicionar verificação de plausibilidade: se valor não faz sentido para o tipo do campo, rejeitar
- **Arquivos**: `src/core/pipeline.py`, `src/extraction/text_extractor.py`
- **Complexidade**: 🟡 MÉDIA

#### Tarefa 2.7: Melhorar extração de campos específicos (`valor_parcela`, `cidade`, `pesquisa_por`, `pesquisa_tipo`)
- **Problema**: Campos não sendo encontrados
- **Análise Necessária**:
  - Para cada campo, verificar:
    - Se labels estão sendo encontrados
    - Se valores estão presentes no PDF
    - Se matching está funcionando
- **Solução Genérica**:
  - Melhorar matching para campos que podem não ter labels explícitos
  - Adicionar fallback: procurar valores por tipo (ex: `valor_parcela` = procurar money, `cidade` = procurar text com letras, `pesquisa_por` = procurar enum)
  - Melhorar `position_hint` matching para campos com hints de posição
  - Adicionar estratégia de "type-based search" quando não há label
- **Arquivos**: `src/matching/matcher.py`
- **Complexidade**: 🟡 MÉDIA

---

## 🔧 Implementação (Ordem de Prioridade)

### Sprint 1: Formato e Correções Críticas
1. ✅ **Tarefa 1.1**: Converter formato de output
2. ✅ **Tarefa 2.2**: Melhorar matching de campos enum (`categoria`, `situacao`)
3. ✅ **Tarefa 2.3**: Corrigir extração de label em vez de valor (`subsecao`)

### Sprint 2: Limpeza e Deduplication
4. ✅ **Tarefa 2.4**: Remover prefixos de labels
5. ✅ **Tarefa 2.6**: Corrigir extrações trocadas
6. ✅ **Tarefa 2.5**: Extrair apenas valor principal

### Sprint 3: Melhorias de Matching
7. ✅ **Tarefa 2.1**: Melhorar matching de campos numéricos
8. ✅ **Tarefa 2.7**: Melhorar extração de campos específicos

---

## 📝 Observações Importantes

1. **Abstração Genérica**: Todas as correções devem ser genéricas, não específicas para os PDFs de exemplo
2. **Pattern-based**: Usar pattern detection genérico sempre que possível
3. **Type-aware**: Validação de tipo deve ser rigorosa para evitar extrações incorretas
4. **Testes**: Cada correção deve ser testada com múltiplos PDFs para garantir que não quebra outros casos

---

## 🎯 Critérios de Sucesso

- **Formato de Output**: 100% compatível com formato esperado
- **Taxa de Acerto**: > 80% dos campos corretos
- **Campos Críticos**: `inscricao`, `categoria`, `situacao` devem ser extraídos corretamente em todos os PDFs
- **Qualidade**: Valores não devem conter labels ou texto extra
- **Robustez**: Soluções devem funcionar para PDFs genéricos, não apenas os de exemplo

