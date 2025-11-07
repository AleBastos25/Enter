# Sistema de Extração de Documentos

Pipeline híbrido layout-first para extração de dados estruturados de PDFs. Extrai informações estruturadas de documentos PDF arbitrários usando uma combinação de análise espacial, detecção de tabelas, matching semântico e fallback opcional com LLM.

## Desafios Mapeados e Soluções Propostas

### Desafios Identificados

1. **Extração de dados estruturados de PDFs com layouts variados**
   - **Problema**: PDFs podem ter layouts muito diferentes (formulários, cartões, telas de sistema, etc.)
   - **Solução**: Construção de grafo hierarquizado que representa a estrutura espacial do documento, assumindo sentido de leitura convencional da esquerda para direita e de cima para baixo. O grafo utiliza edges ortogonais (horizontais e verticais) para capturar relações espaciais entre elementos, permitindo adaptação a diferentes estruturas sem reconfiguração

2. **Matching de campos quando labels variam**
   - **Problema**: Labels podem ser escritos de formas diferentes ("Nome", "Nome do profissional", "Nome completo")
   - **Solução**: Uso de embeddings semânticos (BAAI/bge-small-en-v1.5) para encontrar campos mesmo quando a redação varia

3. **Extração de dados de tabelas**
   - **Problema**: Dados podem estar em tabelas KV (chave-valor) ou tabelas grid
   - **Solução**: Detecção automática de tabelas com suporte a ambos os formatos

4. **Casos ambíguos e edge cases**
   - **Problema**: Alguns campos podem ser difíceis de extrair com heurísticas
   - **Solução**: Fallback opcional com LLM (GPT-4o-mini) para casos ambíguos, com controle de orçamento

5. **Validação de tipos específicos (CPF, CNPJ, datas, etc.)**
   - **Problema**: Dados extraídos precisam ser validados e normalizados
   - **Solução**: Sistema de validadores com 20+ tipos, incluindo tipos brasileiros específicos

6. **Performance e custo**
   - **Problema**: LLM e embeddings podem ser caros e lentos
   - **Solução**: Abordagem determinística por padrão (heurísticas e tabelas primeiro), usando AI apenas quando necessário

7. **Complexidade arquitetural e múltiplos níveis de abstração**
   - **Problema**: O problema exige lidar com múltiplos níveis de abstração (tokens, blocos, tabelas, schemas, hints, validadores) e generalidade dos inputs
   - **Solução**: Uso de programação orientada a objetos com hierarquia de classes bem definida (BaseHint, BaseRule, BaseMatcher, etc.), permitindo extensibilidade e manutenibilidade do código através de abstrações claras

### Arquitetura da Solução

A solução implementa um pipeline híbrido em múltiplas camadas:

1. **Análise de Layout**: Constrói grafo hierarquizado com edges ortogonais que representa a estrutura espacial do documento. O grafo é construído assumindo sentido de leitura convencional (esquerda para direita, cima para baixo), criando relações horizontais (east/west) entre tokens na mesma linha e relações verticais (north/south) entre elementos em linhas diferentes. A hierarquia tipográfica é analisada para identificar padrões de formatação (tamanho de fonte, negrito, cor) que indicam estrutura semântica

2. **Detecção de Tabelas**: Identifica tabelas KV (chave-valor) e grid automaticamente

3. **Enriquecimento de Schema**: Infere tipos, gera sinônimos, extrai hints (padrões tipográficos e semânticos)

4. **Matching Multi-estratégia**: 
   - Relações espaciais através do grafo (mesma linha, abaixo, mesma coluna)
   - Lookups em tabelas
   - Similaridade semântica (embeddings)
   - Memória de padrões (aprendizado incremental)

5. **Extração e Validação**: Extrai valores e valida tipos usando hints e validadores

6. **LLM Fallback**: Opcional para casos ambíguos

7. **Fusão de Resultados**: Combina resultados entre páginas (modo multi-página)

### Diferenciais da Solução

- **Determinístico por padrão**: Heurísticas e tabelas antes de qualquer uso de AI
- **Custo-efetivo**: LLM usado apenas quando necessário, com controle de orçamento
- **Adaptável**: Funciona com diferentes tipos de documentos sem reconfiguração
- **Extensível**: Sistema de validadores e hints facilmente extensível
- **Performático**: Processamento rápido para documentos simples, com opção de análise mais profunda quando necessário


## Quick Start

### Installation

##  Aviso 

**Validação de Instalação:**
- ✅ **Windows**: Instruções validadas e testadas na máquina do desenvolvedor
- ⚠️ **Linux e macOS**: Instruções baseadas em documentação e assistência de IA (GPT-5). **Não foram testadas em ambiente real**. Se encontrar problemas, por favor reporte ou ajuste conforme sua distribuição/versão do sistema operacional.

Para instruções detalhadas de instalação em **Windows, Linux ou macOS**, consulte o [INSTALLATION.md](INSTALLATION.md).

**Instalação rápida:**

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# Windows: .\venv\Scripts\Activate.ps1
# Linux/Mac: source venv/bin/activate

# Instalar dependências Python
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Instalar dependências Node.js (para interface web)
cd frontend
npm install
cd ..
```

**Requisitos:**
- Python >= 3.10 (recomendado: 3.11+)
- Node.js >= 18 (apenas para interface web)
- pip e npm

### Uso Básico

```bash
# Processar PDFs de uma pasta
python scripts/batch_extract.py --input data/samples --output results.json
```


## Como Utilizar a Solução

A solução oferece duas formas de uso: **versão terminal** (CLI) e **versão web** (API + Interface).

### Versão Terminal (CLI)

A versão terminal permite processar múltiplos PDFs de uma pasta e gerar um JSON de resposta oficial.

#### Pré-requisitos

```bash
# Instalar dependências
pip install -r requirements.txt
pip install -r backend/requirements.txt
```

#### Uso Básico

```bash
# Processar todos os PDFs da pasta samples
python scripts/batch_extract.py --input data/samples --output results.json
```

#### Opções Avançadas

```bash
# Processar apenas PDFs com label específico
python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab

# Modo silencioso (sem prints de progresso)
python scripts/batch_extract.py --input data/samples --output results.json --quiet

# Processar pasta customizada
python scripts/batch_extract.py --input /caminho/para/pdfs --output /caminho/para/saida.json
```



### Versão Web (API + Interface)

A versão web oferece uma interface gráfica e uma API REST para extração de dados.

#### Iniciar o Backend (API)

```bash
# No diretório raiz do projeto
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# ou
python -m backend.src.main
```

A API estará disponível em `http://localhost:8000`

**Nota para Windows:** Você pode usar o script `start-ui.bat` (duplo clique) ou `.\start-ui.ps1` no PowerShell para iniciar automaticamente o backend e frontend. Veja [START_UI.md](START_UI.md) para mais detalhes.


#### Iniciar o Frontend (Interface Web)

```bash
# No diretório frontend
cd frontend
npm install
npm run dev
```

A interface estará disponível em `http://localhost:3000`

#### Uso da Interface Web

1. Acesse `http://localhost:3000` no navegador
2. Preencha o **Label** do documento (ex: `carteira_oab`)
3. Defina o **Schema** de extração (JSON com descrições dos campos)
4. Selecione um ou mais arquivos PDF
5. Clique em **Extrair** para processar
6. Visualize os resultados na interface

#### Exemplo de Schema para Interface

```json
{
  "nome": "Nome do profissional, normalmente no canto superior esquerdo",
  "inscricao": "Número de inscrição do profissional",
  "seccional": "Seccional do profissional (sigla UF)",
  "situacao": "Situação do profissional, normalmente no canto inferior direito"
}
```

## Uso via Script CLI

O script `batch_extract.py` permite processar múltiplos PDFs de uma pasta:

```bash
# Processar todos os PDFs da pasta samples
python scripts/batch_extract.py --input data/samples --output results.json

# Processar apenas PDFs com label específico
python scripts/batch_extract.py --input data/samples --output results.json --label carteira_oab

# Modo silencioso
python scripts/batch_extract.py --input data/samples --output results.json --quiet
```

### Opções do Script

- `--input, -i`: Caminho da pasta contendo os PDFs (e opcionalmente dataset.json)
- `--output, -o`: Caminho do arquivo JSON de saída
- `--label, -l`: Filtrar apenas PDFs com este label (opcional)
- `--quiet, -q`: Modo silencioso (não imprime progresso)

## Configuração

### Secrets (para LLM/OpenAI embeddings)

```bash
# Copiar template de secrets
cp configs/secrets.yaml.example configs/secrets.yaml
# Editar e adicionar sua OPENAI_API_KEY
# Windows: notepad configs/secrets.yaml
# Linux/Mac: nano configs/secrets.yaml
```

**Importante:** O arquivo `secrets.yaml` é git-ignored. Use o template `secrets.yaml.example` como base.


## Tipos de Campos e Validadores

O sistema suporta 20+ tipos de campos com validação e normalização automática:

### Tipos Básicos
- `text`: Texto simples ou multi-linha
- `text_multiline`: Texto multi-linha (endereços, descrições)
- `id_simple`: ID alfanumérico (≥3 caracteres, requer ≥1 dígito)
- `date`: Normalizado para `YYYY-MM-DD`
- `money`: Formato brasileiro normalizado para decimal (ex: `76871.20`)
- `percent`: Normalizado para decimal (ex: `12.5`)
- `int`: Número inteiro
- `float`: Número decimal
- `enum`: Enumeração com validação de opções

### Tipos Brasileiros
- `uf`: Código de estado (2 letras maiúsculas: PR, SP, etc.)
- `cep`: CEP brasileiro (8 dígitos)
- `cpf`: CPF brasileiro com validação
- `cnpj`: CNPJ brasileiro com validação
- `phone_br`: Telefone normalizado para E.164
- `placa_mercosul`: Placa de veículo (formato Mercosul ou antigo)
- `cnh`: Número de CNH
- `pis_pasep`: Número PIS/PASEP
- `chave_nf`: Chave de nota fiscal (44 dígitos)
- `rg`: Número de RG
- `email`: Endereço de email
- `alphanum_code`: Código alfanumérico genérico

## Hints (Padrões Tipográficos)

O sistema utiliza hints para extrair padrões tipográficos e semânticos dos campos. As hints identificam características como:
- Tamanho de fonte
- Estilo (negrito, itálico)
- Cor do texto
- Padrões de formatação (datas, valores monetários, telefones, etc.)

As hints são implementadas através de classes especializadas (DateHint, MoneyHint, PhoneHint, etc.) que detectam padrões específicos nos dados extraídos.

## Aprendizado Incremental

O sistema implementa um mecanismo de aprendizado incremental que melhora a precisão da extração ao longo do tempo, aprendendo com documentos processados anteriormente.

### Como Funciona

O sistema de aprendizado coleta informações de cada extração realizada e armazena padrões aprendidos para cada tipo de documento (`label`) e campo:

1. **Coleta de Dados**: Para cada campo extraído, o sistema registra:
   - **Posição espacial** (coordenadas X, Y) onde o campo foi encontrado
   - **Role do token** (LABEL, VALUE, HEADER, etc.)
   - **Tipo de dado** inferido (data, dinheiro, texto, etc.)
   - **Estratégia de matching** utilizada (pattern, regex, embedding, etc.)
   - **Número de conexões** do token no grafo
   - **Sucesso da extração** (se o campo foi encontrado ou não)

2. **Análise de Padrões**: Com base nas ocorrências coletadas, o sistema calcula:
   - **Posição média e desvio padrão** de cada campo
   - **Distribuição de roles** mais comuns
   - **Distribuição de tipos de dado** mais frequentes
   - **Taxa de sucesso** (quantas vezes o campo foi encontrado)
   - **Rigidez do padrão** (quão consistente é a localização do campo)

3. **Aplicação do Aprendizado**: Durante extrações subsequentes, o sistema:
   - **Rejeita matches inconsistentes**: Se um candidato está muito longe da posição esperada, tem role ou tipo de dado muito diferentes do padrão aprendido, ou se o campo nunca foi encontrado em documentos anteriores, ele é rejeitado antes de ser considerado como match válido

### Persistência

O aprendizado é salvo automaticamente após cada extração em:
```
~/.graph_extractor/learning.json
```
(No Windows: `C:\Users\<seu_usuario>\.graph_extractor\learning.json`)

O arquivo é atualizado incrementalmente, permitindo que o conhecimento seja preservado entre execuções do sistema.

### Ativação/Desativação

O aprendizado incremental está **ativado por padrão** e pode ser controlado:

- **CLI**: Use a flag `--no-learning` para desabilitar
  ```bash
  python scripts/batch_extract.py --input data/samples --output results.json --no-learning
  ```

- **API/UI**: O parâmetro `use_learning` pode ser passado na requisição (padrão: `true`)

- **Código**: Passe `use_learning=False` ao inicializar o `GraphSchemaExtractor`

### Benefícios

- **Melhora contínua**: A precisão aumenta conforme mais documentos são processados
- **Adaptação a layouts específicos**: O sistema aprende onde cada campo costuma aparecer em documentos do mesmo tipo
- **Redução de falsos positivos**: Rejeita candidatos que não seguem padrões estabelecidos (requer pelo menos 3 ocorrências para padrões positivos)
- **Transparente**: Funciona automaticamente sem necessidade de configuração adicional

### Limitações

- Requer múltiplas extrações do mesmo tipo de documento para ser efetivo (mínimo de 3 ocorrências para rejeitar matches positivos)
- Padrões aprendidos são específicos por `label` (tipo de documento)
- Pode rejeitar matches válidos se o layout mudar significativamente
- O sistema apenas rejeita matches inconsistentes; não há sistema de priorização/boost para matches que seguem padrões


## Limitações e Trade-offs

### O que Funciona Bem

- **Layouts estruturados**: Documentos com labels e valores claros (IDs, certificados, formulários)
- **Tabelas**: Tabelas KV (chave-valor) e grid com estrutura visível
- **Posicionamento consistente**: Campos que aparecem em locais previsíveis
- **Labels claros**: Labels que correspondem ou são semanticamente similares às descrições do schema
- **PDFs baseados em texto**: PDFs com texto extraível (não scans puros de imagem)

### Casos Difíceis

- **Layouts altamente complexos**: Documentos com elementos sobrepostos, estruturas de colunas incomuns
- **Qualidade de OCR ruim**: PDFs com extração de texto de baixa qualidade ou erros de OCR
- **Labels ambíguos**: Quando múltiplos campos podem corresponder ao mesmo label
- **Documentos muito grandes**: Tempo de processamento aumenta linearmente com o número de páginas

### Trade-offs

- **Performance vs. Precisão**: Análise mais profunda (embeddings, LLM) aumenta precisão mas custa tempo/dinheiro
- **Determinismo vs. AI**: Heurísticas determinísticas são rápidas e gratuitas, mas LLM pode lidar com casos extremos
- **Memória vs. Velocidade**: Memória de padrões melhora precisão ao longo do tempo mas requer armazenamento
- **Multi-página vs. Página única**: Processamento multi-página é mais robusto mas mais lento

## Licença

Este projeto faz parte do desafio take-home do Enter AI Fellowship. (Alexandre Bastos)