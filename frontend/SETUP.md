# Setup do Frontend - Graph Extractor UI

## ⚠️ Node.js Necessário

O frontend requer **Node.js 18+** e **npm** (vem junto com Node.js).

## Instalação do Node.js

### Windows

1. **Baixe o Node.js LTS**:
   - Acesse: https://nodejs.org/
   - Baixe a versão LTS (recomendada)
   - Execute o instalador `.msi`

2. **Durante a instalação**:
   - ✅ Marque "Add to PATH"
   - ✅ Marque "Automatically install necessary tools"

3. **Reinicie o PowerShell/Terminal**

4. **Verifique a instalação**:
   ```powershell
   node --version
   npm --version
   ```

### Alternativa: Chocolatey

Se você tem Chocolatey instalado:

```powershell
choco install nodejs-lts
```

### Alternativa: winget

```powershell
winget install OpenJS.NodeJS.LTS
```

## Instalação das Dependências

Após instalar o Node.js:

```powershell
cd frontend
npm install
```

Isso irá instalar:
- Next.js
- React
- TypeScript
- TailwindCSS
- Axios
- JSZip

## Execução

```powershell
# Desenvolvimento
npm run dev

# Build de produção
npm run build

# Executar produção
npm start
```

## Configuração

Crie um arquivo `.env.local` (opcional):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Se o backend estiver em outra porta, ajuste conforme necessário.

## Problemas Comuns

### "npm não é reconhecido"

- Node.js não está instalado
- Node.js não está no PATH
- Reinicie o terminal após instalar

### Erro de módulos não encontrados

```powershell
# Limpar cache e reinstalar
rm -rf node_modules package-lock.json
npm install
```

### Porta 3000 ocupada

```powershell
npm run dev -- -p 3001
```

