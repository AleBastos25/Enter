"""Script para medir o tempo de cada import do pipeline.py"""

import time
import sys
import importlib
from pathlib import Path

def measure_import(module_name, import_func):
    """Mede o tempo de import de um módulo"""
    start = time.perf_counter()
    try:
        import_func()
        elapsed = time.perf_counter() - start
        return elapsed, None
    except Exception as e:
        elapsed = time.perf_counter() - start
        return elapsed, str(e)

def main():
    # Adicionar o diretório raiz ao path
    root_path = Path(__file__).parent.parent
    src_path = root_path / "src"
    if str(root_path) not in sys.path:
        sys.path.insert(0, str(root_path))
    
    print("=" * 80)
    print("Benchmark de Imports do pipeline.py")
    print("=" * 80)
    print()
    
    # Lista de imports do pipeline.py
    imports = [
        # Standard library imports
        ("__future__ annotations", lambda: __import__("__future__", fromlist=["annotations"])),
        ("re", lambda: importlib.import_module("re")),
        ("unicodedata", lambda: importlib.import_module("unicodedata")),
        ("dataclasses", lambda: importlib.import_module("dataclasses")),
        ("pathlib", lambda: importlib.import_module("pathlib")),
        ("typing", lambda: importlib.import_module("typing")),
        ("numpy", lambda: importlib.import_module("numpy")),
        ("yaml", lambda: importlib.import_module("yaml")),
        
        # Project imports (usando importlib com caminho completo)
        ("extraction.text_extractor", lambda: importlib.import_module("src.extraction.text_extractor")),
        ("io.cache", lambda: importlib.import_module("src.io.cache")),
        ("io.pdf_loader", lambda: importlib.import_module("src.io.pdf_loader")),
        ("layout.builder", lambda: importlib.import_module("src.layout.builder")),
        ("core.policy", lambda: importlib.import_module("src.core.policy")),
        ("llm.client", lambda: importlib.import_module("src.llm.client")),
        ("llm.policy", lambda: importlib.import_module("src.llm.policy")),
        ("llm.prompts", lambda: importlib.import_module("src.llm.prompts")),
        ("matching.matcher", lambda: importlib.import_module("src.matching.matcher")),
        ("tables.detector", lambda: importlib.import_module("src.tables.detector")),
        ("validation.validators", lambda: importlib.import_module("src.validation.validators")),
        ("core.models", lambda: importlib.import_module("src.core.models")),
        ("core.schema", lambda: importlib.import_module("src.core.schema")),
    ]
    
    results = []
    total_time = 0
    
    for module_name, import_func in imports:
        elapsed, error = measure_import(module_name, import_func)
        results.append((module_name, elapsed, error))
        total_time += elapsed
        
        status = "OK" if error is None else "ERRO"
        error_msg = f" - ERRO: {error}" if error else ""
        print(f"{status:5s} {module_name:40s} {elapsed*1000:8.2f} ms{error_msg}")
    
    print()
    print("=" * 80)
    print(f"Tempo total: {total_time*1000:.2f} ms ({total_time:.3f} s)")
    print("=" * 80)
    print()
    
    # Ordenar por tempo (mais lento primeiro)
    print("\nTop 15 imports mais lentos:")
    print("-" * 80)
    sorted_results = sorted([r for r in results if r[2] is None], key=lambda x: x[1], reverse=True)
    for i, (module_name, elapsed, _) in enumerate(sorted_results[:15], 1):
        percentage = (elapsed / total_time) * 100
        print(f"{i:2d}. {module_name:40s} {elapsed*1000:8.2f} ms ({percentage:5.1f}%)")

if __name__ == "__main__":
    main()
