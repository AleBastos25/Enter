"""Geração de HTML do grafo para visualização."""

import sys
from pathlib import Path
from typing import Optional

# Adicionar raiz do projeto ao path
# backend/src/services/graph_generator.py
# -> backend/src/services (0 níveis - próprio)
# -> backend/src (1 nível - parent)
# -> backend (2 níveis - parent.parent)
# -> raiz do projeto (3 níveis - parent.parent.parent)
backend_src = Path(__file__).parent.parent  # backend/src
backend_dir = backend_src.parent            # backend
project_root = backend_dir.parent           # raiz do projeto

if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from scripts.visualize_token_graph_v3 import create_token_graph_html_v3


class GraphGenerator:
    """Gera HTMLs de visualização do grafo."""
    
    def __init__(self, output_dir: Optional[Path] = None):
        """Inicializa o gerador.
        
        Args:
            output_dir: Diretório para salvar HTMLs (default: backend/static/graphs)
        """
        if output_dir is None:
            output_dir = project_root / "backend" / "static" / "graphs"
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_graph_html(
        self,
        pdf_path: str,
        run_id: str,
        label: Optional[str] = None
    ) -> str:
        """Gera HTML do grafo para um PDF.
        
        Args:
            pdf_path: Caminho para o PDF
            run_id: ID único da execução
            label: Label do documento (opcional)
            
        Returns:
            Caminho relativo para o HTML gerado (ex: /graph/{run_id}.html)
        """
        output_file = self.output_dir / f"{run_id}.html"
        
        try:
            create_token_graph_html_v3(
                pdf_path=str(pdf_path),
                output_path=str(output_file),
                label=label
            )
            
            # Retornar caminho relativo para URL
            return f"/graph/{run_id}.html"
        except Exception as e:
            raise RuntimeError(f"Erro ao gerar HTML do grafo: {str(e)}") from e
    
    def get_graph_html_path(self, run_id: str) -> Optional[Path]:
        """Obtém caminho do arquivo HTML do grafo.
        
        Args:
            run_id: ID único da execução
            
        Returns:
            Caminho do arquivo ou None se não existir
        """
        html_file = self.output_dir / f"{run_id}.html"
        return html_file if html_file.exists() else None


# Instância singleton
graph_generator = GraphGenerator()

