"""Extração de tokens do PDF."""

import re
import logging
from typing import List
import fitz  # PyMuPDF
from src.graph_builder.models import Token, BBox


class TokenExtractor:
    """Extrai tokens (palavras/frases) com coordenadas do PDF."""
    
    def __init__(self):
        """Inicializa o extrator."""
        self.date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}")
        # Padrão para detectar múltiplos dois pontos: texto : texto : texto
        self.multiple_colons_pattern = re.compile(r'([^:]+:\s*[^:]+(?::\s*[^:]+)*)')
    
    def extract(self, pdf_path: str) -> List[Token]:
        """Extrai tokens do PDF.
        
        Args:
            pdf_path: Caminho para o arquivo PDF.
        
        Returns:
            Lista de tokens extraídos.
        """
        doc = fitz.open(pdf_path)
        page = doc[0]
        width, height = page.rect.width, page.rect.height
        
        text_dict = page.get_text("dict")
        tokens = []
        token_id = 0
        
        for block_idx, block_dict in enumerate(text_dict.get("blocks", [])):
            if block_dict.get("type") != 0:  # 0 = text block
                continue
            
            for line_dict in block_dict.get("lines", []):
                spans = line_dict.get("spans", [])
                
                for span in spans:
                    span_text = span.get("text", "").strip()
                    if not span_text:
                        continue
                    
                    span_bbox = span.get("bbox")  # [x0, y0, x1, y1] em coordenadas da página
                    if not span_bbox:
                        continue
                    
                    # Normalizar bbox e aplicar padding
                    bbox_normalized = self._normalize_bbox(span_bbox, width, height)
                    
                    # Extrair metadados de estilo
                    flags = span.get("flags", 0)
                    italic = bool(flags & 2)  # Flag 2 = italic
                    bold = bool(flags & 16) or "bold" in (span.get("font", "") or "").lower()
                    
                    # Extrair cor
                    color = span.get("color")
                    if color is not None:
                        if isinstance(color, int):
                            color = f"#{color:06x}"
                    
                    # Verificar se deve separar por ":"
                    # Usar separação recursiva para lidar com múltiplos dois pontos
                    tokens_to_add = self._separate_recursively(
                        span_text, bbox_normalized, span.get("size"), bold, italic, color, block_idx
                    )
                    
                    for token_data in tokens_to_add:
                        token = Token(
                            id=token_id,
                            text=token_data["text"],
                            bbox=token_data["bbox"],
                            font_size=token_data.get("font_size"),
                            bold=token_data.get("bold", False),
                            italic=token_data.get("italic", False),
                            color=token_data.get("color"),
                            block_id=block_idx,
                            role=token_data.get("role"),  # Usar role sugerido se disponível (para padrão múltiplos dois pontos)
                            separated_pair=token_data.get("separated_pair", False)  # Marcar se foi separado
                        )
                        tokens.append(token)
                        token_id += 1
        
        doc.close()
        
        # Mesclar tokens com sobreposição excessiva de bbox
        tokens = self._merge_overlapping_tokens(tokens)
        
        return tokens
    
    def _merge_overlapping_tokens(self, tokens: List[Token]) -> List[Token]:
        """Mescla tokens com sobreposição excessiva de bbox ou tokens em linhas consecutivas.
        
        - Se dois tokens têm sobreposição > 80% em área, são mesclados.
        - Se dois tokens estão na mesma coluna (x sobreposto) e em linhas consecutivas (y próximo),
          e têm texto relacionado (ex: "Telefone da" + "Cobradora"), são mesclados.
        - Após mesclar, se o token resultante tiver dois pontos no meio, separa novamente.
        """
        if len(tokens) < 2:
            return tokens
        
        merged = []
        used = set()
        next_id = max((t.id for t in tokens), default=0) + 1  # ID para novos tokens gerados
        
        for i, token1 in enumerate(tokens):
            if i in used:
                continue
            
            # Procurar tokens sobrepostos ou em linhas consecutivas
            overlapping_tokens = [token1]
            overlapping_indices = [i]
            
            for j, token2 in enumerate(tokens[i+1:], start=i+1):
                if j in used:
                    continue
                
                bbox1 = token1.bbox
                bbox2 = token2.bbox
                
                # Calcular sobreposição
                x_overlap = max(0, min(bbox1.x1, bbox2.x1) - max(bbox1.x0, bbox2.x0))
                y_overlap = max(0, min(bbox1.y1, bbox2.y1) - max(bbox1.y0, bbox2.y0))
                overlap_area = x_overlap * y_overlap
                
                area1 = (bbox1.x1 - bbox1.x0) * (bbox1.y1 - bbox1.y0)
                area2 = (bbox2.x1 - bbox2.x0) * (bbox2.y1 - bbox2.y0)
                
                # Calcular ratio de sobreposição (usar a menor área como referência)
                min_area = min(area1, area2)
                should_merge = False
                
                if min_area > 0:
                    overlap_ratio = overlap_area / min_area
                    
                    # Se sobreposição > 80%, mesclar
                    if overlap_ratio > 0.8:
                        should_merge = True
                
                # Verificar se são tokens em linhas consecutivas na mesma coluna
                if not should_merge:
                    # Calcular sobreposição vertical usando a fórmula especificada
                    # Razão = (altura sobreposta) / (altura da célula se mesclada)
                    y0_1, y1_1 = bbox1.y0, bbox1.y1
                    y0_2, y1_2 = bbox2.y0, bbox2.y1
                    
                    # Altura sobreposta
                    overlap_height = max(0, min(y1_1, y1_2) - max(y0_1, y0_2))
                    
                    # Altura da célula se mesclada
                    merged_height = max(y1_1, y1_2) - min(y0_1, y0_2)
                    
                    # Razão de sobreposição vertical
                    vertical_overlap_ratio = overlap_height / merged_height if merged_height > 0 else 0
                    
                    # Verificar sobreposição horizontal (mesma coluna)
                    width1 = bbox1.x1 - bbox1.x0
                    width2 = bbox2.x1 - bbox2.x0
                    min_width = min(width1, width2)
                    x_overlap_width = x_overlap / min_width if min_width > 0 else 0
                    
                    # Se estão na mesma coluna (x_overlap > 70%) e têm sobreposição vertical suficiente
                    # Usar threshold de 20% de sobreposição vertical (meio termo entre 15% e 25%)
                    if x_overlap_width > 0.7 and vertical_overlap_ratio > 0.20:
                        # Verificar se os textos parecem relacionados (um continua o outro)
                        text1_lower = token1.text.strip().lower()
                        text2_lower = token2.text.strip().lower()
                        
                        # Verificar se são tokens adjacentes (não há outros tokens na mesma coluna entre eles)
                        is_adjacent = True
                        for other_token in tokens:
                            if other_token.id == token1.id or other_token.id == token2.id:
                                continue
                            other_bbox = other_token.bbox
                            # Verificar se está entre os dois tokens E na mesma coluna
                            # Calcular sobreposição X com o token intermediário
                            other_x_overlap = max(0, min(bbox1.x1, bbox2.x1, other_bbox.x1) - max(bbox1.x0, bbox2.x0, other_bbox.x0))
                            other_x_overlap_ratio = other_x_overlap / min_width if min_width > 0 else 0
                            
                            # Só considerar como bloqueador se estiver na mesma coluna (x_overlap > 50%)
                            if (min(bbox1.y0, bbox2.y0) < other_bbox.y0 < max(bbox1.y1, bbox2.y1) and
                                other_x_overlap_ratio > 0.5):
                                is_adjacent = False
                                break
                        
                        if is_adjacent:
                            # Verificar se parecem formar uma frase coerente
                            # Ex: "Telefone da" + "Cobradora" = OK
                            # Ex: "SUPLEMENTAR" + "Endereço Profissional" = NÃO (são títulos distintos)
                            text1_words = text1_lower.split()
                            text2_words = text2_lower.split()
                            
                            if len(text1_words) > 0 and len(text2_words) > 0:
                                text1_last_word = text1_words[-1] if text1_words else ""
                                text2_first_word = text2_words[0] if text2_words else ""
                                
                                # Palavras comuns que indicam continuação
                                connecting_words = {'da', 'de', 'do', 'para', 'com', 'em', 'na', 'no', 'pelo', 'pela'}
                                
                                # Verificar se um termina com palavra conectora ou dois pontos
                                if text1_last_word in connecting_words or text1_last_word.endswith(':'):
                                    should_merge = True
                                # Verificar se são palavras distintas que parecem títulos (ambas em maiúsculas ou ambas substantivos)
                                elif (text1_lower.isupper() and text2_lower.isupper() and
                                      len(text1_words) == 1 and len(text2_words) >= 2):
                                    # Ambos são títulos distintos, não mesclar
                                    should_merge = False
                                # Se não há indicador claro, não mesclar por segurança
                                else:
                                    should_merge = False
                
                if should_merge:
                    overlapping_tokens.append(token2)
                    overlapping_indices.append(j)
            
            # Se encontrou tokens sobrepostos, mesclar
            if len(overlapping_tokens) > 1:
                # Mesclar textos (usar quebra de linha se estiverem em linhas diferentes)
                texts = []
                for t in overlapping_tokens:
                    texts.append(t.text.strip())
                
                # Sempre usar espaço para mesclar tokens (não usar \n)
                sorted_tokens = sorted(overlapping_tokens, key=lambda t: (t.bbox.y0, t.bbox.x0))
                merged_text = " ".join(t.text.strip() for t in sorted_tokens)
                
                # Calcular bbox unificado (union)
                x0 = min(t.bbox.x0 for t in overlapping_tokens)
                y0 = min(t.bbox.y0 for t in overlapping_tokens)
                x1 = max(t.bbox.x1 for t in overlapping_tokens)
                y1 = max(t.bbox.y1 for t in overlapping_tokens)
                
                # Usar propriedades do primeiro token (ou do token com maior área)
                main_token = max(overlapping_tokens, key=lambda t: (t.bbox.x1 - t.bbox.x0) * (t.bbox.y1 - t.bbox.y0))
                
                merged_token = Token(
                    id=token1.id,  # Manter ID do primeiro token
                    text=merged_text,
                    bbox=BBox(x0, y0, x1, y1),
                    font_size=main_token.font_size,
                    bold=main_token.bold,
                    italic=main_token.italic,
                    color=main_token.color,
                    block_id=main_token.block_id,
                    role=main_token.role  # Manter role se houver
                )
                
                # Verificar se o token mesclado tem dois pontos no meio
                # Se sim, separar novamente (isso garante que mesmo merges indevidos serão corrigidos)
                if merged_token.has_colon_in_middle():
                    # Marcar que estamos em processo de merge para permitir separação mais permissiva
                    self._merging = True
                    try:
                        # Separar o token mesclado
                        separated = self._maybe_separate_by_colon(
                            merged_text,
                            merged_token.bbox,
                            main_token.font_size,
                            main_token.bold,
                            main_token.italic,
                            main_token.color,
                            main_token.block_id
                        )
                    finally:
                        self._merging = False
                    if separated and len(separated) > 1:
                        # Converter dicts para Tokens com novos IDs
                        for idx, token_data in enumerate(separated):
                            token_obj = Token(
                                id=merged_token.id if idx == 0 else next_id,  # Primeiro mantém ID original, outros recebem novo ID
                                text=token_data["text"],
                                bbox=token_data["bbox"],
                                font_size=token_data.get("font_size", main_token.font_size),
                                bold=token_data.get("bold", main_token.bold),
                                italic=token_data.get("italic", main_token.italic),
                                color=token_data.get("color", main_token.color),
                                block_id=main_token.block_id,
                                role=token_data.get("role")
                            )
                            merged.append(token_obj)
                            if idx > 0:
                                next_id += 1
                    else:
                        # Se não conseguiu separar, manter o token mesclado
                        merged.append(merged_token)
                else:
                    merged.append(merged_token)
                used.update(overlapping_indices)
            else:
                merged.append(token1)
        
        return merged
    
    def _separate_recursively(
        self,
        span_text: str,
        bbox: BBox,
        font_size: float,
        bold: bool,
        italic: bool,
        color: str,
        block_id: int
    ) -> List[dict]:
        """Separa texto recursivamente por dois pontos.
        
        Args:
            span_text: Texto do span.
            bbox: Bbox normalizado.
            font_size: Tamanho da fonte.
            bold: Se é negrito.
            italic: Se é itálico.
            color: Cor do texto.
            block_id: ID do bloco.
        
        Returns:
            Lista de dicionários com tokens (pode ter apenas um se não precisar separar).
        """
        separated = self._maybe_separate_by_colon(
            span_text, bbox, font_size, bold, italic, color, block_id
        )
        
        if not separated:
            # Não precisa separar, retornar token único
            return [{
                "text": span_text,
                "bbox": bbox,
                "font_size": font_size,
                "bold": bold,
                "italic": italic,
                "color": color
            }]
        
        # Verificar se algum token separado ainda tem múltiplos dois pontos
        result = []
        for token_data in separated:
            token_text = token_data["text"]
            token_bbox = token_data["bbox"]
            
            # Contar dois pontos
            colon_count = token_text.count(":")
            if colon_count > 1:
                # Ainda tem múltiplos dois pontos, separar recursivamente
                sub_tokens = self._separate_recursively(
                    token_text, token_bbox, font_size, bold, italic, color, block_id
                )
                result.extend(sub_tokens)
            else:
                # Não precisa mais separar
                result.append(token_data)
        
        return result
    
    def _normalize_bbox(self, span_bbox: List[float], width: float, height: float) -> BBox:
        """Normaliza bbox e aplica padding à direita.
        
        Args:
            span_bbox: Bbox original [x0, y0, x1, y1] em coordenadas da página.
            width: Largura da página.
            height: Altura da página.
        
        Returns:
            BBox normalizado (0-1).
        """
        span_width = span_bbox[2] - span_bbox[0]
        padding_factor_right = 0.0  # 12% de padding na largura
        min_padding_right = 0.0  # Mínimo de 20 pontos à direita
        
        padding_right = max(span_width * padding_factor_right, min_padding_right)
        
        x0_norm = max(0.0, span_bbox[0] / width)
        y0_norm = max(0.0, span_bbox[1] / height)
        x1_norm = min(1.0, (span_bbox[2] + padding_right) / width)
        y1_norm = min(1.0, span_bbox[3] / height)
        
        return BBox(x0_norm, y0_norm, x1_norm, y1_norm)
    
    def _maybe_separate_by_colon(
        self,
        span_text: str,
        bbox: BBox,
        font_size: float,
        bold: bool,
        italic: bool,
        color: str,
        block_id: int
    ) -> List[dict]:
        """Separa span por ':' se necessário.
        
        REGRA ATUALIZADA: Separa em TODOS os dois pontos, não apenas quando há data/valor depois.
        Isso garante que tokens como "Cidade: Mozarlândia U.F.: GO" sejam separados em:
        - "Cidade:"
        - "Mozarlândia U.F.:"
        - "GO"
        
        Args:
            span_text: Texto do span.
            bbox: Bbox normalizado.
            font_size: Tamanho da fonte.
            bold: Se é negrito.
            italic: Se é itálico.
            color: Cor do texto.
            block_id: ID do bloco.
        
        Returns:
            Lista de dicionários com tokens separados, ou lista vazia se não deve separar.
        """
        # Verificar se tem quebra de linha primeiro
        if "\n" in span_text:
            # Separar por quebra de linha
            parts = span_text.split("\n", 1)  # Dividir apenas na primeira quebra
            if len(parts) == 2:
                part1, part2 = parts[0].strip(), parts[1].strip()
                
                # Verificar se a primeira parte termina com dois pontos
                if part1.endswith(":"):
                    # Calcular bbox proporcional baseado na altura
                    # Assumir que cada parte ocupa metade da altura
                    mid_y = (bbox.y0 + bbox.y1) / 2
                    
                    return [
                        {
                            "text": part1,
                            "bbox": BBox(bbox.x0, bbox.y0, bbox.x1, mid_y),
                            "font_size": font_size,
                            "bold": bold,
                            "italic": italic,
                            "color": color,
                            "role": "LABEL"  # Token que termina com ":" é automaticamente LABEL
                        },
                        {
                            "text": part2,
                            "bbox": BBox(bbox.x0, mid_y, bbox.x1, bbox.y1),
                            "font_size": font_size,
                            "bold": bold,
                            "italic": italic,
                            "color": color,
                            "role": None  # Deixar outras regras decidirem
                        }
                    ]
        
        if ":" not in span_text or len(span_text) <= 3:
            return []
        
        # Encontrar todas as posições de ":"
        colon_positions = []
        pos = 0
        while True:
            pos = span_text.find(":", pos)
            if pos == -1:
                break
            if pos > 0 and pos < len(span_text) - 1:  # Não no início nem no fim
                colon_positions.append(pos)
            pos += 1
        
        if not colon_positions:
            return []
        
        # Se tem apenas um ":", separar e classificar automaticamente
        if len(colon_positions) == 1:
            colon_pos = colon_positions[0]
            before_colon = span_text[:colon_pos + 1].strip()
            after_colon = span_text[colon_pos + 1:].strip()
            
            # Verificar se há espaço depois dos dois pontos (padrão "texto: texto")
            if len(after_colon) == 0:
                return []  # Não separar se não há nada depois
            
            # Separar em dois tokens
            total_len = len(span_text)
            before_ratio = len(before_colon) / total_len if total_len > 0 else 0.5
            x1_first = bbox.x0 + (bbox.x1 - bbox.x0) * before_ratio
            
            return [
                {
                    "text": before_colon,
                    "bbox": BBox(bbox.x0, bbox.y0, x1_first, bbox.y1),
                    "font_size": font_size,
                    "bold": bold,
                    "italic": italic,
                    "color": color,
                    "role": "LABEL",  # Token que termina com ":" é automaticamente LABEL
                    "separated_pair": True  # Marcar como par separado
                },
                {
                    "text": after_colon,
                    "bbox": BBox(x1_first, bbox.y0, bbox.x1, bbox.y1),
                    "font_size": font_size,
                    "bold": bold,
                    "italic": italic,
                    "color": color,
                    "role": "VALUE",  # Token após ":" é automaticamente VALUE
                    "separated_pair": True  # Marcar como par separado
                }
            ]
        
        # Se tem múltiplos ":", usar regra de padrão: texto : texto : texto
        return self._separate_multiple_colons(span_text, bbox, font_size, bold, italic, color)
    
    def _separate_multiple_colons(
        self,
        span_text: str,
        bbox: BBox,
        font_size: float,
        bold: bool,
        italic: bool,
        color: str
    ) -> List[dict]:
        """Separa texto com múltiplos dois pontos usando padrão: texto : texto : texto
        
        Args:
            span_text: Texto do span com múltiplos dois pontos.
            bbox: Bbox normalizado.
            font_size: Tamanho da fonte.
            bold: Se é negrito.
            italic: Se é itálico.
            color: Cor do texto.
        
        Returns:
            Lista de dicionários com tokens separados.
        """
        # Padrão: texto : texto : texto (pode ter espaços antes/depois dos dois pontos)
        # Exemplo: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"
        # Deve separar em: ["Cidade:", "Mozarlândia", "U.F.:", "GO", "CEP:", "76709970"]
        
        tokens = []
        current_pos = 0
        current_x = bbox.x0
        bbox_width = bbox.x1 - bbox.x0
        total_chars = len(span_text)
        
        # Encontrar todas as posições de ":" com contexto
        colon_positions = []
        pos = 0
        while True:
            pos = span_text.find(":", pos)
            if pos == -1:
                break
            if pos > 0 and pos < len(span_text) - 1:
                colon_positions.append(pos)
            pos += 1
        
        # Separar em tokens: cada ":" marca o fim de um label, o texto depois é o valor
        # Padrão: texto : texto : texto
        # Exemplo: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"
        # Resultado: ["Cidade:", "Mozarlândia", "U.F.:", "GO", "CEP:", "76709970"]
        # Roles automáticos: LABEL, VALUE, LABEL, VALUE, LABEL, VALUE
        
        # Estratégia: para cada ":", separar label e valor
        # Se o valor contém espaço antes do próximo ":", separar o valor também
        for i, colon_pos in enumerate(colon_positions):
            # Token antes dos dois pontos (label) - do current_pos até o ":"
            # Se current_pos está em um espaço, precisamos pegar o texto antes do espaço também
            if current_pos < colon_pos:
                # Se current_pos está em um espaço, procurar o início da palavra antes do espaço
                if current_pos < len(span_text) and span_text[current_pos] == " ":
                    # Estamos em um espaço, procurar o início da palavra antes
                    # Exemplo: current_pos está no espaço antes de "U.F .:"
                    # Precisamos pegar "U.F .:" como label, então vamos do espaço até o ":"
                    # Mas o strip() remove o espaço, então precisamos pegar sem strip ou ajustar
                    label_text = span_text[current_pos:colon_pos + 1].strip()
                    # Se o label não começa com letra/número, pode ser que precise incluir o espaço
                    # Mas na verdade, o strip() já remove espaços, então está OK
                else:
                    label_text = span_text[current_pos:colon_pos + 1].strip()
                
                if label_text:
                    label_ratio = len(label_text) / total_chars if total_chars > 0 else 0.1
                    label_width = bbox_width * label_ratio
                    label_x1 = current_x + label_width
                    
                    tokens.append({
                        "text": label_text,
                        "bbox": BBox(current_x, bbox.y0, label_x1, bbox.y1),
                        "font_size": font_size,
                        "bold": bold,
                        "italic": italic,
                        "color": color,
                        "role": "LABEL"  # Token que termina com ":" é automaticamente LABEL
                    })
                    current_x = label_x1
                    current_pos = colon_pos + 1
            
            # Token depois dos dois pontos (valor) - até o próximo ":" ou fim
            next_colon = colon_positions[i + 1] if i + 1 < len(colon_positions) else len(span_text)
            value_start = colon_pos + 1
            value_text_raw = span_text[value_start:next_colon]
            
            # Verificar se há espaço antes do próximo ":" (indica que precisa separar o valor)
            if i + 1 < len(colon_positions):
                # Há próximo ":", verificar se há espaço antes dele no valor
                # Exemplo: "Mozarlândia U.F ." -> espaço antes de "U.F .:"
                # Precisamos encontrar o espaço que está antes de um padrão que indica um novo label
                # Padrão: espaço seguido de texto seguido de ":" (ex: " U.F .:")
                # Procurar por padrão: espaço + texto + ":" no final
                # Mas como não temos o ":" no value_text_raw, precisamos procurar de outra forma
                # Procurar por todos os espaços e verificar qual está antes de um possível label
                # Simplificando: procurar o último espaço que não está imediatamente antes de "."
                spaces = []
                for j in range(len(value_text_raw) - 1, -1, -1):
                    if value_text_raw[j] == " ":
                        # Verificar se não está imediatamente antes de "."
                        if j + 1 < len(value_text_raw) and value_text_raw[j + 1] != ".":
                            spaces.append(j)
                            if len(spaces) >= 2:  # Pegar os dois últimos espaços válidos
                                break
                
                if spaces:
                    # Usar o primeiro espaço encontrado (mais próximo do final)
                    last_space_pos = spaces[0]
                    
                    # Há espaço antes do próximo ":", separar o valor
                    # Primeira parte: até o espaço (ex: "Mozarlândia")
                    first_part = value_text_raw[:last_space_pos].strip()
                    # Segunda parte: do espaço até o próximo ":" (ex: "U.F .") - será label no próximo loop
                    
                    if first_part:
                        first_ratio = len(first_part) / total_chars if total_chars > 0 else 0.1
                        first_width = bbox_width * first_ratio
                        first_x1 = current_x + first_width
                        
                        tokens.append({
                            "text": first_part,
                            "bbox": BBox(current_x, bbox.y0, first_x1, bbox.y1),
                            "font_size": font_size,
                            "bold": bold,
                            "italic": italic,
                            "color": color,
                            "role": "VALUE"  # Valor após um LABEL é automaticamente VALUE
                        })
                        current_x = first_x1
                        # Ajustar current_pos para DEPOIS do espaço (início da segunda parte)
                        # Assim o próximo loop pegará "U.F .:" como label
                        current_pos = value_start + last_space_pos + 1
                else:
                    # Não há espaço, adicionar valor completo
                    value_text = value_text_raw.strip()
                    if value_text:
                        value_ratio = len(value_text) / total_chars if total_chars > 0 else 0.1
                        value_width = bbox_width * value_ratio
                        value_x1 = current_x + value_width
                        
                        tokens.append({
                            "text": value_text,
                            "bbox": BBox(current_x, bbox.y0, value_x1, bbox.y1),
                            "font_size": font_size,
                            "bold": bold,
                            "italic": italic,
                            "color": color,
                            "role": "VALUE"  # Valor após um LABEL é automaticamente VALUE
                        })
                        current_x = value_x1
                        current_pos = next_colon
            else:
                # Último valor, sem próximo ":"
                value_text = value_text_raw.strip()
                if value_text:
                    value_ratio = len(value_text) / total_chars if total_chars > 0 else 0.1
                    value_width = bbox_width * value_ratio
                    value_x1 = current_x + value_width
                    
                    tokens.append({
                        "text": value_text,
                        "bbox": BBox(current_x, bbox.y0, value_x1, bbox.y1),
                        "font_size": font_size,
                        "bold": bold,
                        "italic": italic,
                        "color": color,
                        "role": "VALUE"  # Último valor também é VALUE
                    })
                    current_x = value_x1
                    current_pos = next_colon
        
        # Garantir que o último token vai até o fim
        if tokens:
            tokens[-1]["bbox"] = BBox(tokens[-1]["bbox"].x0, bbox.y0, bbox.x1, bbox.y1)
        
        return tokens if len(tokens) > 1 else []
    
    def _fallback_separation(
        self,
        span_text: str,
        bbox: BBox,
        font_size: float,
        bold: bool,
        italic: bool,
        color: str
    ) -> List[dict]:
        """Separação de fallback simples (primeiro dois pontos apenas)."""
        colon_pos = span_text.find(":")
        if colon_pos <= 0 or colon_pos >= len(span_text) - 1:
            return []
        
        before_colon = span_text[:colon_pos + 1].strip()
        after_colon = span_text[colon_pos + 1:].strip()
        
        if not after_colon or not after_colon.strip():
            return []
        
        total_len = len(span_text)
        before_ratio = len(before_colon) / total_len if total_len > 0 else 0.5
        x1_first = bbox.x0 + (bbox.x1 - bbox.x0) * before_ratio
        
        return [
            {
                "text": before_colon,
                "bbox": BBox(bbox.x0, bbox.y0, x1_first, bbox.y1),
                "font_size": font_size,
                "bold": bold,
                "italic": italic,
                "color": color,
                "role": "LABEL"  # Token que termina com ":" é automaticamente LABEL
            },
            {
                "text": after_colon,
                "bbox": BBox(x1_first, bbox.y0, bbox.x1, bbox.y1),
                "font_size": font_size,
                "bold": bold,
                "italic": italic,
                "color": color,
                "role": "VALUE"  # Valor após um LABEL é automaticamente VALUE
            }
        ]

