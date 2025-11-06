"""Script para debugar detalhes de spans individuais."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF

# Carregar PDF
pdf_path = Path("data/samples/tela_sistema_2.pdf")
print(f"Carregando PDF: {pdf_path}")

doc = fitz.open(pdf_path)
page = doc[0]
width, height = page.rect.width, page.rect.height

text_dict = page.get_text("dict")

# Procurar a linha que contém "Cidade" ou "Mozarlândia" ou "U.F."
print("="*80)
print("ANÁLISE DETALHADA DE TODOS OS SPANS NA LINHA RELEVANTE:")
print("="*80)

for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
    if block_dict.get("type") != 0:
        continue
    
    for line_idx, line_dict in enumerate(block_dict.get("lines", [])):
        spans = line_dict.get("spans", [])
        
        # Verificar se algum span contém palavras-chave
        has_keywords = False
        for span in spans:
            span_text = span.get("text", "").strip()
            if "cidade" in span_text.lower() or "mozarlândia" in span_text.lower() or "u.f." in span_text.lower():
                has_keywords = True
                break
        
        if has_keywords:
            print(f"\nLinha {line_idx} do bloco {block_idx}:")
            print(f"BBox da linha: {line_dict.get('bbox')}")
            print(f"Total de spans: {len(spans)}")
            
            for span_idx, span in enumerate(spans):
                span_text = span.get("text", "").strip()
                flags = span.get("flags", 0)
                bold = bool(flags & 16) or "bold" in (span.get("font", "") or "").lower()
                italic = bool(flags & 2)
                
                print(f"\n  Span {span_idx}:")
                print(f"    Texto: {repr(span_text)}")
                print(f"    Font: {span.get('font')}")
                print(f"    Size: {span.get('size')}")
                print(f"    Flags: {flags} (bin: {bin(flags)})")
                print(f"    Bold: {bold}")
                print(f"    Italic: {italic}")
                print(f"    Color: {span.get('color')}")
                print(f"    BBox: {span.get('bbox')}")
                
                # Calcular posição relativa do texto dentro do span
                if span_text:
                    print(f"    Comprimento: {len(span_text)} caracteres")

# Tentar usar get_text com "rawdict" para ver se há mais detalhes
print("\n" + "="*80)
print("TENTATIVA COM get_text('rawdict'):")
print("="*80)

try:
    raw_dict = page.get_text("rawdict")
    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if "cidade" in text.lower() or "mozarlândia" in text.lower() or "u.f." in text.lower():
                    flags = span.get("flags", 0)
                    bold = bool(flags & 16) or "bold" in (span.get("font", "") or "").lower()
                    print(f"\nSpan (rawdict):")
                    print(f"  Texto: {repr(text)}")
                    print(f"  Font: {span.get('font')}")
                    print(f"  Bold: {bold}")
                    print(f"  Flags: {flags}")
                    print(f"  BBox: {span.get('bbox')}")
except Exception as e:
    print(f"Erro: {e}")

# Tentar usar get_text com "dict" e verificar se há chars individuais
print("\n" + "="*80)
print("VERIFICANDO SE HÁ INFORMAÇÃO DE CARACTERES INDIVIDUAIS:")
print("="*80)

# PyMuPDF não fornece formatação por caractere diretamente
# Mas podemos verificar se o texto completo está em múltiplos spans
# Se "Cidade:" está em um span e "Mozarlândia U.F.: GO CEP: 76709970" está em outro,
# podemos detectar isso

# Verificar se há múltiplos spans na mesma linha com formatações diferentes
for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
    if block_dict.get("type") != 0:
        continue
    
    for line_dict in block_dict.get("lines", []):
        spans = line_dict.get("spans", [])
        
        # Verificar se algum span contém palavras-chave
        relevant_spans = []
        for span in spans:
            span_text = span.get("text", "").strip()
            if "cidade" in span_text.lower() or "mozarlândia" in span_text.lower() or "u.f." in span_text.lower():
                relevant_spans.append(span)
        
        if relevant_spans:
            print(f"\nEncontrados {len(relevant_spans)} spans relevantes na mesma linha:")
            full_text = ""
            for span_idx, span in enumerate(relevant_spans):
                span_text = span.get("text", "").strip()
                flags = span.get("flags", 0)
                bold = bool(flags & 16) or "bold" in (span.get("font", "") or "").lower()
                full_text += span_text
                print(f"  Span {span_idx}: {repr(span_text)} - Bold: {bold}")
            
            print(f"\nTexto completo concatenado: {repr(full_text)}")
            print(f"Se houver múltiplos spans, cada um tem sua própria formatação!")

doc.close()

