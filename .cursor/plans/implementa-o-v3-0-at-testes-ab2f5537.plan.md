<!-- ab2f5537-610f-4446-8920-57e4958a67d6 087239de-e9fb-473a-a2b8-37a6b3da2e35 -->
# Plano de Ação: Implementação v3.0 até Testes com PDFs

## Objetivo

Implementar mudanças mínimas necessárias para alinhar com v3.0, mantendo compatibilidade com visualização HTML, e testar com todos os PDFs de `data/samples/`.

## Estratégia

Implementação incremental focada no essencial:

1. Adicionar metadados de estilo aos nós do grafo (sem quebrar visualização)
2. Integrar classificação de papéis básica
3. Conectar com pipeline existente
4. Testar com todos os PDFs

---

## Etapa 1: Enriquecer nós do grafo com metadados de estilo

### 1.1 Atualizar `scripts/build_token_graph.py`

**Arquivo:** `scripts/build_token_graph.py`

**Mudanças:**

- Adicionar cálculo de `StyleSignature` para cada token usando `src/layout/style_signature.py`
- Adicionar campos aos nós: `style_signature`, `role` (inicialmente None), `italic`, `color`, `line_index`, `component_id`
- Manter estrutura atual para compatibilidade com `visualize_token_graph.py`

**Código a adicionar:**

```python
# No início do arquivo
from src.layout.style_signature import compute_style_signatures, StyleSignature
from src.core.models import Block

# Em extract_tokens_with_coords(), adicionar:
- italic: bool = bool(span.get("flags", 0) & 2)  # Flag 2 = italic
- color: extrair de span.get("color") se disponível

# Em build_token_graph(), após criar nodes:
1. Converter tokens para Blocks temporários para calcular StyleSignatures
2. Calcular style_signatures usando compute_style_signatures()
3. Adicionar style_signature a cada nó
4. Calcular line_index (ordem Y)
5. Inicializar component_id (será preenchido depois)
```

**Validação:** Executar `python scripts/build_token_graph.py` e verificar que JSON gerado tem campos extras.

---

## Etapa 2: Classificação básica de papéis

### 2.1 Criar função de classificação inicial em `scripts/build_token_graph.py`

**Arquivo:** `scripts/build_token_graph.py`

**Adicionar função:**

```python
def classify_initial_roles(tokens, graph):
    """Classificação inicial básica de papéis (HEADER/LABEL/VALUE).
    
    Regras simplificadas:
    - HEADER: fonte muito grande ou centralizado
    - LABEL: termina com separador (:, —, .) ou curto sem dígitos
    - VALUE: passa type-gate básico ou está ao lado de LABEL
    """
```

**Integrar em `build_token_graph()`:**

- Após criar edges, chamar `classify_initial_roles()`
- Adicionar campo `role` a cada nó

**Validação:** Verificar que nós têm campo `role` no JSON gerado.

---

## Etapa 3: Integrar grafo enriquecido no pipeline

### 3.1 Criar módulo `src/graph/token_graph.py`

**Arquivo:** `src/graph/token_graph.py` (NOVO)

**Conteúdo:**

```python
"""Wrapper para usar grafo de tokens no pipeline."""

from typing import Dict, List, Any
from pathlib import Path
import sys

# Importar funções de build_token_graph
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

def build_token_graph_for_pipeline(pdf_path: str) -> Dict[str, Any]:
    """Constrói grafo de tokens para uso no pipeline.
    
    Returns:
        Dict com 'nodes' e 'edges', onde cada nó tem:
        - id, text, bbox
        - style_signature, role, font_size, bold, italic, color
        - line_index, component_id
    """
    tokens = extract_tokens_from_page(pdf_path)
    graph = build_token_graph(tokens)
    return graph
```

### 3.2 Atualizar `src/core/pipeline.py`

**Arquivo:** `src/core/pipeline.py`

**Mudanças em `_run_single_page()`:**

- Após `build_layout()`, adicionar:
  ```python
  # Construir grafo de tokens v3.0
  from ..graph.token_graph import build_token_graph_for_pipeline
  token_graph = build_token_graph_for_pipeline(pdf_path)
  # Anexar ao layout via setattr
  object.__setattr__(layout, "token_graph", token_graph)
  ```


**Validação:** Pipeline deve executar sem erros (grafo será usado depois).

---

## Etapa 4: Emparelhamento LABEL→VALUE básico

### 4.1 Criar `src/matching/label_value_v3.py`

**Arquivo:** `src/matching/label_value_v3.py` (NOVO)

**Implementação mínima:**

```python
"""Emparelhamento LABEL→VALUE usando grafo ortogonal."""

def find_label_value_pairs_v3(
    token_graph: Dict[str, Any],
    field_name: str,
    field_description: str,
    field_type: str
) -> List[Dict[str, Any]]:
    """Encontra pares LABEL→VALUE para um campo.
    
    Estratégia simplificada:
    1. Encontrar LABELs que contenham palavras-chave do campo
    2. Buscar VALUES ortogonalmente (→, ↓) a partir do LABEL
    3. Filtrar por type-gate básico
    4. Retornar melhor candidato
    """
```

**Integração:**

- Usar `token_graph` do layout
- Buscar LABELs por palavras-chave da descrição do campo
- Buscar VALUES nas direções → e ↓
- Aplicar type-gate básico (`src/validation/validators.py`)

### 4.2 Integrar no pipeline

**Arquivo:** `src/core/pipeline.py`

**Em `_run_single_page()`, na seção de matching:**

- Se `token_graph` existe, tentar usar `find_label_value_pairs_v3()` primeiro
- Fallback para matching existente se não encontrar

**Validação:** Pipeline deve extrair valores usando grafo de tokens.

---

## Etapa 5: Testes com todos os PDFs

### 5.1 Criar script de teste `scripts/test_all_pdfs_v3.py`

**Arquivo:** `scripts/test_all_pdfs_v3.py` (NOVO)

**Conteúdo:**

```python
"""Testa pipeline v3.0 com todos os PDFs de data/samples/."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.pipeline import Pipeline

def main():
    project_root = Path(__file__).parent.parent
    samples_dir = project_root / "data" / "samples"
    ground_truth_path = project_root / "ground_truth.json"
    dataset_path = project_root / "data" / "samples" / "dataset.json"
    
    # Carregar ground truth e dataset
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = json.load(f)
    gt_by_pdf = {entry["pdf"]: entry for entry in gt_data}
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    schema_by_pdf = {entry["pdf_path"]: entry for entry in dataset}
    
    # Pipeline
    pipeline = Pipeline()
    
    # Processar cada PDF
    results = []
    for pdf_name in sorted(gt_by_pdf.keys()):
        pdf_path = samples_dir / pdf_name
        if not pdf_path.exists():
            continue
        
        schema_info = schema_by_pdf.get(pdf_name)
        if not schema_info:
            continue
        
        label = schema_info["label"]
        schema_dict = schema_info["extraction_schema"]
        
        print(f"\n{'='*80}")
        print(f"Processando: {pdf_name} (label: {label})")
        print(f"{'='*80}")
        
        try:
            result = pipeline.run(label, schema_dict, str(pdf_path), debug=True)
            results.append({
                "pdf": pdf_name,
                "result": result
            })
            
            # Comparar com ground truth
            expected = gt_by_pdf[pdf_name]["result"]
            actual = result["results"]
            
            print(f"\nComparação para {pdf_name}:")
            for field_name, expected_value in expected.items():
                actual_value = actual.get(field_name, {}).get("value")
                match = str(actual_value) == str(expected_value) if actual_value else (expected_value is None)
                status = "✓" if match else "✗"
                print(f"  {status} {field_name}: esperado={expected_value}, obtido={actual_value}")
        
        except Exception as e:
            print(f"  ERRO: {e}")
            import traceback
            traceback.print_exc()
    
    # Salvar resultados
    output_path = project_root / "test_results_v3.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResultados salvos em: {output_path}")

if __name__ == "__main__":
    main()
```

### 5.2 Executar testes

**Comando:**

```bash
python scripts/test_all_pdfs_v3.py
```

**Validação esperada:**

- Todos os 6 PDFs processados sem erros
- Resultados comparados com ground_truth.json
- Arquivo `test_results_v3.json` gerado

---

## Checklist de Implementação

### Prioridade 1 (Essencial para funcionar)

- [ ] **Etapa 1.1:** Adicionar campos de estilo em `build_token_graph.py`
- [ ] **Etapa 2.1:** Adicionar classificação básica de papéis
- [ ] **Etapa 3.1:** Criar `src/graph/token_graph.py`
- [ ] **Etapa 3.2:** Integrar grafo no pipeline
- [ ] **Etapa 4.1:** Criar `src/matching/label_value_v3.py` básico
- [ ] **Etapa 4.2:** Integrar no pipeline
- [ ] **Etapa 5.1:** Criar script de teste
- [ ] **Etapa 5.2:** Executar testes e validar resultados

### Prioridade 2 (Melhorias)

- [ ] Adicionar propagação de estilo entre TUs conectados
- [ ] Melhorar classificação de papéis (mais regras)
- [ ] Adicionar filtro de Pareto (já existe, integrar)
- [ ] Adicionar tie-breakers (já existe, integrar)

---

## Ordem de Execução

1. **Implementar Etapa 1** → Testar `build_token_graph.py` isoladamente
2. **Implementar Etapa 2** → Verificar que roles aparecem no JSON
3. **Implementar Etapa 3** → Pipeline deve executar sem erros
4. **Implementar Etapa 4** → Pipeline deve extrair valores
5. **Implementar Etapa 5** → Executar testes e analisar resultados

---

## Critérios de Sucesso

- [ ] Grafo de tokens tem campos de estilo completos
- [ ] Pipeline executa sem erros para todos os PDFs
- [ ] Pelo menos alguns campos são extraídos corretamente
- [ ] Script de teste gera relatório comparativo
- [ ] Visualização HTML continua funcionando

---

## Notas

- **Compatibilidade:** Campos extras no JSON não quebram `visualize_token_graph.py`
- **Incremental:** Cada etapa pode ser testada isoladamente
- **Fallback:** Pipeline mantém matching existente como fallback
- **Foco:** Implementação mínima viável primeiro, melhorias depois

### To-dos

- [ ] Criar src/graph/spacing_model.py com cálculo de limiares automáticos (τ_same_line, τ_same_column, τ_multiline) usando mediana + MAD
- [ ] Criar src/graph/orthogonal_edges.py com construção de grafo ortogonal usando arestas direcionais simples (↑↓←→)
- [ ] Criar src/graph/components.py para agrupamento de TUs por estilo conectados ortogonalmente
- [ ] Criar src/graph/roles_rules.py implementando regras R-H*, R-L*, R-V* e propagação por estilo E-1/E-2
- [ ] Adicionar função build_lexicon em src/core/schema.py para gerar léxico exato por campo
- [ ] Criar src/matching/label_value.py para busca ortogonal determinística LABEL→VALUE em ordem fixa (→↓↑←)
- [ ] Refatorar src/matching/pareto.py para usar critérios lógicos (não scores contínuos) e eliminação de dominados
- [ ] Ajustar src/matching/tie_breakers.py para usar comparação lexicográfica determinística
- [ ] Ajustar src/llm/chooser.py para cache por hash, integração com memória e revalidação type-gate
- [ ] Criar src/extraction/join_multiline.py para concatenação de values multiline
- [ ] Criar src/validation/type_gates.py extraindo type_gate_generic de patterns.py
- [ ] Criar src/utils/proof_builder.py com montagem completa de provas conforme v2.md
- [ ] Criar src/core/memory.py para memória de invariantes (vocabulário, direção, offset, style, shape)
- [ ] Ajustar src/memory/temperature.py para calcular T e usar para política de LLM
- [ ] Refatorar src/core/pipeline.py para seguir fluxo completo do v2.md (15 etapas)
- [ ] Adicionar OrthogonalGraph, StyleComponent, Role em src/core/models.py