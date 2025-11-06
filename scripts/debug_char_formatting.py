"""Script para tentar extrair formatação por caractere."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz  # PyMuPDF

# Carregar PDF
pdf_path = Path("data/samples/tela_sistema_2.pdf")
print(f"Carregando PDF: {pdf_path}")

doc = fitz.open(pdf_path)
page = doc[0]

# Tentar diferentes métodos de extração
print("="*80)
print("MÉTODO 1: get_text('dict') - padrão")
print("="*80)
text_dict = page.get_text("dict")
for block in text_dict.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            text = span.get("text", "")
            if "cidade" in text.lower():
                print(f"Span: {repr(text)}")
                print(f"  Font: {span.get('font')}")
                print(f"  Flags: {span.get('flags')}")
                print(f"  Bold: {bool(span.get('flags', 0) & 16)}")

print("\n" + "="*80)
print("MÉTODO 2: get_text('rawdict')")
print("="*80)
try:
    raw_dict = page.get_text("rawdict")
    for block in raw_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "")
                    if "cidade" in text.lower():
                        print(f"Span: {repr(text)}")
                        print(f"  Font: {span.get('font')}")
                        print(f"  Flags: {span.get('flags')}")
                        print(f"  Bold: {bool(span.get('flags', 0) & 16)}")
except Exception as e:
    print(f"Erro: {e}")

print("\n" + "="*80)
print("MÉTODO 3: Tentar usar get_text com flags específicos")
print("="*80)

# Tentar usar get_text com diferentes flags
try:
    # Tentar extrair com mais detalhes
    text_blocks = page.get_text("blocks")
    for block in text_blocks:
        if block[0] == 0:  # Text block
            bbox, text, block_no, block_type = block
            if "cidade" in text.lower():
                print(f"Block text: {repr(text[:100])}")
                print(f"  BBox: {bbox}")
except Exception as e:
    print(f"Erro: {e}")

print("\n" + "="*80)
print("MÉTODO 4: Usar get_textpage() para análise mais detalhada")
print("="*80)

try:
    # get_textpage() pode fornecer mais informações
    textpage = page.get_textpage()
    # Tentar extrair spans individuais
    dict_result = textpage.extractDICT()
    for block in dict_result.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                text = span.get("text", "")
                if "cidade" in text.lower():
                    print(f"Span: {repr(text)}")
                    print(f"  Font: {span.get('font')}")
                    print(f"  Flags: {span.get('flags')}")
                    print(f"  Size: {span.get('size')}")
                    print(f"  Color: {span.get('color')}")
except Exception as e:
    print(f"Erro: {e}")

print("\n" + "="*80)
print("MÉTODO 5: Verificar se há múltiplos spans na mesma posição")
print("="*80)

# Verificar se há sobreposição de spans (pode indicar formatação mista)
text_dict = page.get_text("dict")
for block in text_dict.get("blocks", []):
    if block.get("type") != 0:
        continue
    for line in block.get("lines", []):
        spans = line.get("spans", [])
        # Verificar se há spans com bboxes sobrepostos mas formatações diferentes
        for i, span1 in enumerate(spans):
            text1 = span1.get("text", "")
            if "cidade" in text1.lower():
                bbox1 = span1.get("bbox")
                flags1 = span1.get("flags", 0)
                bold1 = bool(flags1 & 16)
                
                print(f"\nSpan principal encontrado:")
                print(f"  Texto: {repr(text1)}")
                print(f"  Bold: {bold1}")
                print(f"  BBox: {bbox1}")
                
                # Verificar outros spans na mesma linha
                print(f"\n  Outros spans na mesma linha ({len(spans)} total):")
                for j, span2 in enumerate(spans):
                    if i != j:
                        text2 = span2.get("text", "")
                        bbox2 = span2.get("bbox")
                        flags2 = span2.get("flags", 0)
                        bold2 = bool(flags2 & 16)
                        
                        # Verificar sobreposição
                        if bbox1 and bbox2:
                            overlap_x = max(0, min(bbox1[2], bbox2[2]) - max(bbox1[0], bbox2[0]))
                            if overlap_x > 0:
                                print(f"    Span {j}: {repr(text2)} - Bold: {bold2} - Sobreposto!")

print("\n" + "="*80)
print("CONCLUSÃO:")
print("="*80)
print("PyMuPDF agrupa texto com mesma formatação em um único span.")
print("Se 'Cidade' está em negrito e 'Mozarlândia' está normal,")
print("eles DEVEM estar em spans diferentes no PDF original.")
print("Se estão no mesmo span, o PDF pode ter formatação mista")
print("que o PyMuPDF não consegue detectar no nível de caractere.")

doc.close()

