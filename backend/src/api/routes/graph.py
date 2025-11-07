"""Rotas para servir HTMLs do grafo."""

import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, FileResponse

# Adicionar raiz do projeto ao path
# backend/src/api/routes/graph.py
# -> backend/src/api/routes (0 níveis - próprio)
# -> backend/src/api (1 nível - parent)
# -> backend/src (2 níveis - parent.parent)
# -> backend (3 níveis - parent.parent.parent)
# -> raiz do projeto (4 níveis - parent.parent.parent.parent)
backend_src = Path(__file__).parent.parent.parent  # backend/src
backend_dir = backend_src.parent                    # backend
project_root = backend_dir.parent                   # raiz do projeto

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
if str(backend_src) not in sys.path:
    sys.path.insert(0, str(backend_src))

from services.graph_generator import graph_generator


router = APIRouter(tags=["graph"])


@router.get("/graph/{run_id}.html")
async def get_graph_html(run_id: str):
    """Retorna HTML do grafo para uma execução.
    
    Args:
        run_id: ID único da execução
        
    Returns:
        Arquivo HTML do grafo
    """
    html_path = graph_generator.get_graph_html_path(run_id)
    
    if html_path is None or not html_path.exists():
        raise HTTPException(status_code=404, detail=f"Grafo não encontrado para run_id: {run_id}")
    
    # Ler conteúdo do HTML e retornar como HTMLResponse (não força download)
    with open(html_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    
    return HTMLResponse(content=html_content)

