"""Script para debugar formatação granular de tokens."""

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

# Procurar tokens 16 e 17
token_id = 0
token_16 = None
token_17 = None

for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
    if block_dict.get("type") != 0:  # 0 = text block
        continue
    
    for line_dict in block_dict.get("lines", []):
        spans = line_dict.get("spans", [])
        
        for span in spans:
            span_text = span.get("text", "").strip()
            if not span_text:
                continue
            
            span_bbox = span.get("bbox")
            if not span_bbox:
                continue
            
            # Verificar se contém ":" e deve ser separado
            if ":" in span_text and len(span_text) > 3:
                colon_pos = span_text.find(":")
                if colon_pos > 0 and colon_pos < len(span_text) - 1:
                    before_colon = span_text[:colon_pos + 1].strip()
                    after_colon = span_text[colon_pos + 1:].strip()
                    
                    # Verificar se deve separar
                    import re
                    date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
                    is_date_after = bool(date_pattern.search(after_colon))
                    is_value_after = bool(re.search(r"^\d|^[A-Z]", after_colon))
                    
                    if is_date_after or (is_value_after and len(after_colon) > 0):
                        # Separar em dois tokens
                        if token_id == 16:
                            token_16 = {
                                "id": token_id,
                                "text": before_colon,
                                "span": span,
                                "is_separated": True,
                                "part": "before_colon"
                            }
                        token_id += 1
                        if token_id == 17:
                            token_17 = {
                                "id": token_id,
                                "text": after_colon,
                                "span": span,
                                "is_separated": True,
                                "part": "after_colon"
                            }
                        token_id += 1
                        continue
            
            # Token normal
            if token_id == 16:
                token_16 = {
                    "id": token_id,
                    "text": span_text,
                    "span": span,
                    "is_separated": False
                }
            elif token_id == 17:
                token_17 = {
                    "id": token_id,
                    "text": span_text,
                    "span": span,
                    "is_separated": False
                }
            
            token_id += 1

print("\n" + "="*80)
print("TOKEN 16:")
print("="*80)
if token_16:
    print(f"ID: {token_16['id']}")
    print(f"Texto: {repr(token_16['text'])}")
    span = token_16['span']
    print(f"Font: {span.get('font')}")
    print(f"Size: {span.get('size')}")
    flags = span.get("flags", 0)
    print(f"Flags: {flags} (bin: {bin(flags)})")
    print(f"Bold (flag 16): {bool(flags & 16)}")
    print(f"Italic (flag 2): {bool(flags & 2)}")
    print(f"Color: {span.get('color')}")
    print(f"Foi separado: {token_16.get('is_separated', False)}")
    
    # Tentar extrair formatação por caractere
    print(f"\nTentando extrair formatação granular...")
    # PyMuPDF não fornece formatação por caractere diretamente no dict
    # Mas podemos verificar se há múltiplos spans no mesmo texto
else:
    print("Token 16 não encontrado!")

print("\n" + "="*80)
print("TOKEN 17:")
print("="*80)
if token_17:
    print(f"ID: {token_17['id']}")
    print(f"Texto: {repr(token_17['text'])}")
    span = token_17['span']
    print(f"Font: {span.get('font')}")
    print(f"Size: {span.get('size')}")
    flags = span.get("flags", 0)
    print(f"Flags: {flags} (bin: {bin(flags)})")
    print(f"Bold (flag 16): {bool(flags & 16)}")
    print(f"Italic (flag 2): {bool(flags & 2)}")
    print(f"Color: {span.get('color')}")
    print(f"Foi separado: {token_17.get('is_separated', False)}")
else:
    print("Token 17 não encontrado!")

# Tentar extrair formatação mais granular usando get_text("rawdict") ou spans individuais
print("\n" + "="*80)
print("ANÁLISE DETALHADA DE SPANS:")
print("="*80)

# Procurar spans que contenham "cidade" ou "Morzolandia" ou "U.F.:"
for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
    if block_dict.get("type") != 0:
        continue
    
    for line_dict in block_dict.get("lines", []):
        spans = line_dict.get("spans", [])
        
        for span in spans:
            span_text = span.get("text", "").strip()
            if not span_text:
                continue
            
            # Procurar por palavras-chave
            if "cidade" in span_text.lower() or "morzolandia" in span_text.lower() or "u.f." in span_text.lower():
                flags = span.get("flags", 0)
                bold = bool(flags & 16)
                italic = bool(flags & 2)
                
                print(f"\nSpan encontrado:")
                print(f"  Texto: {repr(span_text)}")
                print(f"  Font: {span.get('font')}")
                print(f"  Size: {span.get('size')}")
                print(f"  Bold: {bold}")
                print(f"  Italic: {italic}")
                print(f"  Color: {span.get('color')}")
                print(f"  BBox: {span.get('bbox')}")

# Tentar usar get_text com opções mais detalhadas
print("\n" + "="*80)
print("TENTATIVA DE EXTRAÇÃO GRANULAR COM get_text('rawdict'):")
print("="*80)

try:
    raw_dict = page.get_text("rawdict")
    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if "cidade" in text.lower() or "morzolandia" in text.lower() or "u.f." in text.lower():
                    flags = span.get("flags", 0)
                    bold = bool(flags & 16)
                    print(f"\nSpan (rawdict):")
                    print(f"  Texto: {repr(text)}")
                    print(f"  Bold: {bold}")
                    print(f"  Flags: {flags}")
except Exception as e:
    print(f"Erro ao usar rawdict: {e}")

doc.close()

