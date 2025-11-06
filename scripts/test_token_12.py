"""Teste simples para verificar token 12."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

tokens = extract_tokens_from_page('data/samples/tela_sistema_1.pdf')
graph = build_token_graph(tokens)

nodes = {n['id']: n for n in graph['nodes']}
print(f"Token 12 role: {nodes[12].get('role')}")
print(f"Token 17 role: {nodes[17].get('role')}")

