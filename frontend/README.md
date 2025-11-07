# Frontend - Graph Extractor UI

Interface React/Next.js para extração de dados de PDFs.

## Instalação

```bash
npm install
# ou
yarn install
```

## Execução

```bash
# Desenvolvimento
npm run dev

# Build de produção
npm run build

# Executar produção
npm start
```

A aplicação estará disponível em `http://localhost:3000`.

## Configuração

Crie um arquivo `.env.local` na raiz do frontend:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Funcionalidades

- Upload de múltiplos PDFs (até 10)
- Upload de schema JSON ou escrita manual
- Extração sequencial de PDFs
- Visualização de resultados em tempo real
- Modo dev com visualização de grafos
- Persistência em sessão (sessionStorage)
- Busca em páginas
- Organização por pastas (labels)

