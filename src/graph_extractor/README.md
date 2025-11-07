# Graph-based Schema Extractor

Sistema de extração de schema baseado em grafo hierárquico de tokens. Utiliza uma cascata de estratégias de matching para encontrar valores correspondentes a cada campo do schema de extração.

## Características

- **Grafo hierárquico**: Constrói grafo de tokens com relações espaciais (edges ortogonais)
- **Cascata de matching**: Pattern → Regex → Embeddings → Tiebreaking
- **Hints/Patterns**: Sistema de dicas para identificar tipos específicos (data, dinheiro, endereço, etc.)
- **Embeddings semânticos**: Usa FastEmbed para matching semântico
- **Tiebreaking inteligente**: Heurísticas + LLM para desempatar entre candidatos
- **Gerenciamento de nós**: Evita reutilização de nós já extraídos

## Uso Básico

```python
from src.graph_extractor import GraphSchemaExtractor

# Inicializar extrator
extractor = GraphSchemaExtractor(
    embedding_model="BAAI/bge-small-en-v1.5",
    min_embedding_similarity=0.3,
    tiebreak_threshold=0.05,
    llm_model="gpt-5-mini",
    use_llm_tiebreaker=True
)

# Definir schema
schema = {
    "nome": "Nome do profissional",
    "inscricao": "Número de inscrição do profissional",
    "seccional": "Seccional do profissional",
}

# Extrair informações
result = extractor.extract(
    label="carteira_oab",
    extraction_schema=schema,
    pdf_path="data/samples/oab_1.pdf"
)

# Acessar resultados
print(result["fields"])
print(result["metadata"])
```

## Arquitetura

### Cascata de Matching

1. **Pattern Matching (Hints)**
   - Aplica hints relevantes para o campo
   - Detecta padrões (data, dinheiro, CPF/CNPJ, telefone, endereço, texto)
   - Score baseado em match perfeito/parcial

2. **Regex Matching**
   - Normalização de texto (remove acentos, lowercase)
   - Match perfeito: nome do campo encontrado no token
   - Match por regex: usa patterns das hints
   - Match parcial: palavras-chave encontradas

3. **Embedding Matching**
   - Gera embeddings usando FastEmbed
   - Calcula similaridade de cosseno entre descrição do campo e tokens
   - Compara com LABEL+VALUE combinado ou apenas VALUE

4. **Tiebreaking**
   - **Heurísticas**: Tipo de token, ordem no documento, tamanho do texto, distância LABEL-VALUE
   - **LLM**: Usado quando heurísticas não resolvem (GPT-5-mini por padrão)

### Sistema de Hints

Hints pré-definidas para identificar padrões específicos:

- **DateHint**: Detecta datas em vários formatos
- **MoneyHint**: Detecta valores monetários (R$, $, €, etc.)
- **CPFCNPJHint**: Detecta CPF/CNPJ
- **PhoneHint**: Detecta números de telefone
- **AddressHint**: Detecta endereços e agrega múltiplos VALUEs
- **TextHint**: Fallback para texto genérico

### Gerenciamento de Nós

- Rastreia nós já usados para evitar duplicação
- Suporta reutilização parcial (ex: "R$ 1.000,00 - R$ 2.000,00")
- Marca nós como usados após extração

## Formato de Saída

```json
{
  "label": "carteira_oab",
  "fields": {
    "nome": "JOÃO DA SILVA",
    "inscricao": "101943",
    "seccional": "SP"
  },
  "metadata": {
    "total_fields": 3,
    "extracted_fields": 3,
    "success_rate": 1.0,
    "nodes_used": [5, 12, 18],
    "nodes_used_count": 3,
    "extraction_time": 2.5,
    "strategies_breakdown": {
      "nome": "pattern_perfect",
      "inscricao": "regex_perfect",
      "seccional": "embedding"
    }
  }
}
```

## Estratégias de Matching

- `pattern_perfect`: Match perfeito via hints
- `pattern_perfect_tiebreak`: Múltiplos matches perfeitos, desempate necessário
- `regex_perfect`: Match perfeito via regex
- `regex_perfect_tiebreak`: Múltiplos matches perfeitos, desempate necessário
- `regex_partial`: Match parcial via regex
- `embedding`: Match por similaridade semântica
- `embedding_tiebreak`: Match por embeddings com desempate
- `none`: Nenhum match encontrado

## Dependências

- `fastembed>=0.2.0`: Para embeddings semânticos rápidos
- `openai>=1.0.0`: Para LLM tiebreaker (opcional)
- `numpy>=1.20.0`: Para cálculos de similaridade
- Componentes do `graph_builder`: TokenExtractor, GraphBuilder, RoleClassifier

## Configuração

### Parâmetros do Extrator

- `embedding_model`: Modelo FastEmbed (default: "BAAI/bge-small-en-v1.5")
- `min_embedding_similarity`: Similaridade mínima para embeddings (0.0 a 1.0, default: 0.3)
- `tiebreak_threshold`: Threshold para considerar empate (default: 0.05)
- `llm_model`: Modelo LLM para tiebreaker (default: "gpt-5-mini")
- `use_llm_tiebreaker`: Se True, usa LLM quando heurísticas não resolvem (default: True)

### API Key (LLM Tiebreaker)

Configure a API key do OpenAI:

```bash
# Variável de ambiente
export OPENAI_API_KEY=sk-...

# Ou em configs/secrets.yaml
OPENAI_API_KEY: sk-...
```

## Limitações

- PDFs devem ter OCR feito (texto embutido)
- Processa apenas primeira página do PDF
- Performance depende do número de nós no grafo
- LLM tiebreaker adiciona custo e latência

## Exemplo Completo

Ver `test_graph_extractor.py` para exemplo completo de uso.

