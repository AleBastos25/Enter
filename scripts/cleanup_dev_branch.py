"""Script para identificar arquivos a manter/remover na branch dev."""

import os
from pathlib import Path

# Arquivos/diretórios a MANTER
KEEP = {
    # Módulo de grafos
    'src/graph_builder/',
    
    # Scripts relacionados a grafos
    'scripts/build_token_graph.py',
    'scripts/visualize_token_graph_v3.py',
    'scripts/generate_all_htmls.py',
    'scripts/visualize_token_graph.py',
    'scripts/visualize_orthogonal_graph.py',
    
    # Dados de exemplo
    'data/samples/',
    
    # Configs básicos (se necessário)
    'configs/',
    
    # Arquivos raiz essenciais
    'README.md',
    '.gitignore',
    'requirements.txt',  # se existir
    'pyproject.toml',  # se existir
    'setup.py',  # se existir
}

# Verificar o que existe
root = Path('.')
all_files = []
for path in root.rglob('*'):
    if path.is_file() and not any(part.startswith('.') for part in path.parts):
        rel_path = str(path.relative_to(root))
        all_files.append(rel_path)

print("=== Arquivos a MANTER ===")
keep_files = []
for pattern in KEEP:
    for file in all_files:
        if file.startswith(pattern) or file == pattern:
            keep_files.append(file)

for f in sorted(keep_files):
    print(f"  {f}")

print(f"\nTotal a manter: {len(keep_files)}")

print("\n=== Arquivos a REMOVER ===")
remove_files = [f for f in all_files if f not in keep_files and not f.startswith('.')]
for f in sorted(remove_files)[:50]:  # Mostrar primeiros 50
    print(f"  {f}")

if len(remove_files) > 50:
    print(f"  ... e mais {len(remove_files) - 50} arquivos")

print(f"\nTotal a remover: {len(remove_files)}")

