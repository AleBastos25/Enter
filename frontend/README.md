# Frontend - Graph Extractor UI

React/Next.js interface for extracting data from PDFs.

## Installation

```bash
npm install
# or
yarn install
```

## Execution

```bash
# Development
npm run dev

# Production build
npm run build

# Run production
npm start
```

The application will be available at `http://localhost:3000`.

## Configuration

Create a `.env.local` file in the frontend root:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Features

- Upload multiple PDFs (up to 10)
- JSON schema upload or manual writing
- Sequential PDF extraction
- Real-time result visualization
- Dev mode with graph visualization
- Session persistence (sessionStorage)
- Page search
- Organization by folders (labels)
