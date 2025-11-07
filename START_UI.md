# Como Iniciar a UI

## Método 1: Duplo clique (mais fácil)

1. Clique duas vezes no arquivo `start-ui.bat`
2. O script irá iniciar automaticamente o backend e frontend

## Método 2: PowerShell

1. Abra o PowerShell na raiz do projeto
2. Execute:
   ```powershell
   .\start-ui.ps1
   ```

## O que o script faz:

1. ✅ Encontra e configura o Node.js
2. ✅ Verifica se o backend está rodando (porta 8000)
3. ✅ Inicia o backend em uma nova janela (se necessário)
4. ✅ Verifica se o frontend está rodando (porta 3000)
5. ✅ Instala dependências do frontend (se necessário)
6. ✅ Inicia o frontend
7. ✅ Abre o navegador automaticamente em http://localhost:3000

## Requisitos:

- Python 3.10+ instalado
- Node.js instalado (o script procura em locais comuns)
- Ambiente virtual Python criado (`.venv`) - opcional

## Problemas comuns:

### Erro de política de execução

Se aparecer erro sobre política de execução, execute no PowerShell:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Backend não inicia

Verifique se a porta 8000 está livre:

```powershell
netstat -ano | findstr :8000
```

### Frontend não inicia

Verifique se a porta 3000 está livre:

```powershell
netstat -ano | findstr :3000
```

## Parar a aplicação:

- **Frontend**: Pressione `Ctrl+C` no terminal do frontend
- **Backend**: Feche a janela do PowerShell do backend ou pressione `Ctrl+C`

## URLs:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Docs da API: http://localhost:8000/docs


