"""Teste da refatoração OOP."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build_token_graph import extract_tokens_from_page, build_token_graph

# Testar extração
pdf_path = Path("data/samples/tela_sistema_1.pdf")
print(f"Testando extração de tokens de {pdf_path}...")
tokens = extract_tokens_from_page(str(pdf_path))
print(f"Tokens extraídos: {len(tokens)}")

# Testar construção do grafo
print("\nTestando construção do grafo...")
graph = build_token_graph(tokens, label="tela_sistema")
print(f"Grafo construído: {len(graph['nodes'])} nós, {len(graph['edges'])} edges")

# Verificar alguns roles
print("\nVerificando roles:")
roles_count = {"HEADER": 0, "LABEL": 0, "VALUE": 0, None: 0}
for node in graph["nodes"]:
    role = node.get("role")
    roles_count[role] = roles_count.get(role, 0) + 1

for role, count in roles_count.items():
    if count > 0:
        print(f"  {role}: {count}")

print("\nTeste concluído com sucesso!")

