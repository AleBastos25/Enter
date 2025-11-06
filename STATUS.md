# Document Extraction System - Especificação Funcional v3.0

> **Última atualização:** Janeiro 2025  
> **Versão:** 3.0 (Grafo Ortogonal, Assinaturas de Estilo, Seleção por Pareto, LLM como Chooser)
> **Status:** Especificação funcional completa - pronto para implementação

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Componentes Principais](#componentes-principais)
4. [Pipeline Detalhado](#pipeline-detalhado)
5. [Provas e Audit Trail](#provas-e-audit-trail)
6. [Memória e Invariantes](#memória-e-invariantes)
7. [Configurações](#configurações)
8. [Por que Esta Abordagem](#por-que-esta-abordagem)

---

## 🎯 Visão Geral

**Em uma frase:** Dado um PDF e um schema `{chave: descrição}`, o sistema transforma o PDF em um **grafo ortogonal de unidades de texto estilisticamente homogêneas**, classifica cada unidade como **HEADER / LABEL / VALUE** por regras, emparelha **LABEL→VALUE** por **busca ortogonal + filtro de Pareto**, resolve empates com **tie-breakers determinísticos**, **usa LLM somente para escolher** entre poucos remanescentes e **aprende invariantes** (léxicos, direções, offsets, estilos) para reduzir chamadas futuras. Tudo com **provas/audit trail** reproduzíveis, sem pontuações arbitrárias.

### Princípios Fundamentais

1. **Determinismo Primeiro**: Regras claras, sem "scores" ad hoc
2. **Grafo Ortogonal**: Estrutura espacial com arestas ↑↓←→ (sem diagonais)
3. **Assinaturas de Estilo**: Classificação por estilo homogêneo, não por posição
4. **Seleção por Pareto**: Dominância parcial em vez de pesos arbitrários
5. **LLM como Chooser**: Modelo escolhe apenas entre poucos candidatos, não extrai do zero
6. **Memória com Temperatura**: Aprende invariantes que realmente generalizam, reduz chamadas LLM progressivamente
7. **Provas Auditáveis**: Cada decisão tem justificativa reproduzível

---

## 🏗️ Arquitetura

### Entradas e Saídas

**Entrada:**
- PDF (1+ páginas)
- `DocumentLabel` (tipo do documento, ex.: `"carteira_oab"`)
- `ExtractionSchema` (mapa `{field_key: field_description}`)
- Configuração (limites de tempo/chamadas LLM; bins de estilo; parâmetros robustos de espaçamento)

**Saída:**
- JSON com, para cada `field_key`:
  - `value` (string normalizada ou `null`)
  - `source`: `"graph"` | `"llm-chooser"` | `"none"`
  - `confidence`: omitido ou rótulo discreto `"deterministic"`/`"chosen"`/`"none"`
  - `proof` (provas auditáveis: nós envolvidos, regras aplicadas, direções, pareto, tie-breakers, memória usada, se LLM foi chamada, justificativa da LLM)

### Pipeline de Alto Nível

```
PDF → Extração de Text Units (TUs)
  → Assinatura de Estilo (S(TU))
  → Modelo de Espaçamento (τ_same_line, τ_same_column, τ_multiline)
  → Grafo Ortogonal G = (V,E) com arestas ↑↓←→
  → Classificação por Papéis (HEADER / LABEL / VALUE)
  → Componentes de Estilo (propagação de papéis)
  → Léxico por Campo (âncoras do schema)
  → Busca de Valores por Label (emparelhamento ortogonal)
  → Seleção por Pareto (4 critérios equivalentes)
  → Tie-breakers Determinísticos
  → LLM Chooser (se necessário, condicionado por temperatura)
  → Multilinha (valores compostos)
  → Type-gate Genérico
  → Normalização e Sanitização
  → Fusão entre Páginas
  → Memória (aprendizado de invariantes)
  → JSON Final com Provas
```

---

## 🔧 Componentes Principais

### 1. Text Units (TUs)

**Definição:** Blocos atômicos de texto com estilo/posicionamento coeso.

**Atributos:**
- Bounding box normalizado `[0..1]×[0..1]` por página
- Texto bruto (sem ZW-chars/de-hyphenation)
- Metadados de estilo: `font_family`, `font_size`, `bold/italic`, `color`
- Dicas de alinhamento (center/left/right) por linha

**Segmentação:** TU ≠ token. TU é o bloco mínimo com estilo/posicionamento coeso.

### 2. Assinatura de Estilo `S(TU)`

**Componentes:**
- `font_family_id` (clusterização simples)
- `font_size_bin` (bins por quantis, não número absoluto)
- `is_bold`, `is_italic`
- `color_cluster` (se disponível)
- `caps_ratio_bin` (percentual de maiúsculas em bins)
- `letter_spacing_bin` (gap médio intra-token em bins)

**Regra:** TUs com **S iguais** pertencem à **mesma classe de estilo**.

### 3. Modelo de Espaçamento (Limiares Derivados do Documento)

**Sem números mágicos:** Limiares aprendidos por estatística resistente (mediana + MAD):

- `τ_same_line`: limite para dizer que dois TUs estão na **mesma linha**
- `τ_same_column`: limite para dizer que dois TUs estão na **mesma coluna**
- `τ_multiline`: limite para agregar linhas **multilinha** de um mesmo valor

**Adaptação:** Limiares variam por página/seção quando necessário.

### 4. Grafo Ortogonal `G = (V,E)`

**Nós:** Todos os TUs.

**Arestas Ortogonais:** ↑ ↓ ← → conectam TUs adjacentes se:
- Sobreposição no eixo ortogonal suficiente (ex.: 60%)
- Distâncias respeitam `τ_same_line` (horiz.) ou `τ_same_column` (vert.)

**Sem diagonais.** Um TU pode ter múltiplas arestas ↓ (ex.: rótulo ocupando a largura de várias linhas abaixo).

### 5. Componentes de Estilo e Papéis

**Classificação Inicial por Regras:**

- **HEADER** se:
  - Tamanho muito alto em relação à seção
  - Centralizado e isolado
  - Pai de grade/tabela visual

- **LABEL** se:
  - Termina em separador típico (`:`, `—`, `.` curto)
  - É curto (≤3 tokens, sem dígitos)
  - Possui vizinho ortogonal que pareça um VALUE (vide type-gate)
  - Contém âncora exata do léxico do schema

- **VALUE** se:
  - Passa o **type-gate genérico** do campo em foco (ou "texto" sem restrições fortes)
  - **Não** termina com separador de label

**Propagação por Estilo:**
- Conectamos entre si TUs **adjacentes** (↑↓←→) com **S idêntica**, criando **componentes de estilo**
- Um componente recebe **um único papel** por prioridade **fixa**: `HEADER > LABEL > VALUE`
- **Regra adicional**: se um TU é marcado como VALUE **mas termina com separador típico**, o componente volta a ser LABEL

**Efeito:** "Se dois TUs têm mesmo estilo, têm o mesmo papel" (desde que conectados ortogonalmente).

### 6. Léxico por Campo

Para cada campo `{chave: descrição}` formamos um **léxico exato** (strings):

- `chave` (variações simples: `nº`, `no`, `num`, com/sem `:`)
- Tokens curtos da `descrição` que não sejam stopwords
- *Opcional*: opções explícitas (para `enum`), exatamente como strings alvo

**Sem similaridade textual** nesta fase: só **pertença exata** ao conjunto.

---

## 🔄 Pipeline Detalhado

### Etapa 1: Extração de Text Units (TUs) e Pré-processamento

1. Renderizamos o PDF em **blocos atômicos** de texto (TUs)
2. Preservamos bounding box, texto bruto, metadados de estilo, dicas de alinhamento
3. Segmentação robusta: TU ≠ token

### Etapa 2: Assinatura de Estilo

Para cada TU calculamos `S(TU)` (font_family_id, font_size_bin, is_bold, is_italic, color_cluster, caps_ratio_bin, letter_spacing_bin).

### Etapa 3: Modelo de Espaçamento

Medimos distribuições de gaps e definimos limiares `τ_same_line`, `τ_same_column`, `τ_multiline` por estatística resistente (mediana + MAD).

### Etapa 4: Grafo Ortogonal

Construímos `G = (V,E)` onde:
- V = todos os TUs
- E = arestas ↑↓←→ conectando TUs adjacentes ortogonalmente

### Etapa 5: Componentes de Estilo e Papéis

1. Classificação inicial por regras (HEADER / LABEL / VALUE)
2. Componentes por estilo (propagação): conectamos TUs adjacentes com S idêntica
3. Um componente recebe um único papel por prioridade fixa: `HEADER > LABEL > VALUE`

### Etapa 6: Léxico por Campo

Para cada campo formamos léxico exato (strings) a partir da chave, descrição e opções explícitas (enum).

### Etapa 7: Busca de Valores por Label (Emparelhamento Ortogonal)

Para cada campo:

1. **Seeds de LABEL**, em ordem:
   - **L-A**: LABELs que **contêm** âncora exata do léxico do campo
   - **L-B**: LABELs canônicos (pelas regras) **sem** âncora
   - **L-C**: fallback raro (LABELs genéricos curtos sem dígitos)

2. Para cada label-seed, lançamos uma **busca ortogonal curta** em **ordem de direção fixa**:
   - Ordem: `→` **depois** `↓`, **depois** `↑`, **por fim** `←`
   - Coletamos candidatos a VALUE que:
     * Respeitam **type-gate** do campo
     * **Não** têm o mesmo estilo do label
     * **Não** violam ordem natural (no-crossing com outros pares já feitos)

3. **Montamos o conjunto C de candidatos** (poucos) e aplicamos **Pareto** (ver Etapa 8)

4. **Se sobrar 1**: seleciona determinística e commita o par `LABEL→VALUE`
   **Se sobrarem >1**: aplica **tie-breakers determinísticos** (ver Etapa 9)
   **Se persistir empate real**: chama **LLM chooser** (ver Etapa 11)

### Etapa 8: Seleção por Pareto (sem pesos)

Em vez de "scores", usamos um **domínio parcial** com **4 critérios equivalentes**:

- **C1 Estrutural**: menos saltos (hops), preferência por **mesma linha/mesma coluna**, sem cruzar a ordem natural
- **C2 Estilo**: estilo **diferente do LABEL** e **consistência** com valores já encontrados desse mesmo **campo** (se existirem)
- **C3 Lexical**: `enum` → membro exato do conjunto; `texto` → não termina com separador e tem ≥4 letras
- **C4 Tipo**: passa o **type-gate** do campo (date-like, money-like, dígitos, e-mail, etc.)

Um candidato **A domina B** se A não é pior em nenhum critério e é melhor em pelo menos um. Mantemos **apenas** os **não-dominados**.

### Etapa 9: Tie-breakers Determinísticos

Se, após Pareto, ainda houver vários:

1. Direção preferida: `→` > `↓` > `↑` > `←`
2. Menos **saltos** (hops)
3. **Distância Manhattan** menor (Δx+Δy)
4. Menor `line_index` (ordem de leitura)
5. Sem inversões ("no-crossing") quando houver múltiplos pares em coluna/linha

Persistindo empate real após todos, delegamos à **LLM chooser**.

### Etapa 10: Campos "sem label" (ex.: `nome`)

Quando a chave/descrição **não indicam** âncoras lexicais viáveis e **não há LABEL confiável** vizinho:

- Procuramos **candidatos canônicos**:
  * Primeiro(s) TU(s) **em top-left** da seção/página (se a descrição sugere posição)
  * Que sejam **VALUE de texto** (≥4 letras, sem dígitos dominantes, não terminam com separador)
  * **Sem** LABEL em (← ou ↑) a 1 salto
- Aplicamos Pareto e tie-breakers. Se restarem >1, **LLM chooser**.

### Etapa 11: Multilinha (valores compostos)

Se o VALUE escolhido possui filhos ↓ com **mesmo estilo** e `dist_y ≤ τ_multiline`, concatenamos até 2–3 linhas ou **até esbarrar em** LABEL/HEADER. Normalizamos espaços; nunca carregamos os separadores de label.

### Etapa 12: Type-gate Genérico (não específico de país)

- `date_like`: padrões com separadores (dd/mm/aaaa, aaaa-mm-dd, etc.) **sem** assumir idioma/país
- `money_like`: número com separadores decimais/agrupamento (aceita `,` ou `.` de forma tolerante)
- `digits_only`/`digits_with_separators`: para IDs genéricos
- `alphanumeric`: misto letra+dígito
- `text`: ≥4 letras, sem predominância numérica

**Nada de validadores "por país"; tudo genérico.** Formas novas aprendidas (value-shapes) podem ser registradas na memória.

### Etapa 13: LLM **apenas** como "chooser"

**Quando:** somente se, após Pareto + tie-breakers, sobraram **>1** candidatos viáveis **ou** em campos sem label com múltiplos "canônicos".

**Entrada compacta:**
- `DocumentLabel`, `field_key`, `field_desc`, `enum_options?`
- Até **3** candidatos com:
  * `label_text?` (se existir)
  * `value_text`
  * `direção` e **vizinhos** (±1 TU) para contexto
  * Resumos de estilo (bold? size-bin?)

**Pergunta:** "Escolha **um índice** (0..k-1) ou **nenhum**; explique em 1 frase."

**Saída:** `{pick: idx|-1, why: "..."}`; revalidamos com **type-gate**.

**Cache** por hash do subgrafo do empate.

**Orçamento** condicionado à **temperatura do documento** (ver Memória).

### Etapa 14: Fusão entre Páginas

- Scaneamos páginas em ordem
- Por default, aceitamos o **primeiro** par válido do campo encontrado **sem** conflito
- Se o schema disser que o valor costuma estar em regiões específicas (ex.: "canto inferior esquerdo"), isso vira **position hint**: tentamos primeiro o subgrafo daquela região por página

### Etapa 15: Normalização e Sanitização

- Datas → ISO quando possível (se parse claro); senão, devolvemos a string crua aprovada pelo type-gate
- Valores multilinha → join com espaço único
- Remoção de "label:" residual do início de value-text

### Etapa 16: Falhas e Abstention

- Se nenhum candidato passar no type-gate **e** não houver LABEL confiável → `value: null`, `source: "none"`, com `proof` do motivo
- A LLM pode devolver `-1` ("nenhum"); nesse caso mantemos `null` e registramos prova e cache

---

## 📋 Provas e Audit Trail

Para cada campo extraído, o `proof` contém:

### `label_component`
- IDs dos nós
- Assinatura de estilo
- Regras aplicadas (ex.: `LABEL:R-L1`, `ANCHOR:lexicon`)

### `value_component`
- IDs dos nós
- Regras de VALUE aplicadas (`R-V1(type)`, `R-V2(vizinhança)`)

### `search`
- Ordem de direções tentadas
- Direção escolhida
- Número de saltos (hops)
- Verificação "no-crossing"

### `pareto`
- Número de candidatos inicial
- Número de candidatos após Pareto
- Por que os restantes não foram dominados

### `tie_breakers`
- O que decidiu (ex.: mesma linha vs. menor distância)
- Ordem de aplicação dos tie-breakers

### `llm_used`
- `false` ou detalhes `{pick, why, cache_key}`

### `memory`
- Invariantes usados (ex.: "direção preferida do campo = →")
- Temperatura do documento no momento da extração

**Tudo determinístico, reproduzível.** Rodadas repetidas produzem o mesmo resultado.

---

## 🧠 Memória e Invariantes

### O que a Memória Guarda

O sistema **não** guarda pesos. Guarda **invariantes** que realmente generalizam:

1. **Vocabulário de LABEL** por campo (strings vistas de sucesso)
2. **Direções** bem-sucedidas por campo (frequência de `→, ↓, ↑, ←`)
3. **Offsets discretos** (saltos típicos) LABEL→VALUE
4. **Assinaturas de estilo** dominantes (bins) de LABEL/HEADER/VALUE por campo
5. **Value-shapes** bem-sucedidos (ex.: "6 dígitos", "AA-9999", "YYYY-MM-DD") **sem** amarrar a um país

### Aprendizado

Aprendemos **apenas** quando a extração veio de caminho **determinístico** ou de **LLM chooser** cujo resultado passou no **type-gate**.

### Temperatura do Documento (frio ↔ quente)

**T ∈ [0,1]** mede quão "quente" o documento está, i.e., **quantos invariantes se repetem**:

```
T = (# de invariantes satisfeitos) / (# invariantes aplicáveis)
```

**Uso prático:**

- **T ≥ 0.8**: não chamamos LLM; só regras+memória
- **0.4 ≤ T < 0.8**: no máximo **1** chamada de chooser
- **T < 0.4**: até **2–3** chamadas (documento realmente novo)

**Efeito:** Documentos similares (mesmo `DocumentLabel`) reduzem chamadas LLM progressivamente.

---

## ⚙️ Configurações

### Limites de Complexidade

- **Construção de grafo**: O(N) com vizinhança local (N = nº de TUs)
- **Busca por campo**: BFS ortogonal com **limite baixo de saltos**; conjunto de candidatos pequeno (k ≤ ~5)
- **Chamada à LLM**: **somente** quando necessário e com payload mínimo (≤ 3 candidatos)

### Parâmetros Configuráveis

**Espaçamento:**
- Percentis para mediana + MAD (ex.: 50º percentil para mediana, 75º para MAD)
- Threshold mínimo/máximo para `τ_same_line`, `τ_same_column`, `τ_multiline`

**Estilo:**
- Número de bins para `font_size_bin`, `caps_ratio_bin`, `letter_spacing_bin`
- Tolerância para clusterização de `font_family_id` e `color_cluster`

**Grafo:**
- Limite de sobreposição ortogonal (ex.: 60%)
- Limite máximo de saltos (hops) na busca

**Pareto:**
- Critérios ativos (C1, C2, C3, C4)
- Pesos relativos (se necessário para desempate secundário)

**LLM:**
- Orçamento máximo por documento (número de chamadas)
- Tamanho máximo do payload (número de candidatos)
- Cache TTL (tempo de vida do cache)

**Memória:**
- Limite de invariantes por campo
- Limite de value-shapes por tipo
- Threshold de temperatura para redução de chamadas LLM

---

## 🎯 Por que Esta Abordagem

### 1. Sem "Scores" Ad Hoc

Seleção por **Pareto** e **tie-breakers lexicográficos** eliminam pesos arbitrários. Cada decisão tem justificativa clara.

### 2. Generaliza

Baseia-se em **layout, estilo, ortogonalidade e tipos genéricos**, não em regras específicas de país/idioma. Funciona para qualquer PDF com estrutura similar.

### 3. Aprende de Verdade

Guarda **invariantes** (lexicon visto, direção, offset, estilo, shape) que **reduzem** chamadas futuras sem engessar. A memória não é um "cache" de exemplos, mas um aprendizado de padrões.

### 4. LLM com Inteligência

Só **escolhe** entre poucos candidatos, **cacheada**, condicionada pela **temperatura** (frio/quente). O LLM não precisa "adivinhar" do zero, apenas desempatar entre opções claras.

### 5. Determinismo e Auditabilidade

Cada decisão tem **provas**; rodadas repetidas produzem o mesmo resultado. O `proof` permite rastrear exatamente por que cada valor foi extraído.

### 6. Funciona no Primeiro PDF

Regras de papel + grafo + type-gate já dão extrações corretas na maioria; a LLM só desempata onde um humano também hesitaria.

### 7. Sem Viés de "Nearby Down-Right"

O grafo tem **↑↓←→** e a preferência de direção é **regra explícita**, não suposição. A busca ortogonal explora todas as direções de forma sistemática.

### 8. Complexidade Controlada

Busca ortogonal com limite de saltos garante O(N) por campo. LLM só é chamado quando absolutamente necessário, com payload mínimo.

---

## 📊 Comparação com Versão Anterior

### Mudanças Principais

| Aspecto | v2.0 (Anterior) | v3.0 (Nova Especificação) |
|---------|----------------|---------------------------|
| **Matching** | Score tuple lexicográfico | Seleção por Pareto + tie-breakers |
| **Grafo** | Arestas direcionais (same_line, same_col) | Grafo ortogonal puro (↑↓←→) |
| **Estilo** | Style z-score | Assinaturas de estilo (bins) |
| **Classificação** | Implícita via matching | Explícita por regras (HEADER/LABEL/VALUE) |
| **LLM** | Fallback para extração | Apenas chooser entre candidatos |
| **Memória** | StrategyStats, pesos | Invariantes (lexicon, direção, offset, estilo, shape) |
| **Temperatura** | Não existia | Mede "quenteza" do documento, controla chamadas LLM |
| **Provas** | Trace básico | Audit trail completo e reproduzível |

### Melhorias

1. **Eliminação de pesos arbitrários**: Pareto substitui scores
2. **Classificação explícita**: HEADER/LABEL/VALUE por regras claras
3. **LLM mais eficiente**: Apenas chooser, não extração do zero
4. **Memória mais robusta**: Invariantes que realmente generalizam
5. **Temperatura**: Reduz chamadas LLM progressivamente
6. **Provas completas**: Audit trail reproduzível

---

## 🚀 Próximos Passos

### Implementação

1. **Fase 1: Grafo Ortogonal**
   - Implementar construção de grafo com arestas ↑↓←→
   - Implementar modelo de espaçamento (limiares derivados do documento)

2. **Fase 2: Assinaturas de Estilo**
   - Implementar cálculo de `S(TU)`
   - Implementar componentes de estilo e propagação de papéis

3. **Fase 3: Classificação por Regras**
   - Implementar regras para HEADER/LABEL/VALUE
   - Implementar léxico por campo

4. **Fase 4: Busca e Seleção**
   - Implementar busca ortogonal por label
   - Implementar seleção por Pareto
   - Implementar tie-breakers determinísticos

5. **Fase 5: LLM Chooser**
   - Implementar LLM como chooser (não extração)
   - Implementar cache de chooser

6. **Fase 6: Memória e Temperatura**
   - Implementar aprendizado de invariantes
   - Implementar cálculo de temperatura
   - Implementar controle de chamadas LLM por temperatura

7. **Fase 7: Provas e Audit Trail**
   - Implementar `proof` completo para cada campo
   - Garantir determinismo e reprodutibilidade

---

## 📚 Referências

- **Design Document**: `context.md` (blueprint completo)
- **Contracts**: `contracts.md` (interfaces e modelos)
- **Análise de Erros**: `CAUSAS_RAIZ_ERROS.md` (problemas identificados na versão anterior)

---

**Status:** ✅ Especificação funcional completa v3.0 - pronto para implementação. Sistema completamente determinístico, baseado em regras claras, grafo ortogonal, assinaturas de estilo, seleção por Pareto, LLM como chooser, memória com temperatura, e provas auditáveis.
