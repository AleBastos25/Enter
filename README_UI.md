# UI Graph Extractor - Documentação

Interface completa para extração de dados de PDFs usando Graph Extractor.

## Estrutura

- **Backend**: FastAPI em `backend/`
- **Frontend**: Next.js/React em `frontend/`

## Pré-requisitos

- **Python 3.10+** (para o backend)
- **Node.js 18+** e **npm** (para o frontend)

> ⚠️ **Importante**: Se você receber erro "npm não é reconhecido", precisa instalar o Node.js primeiro.
> Veja [INSTALLATION.md](INSTALLATION.md) ou [frontend/SETUP.md](frontend/SETUP.md) para instruções detalhadas.

## 🚀 Início Rápido

**Método mais fácil**: Execute `start-ui.bat` (duplo clique) ou `.\start-ui.ps1` no PowerShell.

O script automaticamente:
- Configura o Node.js
- Inicia o backend
- Inicia o frontend  
- Abre o navegador

Veja [START_UI.md](START_UI.md) para mais detalhes.

## Instalação e Execução Manual

### 1. Instalar Node.js (se ainda não tiver)

**Windows:**
- Baixe de: https://nodejs.org/ (versão LTS)
- Opção A: Execute o instalador `.msi` (recomendado - adiciona ao PATH automaticamente)
- Opção B: Extraia o zip e adicione ao PATH manualmente

**Se você já baixou o Node.js (ex: `C:\Users\aleba\Downloads\node-v24.11.0-win-x64`):**
```powershell
# Execute o script de configuração
.\setup_node_path.ps1

# Ou adicione manualmente ao PATH:
[Environment]::SetEnvironmentVariable("Path", "$([Environment]::GetEnvironmentVariable('Path','User'));C:\Users\aleba\Downloads\node-v24.11.0-win-x64", "User")
```

Reinicie o terminal e verifique: `node --version` e `npm --version`

### 2. Backend

```bash
# No diretório raiz do projeto
# Instalar dependências (se ainda não instalou)
pip install -r requirements.txt
pip install -r backend/requirements.txt

# Executar servidor
uvicorn backend.src.main:app --reload --host 0.0.0.0 --port 8000
# ou
python -m backend.src.main
```

O backend estará disponível em `http://localhost:8000`.

**Nota para Windows:** Você pode usar o script `start-ui.bat` (duplo clique) ou `.\start-ui.ps1` no PowerShell para iniciar automaticamente o backend e frontend. O script `start-ui.bat` pode ser adaptado para rodar em qualquer máquina Windows.

### 3. Frontend

```bash
# Instalar dependências (após instalar Node.js)
cd frontend
npm install

# Executar em desenvolvimento
npm run dev
```

O frontend estará disponível em `http://localhost:3000`.

## Funcionalidades Implementadas

### Backend

- ✅ Endpoint `POST /api/graph-extract` para extração de múltiplos PDFs
- ✅ Endpoint `GET /graph/{run_id}.html` para visualização de grafos
- ✅ Suporte a callbacks de progresso no Graph Extractor
- ✅ Geração de HTML do grafo durante extração (dev mode)
- ✅ Validação de até 10 PDFs por requisição
- ✅ Processamento sequencial de PDFs
- ✅ Extração de regras usadas do metadata

### Frontend

- ✅ Interface estilo ChatGPT
- ✅ Upload de schema JSON (arquivo ou manual)
- ✅ Drag & Drop de PDFs (até 10)
- ✅ Autocomplete de labels recentes
- ✅ Visualização de resultados em tempo real
- ✅ Modo dev com visualização de grafos, tempo e regras
- ✅ Sidebar com páginas e busca
- ✅ Organização por pastas (labels)
- ✅ Persistência em sessionStorage
- ✅ Botões Copiar e Baixar JSON
- ✅ Retry por run (estrutura pronta)

## Uso

1. **Iniciar Backend**: Execute o servidor FastAPI na porta 8000
2. **Iniciar Frontend**: Execute o servidor Next.js na porta 3000
3. **Acessar UI**: Abra `http://localhost:3000` no navegador
4. **Extrair Dados**:
   - Digite um label
   - Faça upload de um schema JSON ou escreva manualmente
   - Adicione PDFs (drag & drop ou seleção)
   - Clique em "Enviar"
   - Aguarde o processamento sequencial
   - Visualize os resultados

## Modo Dev

Ative o toggle "Dev Mode" no header para:
- Ver tempo de processamento
- Ver regras/estratégias usadas
- Acessar link "Abrir Grafo" para visualização HTML do grafo

## Notas

- Persistência é apenas em sessão (perde ao fechar a aba)
- Dev mode persiste em localStorage
- HTMLs do grafo são gerados apenas em dev mode
- Processamento é sequencial (um PDF por vez)

## Próximos Passos (Opcional)

- [ ] Implementar streaming real-time com SSE
- [ ] Adicionar export ZIP de inputs/outputs
- [ ] Melhorar tratamento de erros
- [ ] Adicionar validação de schema mais robusta
- [ ] Implementar retry completo
- [ ] Adicionar loading states mais detalhados

