"""Script para gerar todos os HTMLs de visualização do grafo de tokens."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.visualize_token_graph_v3 import create_token_graph_html_v3

# Lista de PDFs e seus labels
pdfs = [
    ('oab_1.pdf', 'carteira_oab'),
    ('oab_2.pdf', 'carteira_oab'),
    ('oab_3.pdf', 'carteira_oab'),
    ('tela_sistema_1.pdf', 'tela_sistema'),
    ('tela_sistema_2.pdf', 'tela_sistema'),
    ('tela_sistema_3.pdf', 'tela_sistema'),
]

samples_dir = Path('data/samples')

print("Gerando HTMLs para todos os PDFs...\n")

for pdf_name, label in pdfs:
    pdf_path = samples_dir / pdf_name
    if not pdf_path.exists():
        print(f"AVISO: {pdf_path} não encontrado, pulando...")
        continue
    
    output_name = f'token_graph_overlay_v3_{pdf_name.replace(".pdf", "")}.html'
    output_path = Path(output_name)
    
    try:
        print(f"Processando {pdf_name} (label: {label})...")
        create_token_graph_html_v3(str(pdf_path), str(output_path), label=label)
        print(f"  OK - HTML gerado: {output_path}\n")
    except Exception as e:
        print(f"  ERRO ao processar {pdf_name}: {e}\n")

print("Concluído!")

