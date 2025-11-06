"""Regras iniciais de classificação de roles."""

import re
from typing import List
from src.graph_builder.rules.base import BaseRule, RuleContext


LABEL_SEPARATORS = [":", "—", "–", ".", "•", "/"]


class InitialLabelRule(BaseRule):
    """PASSO 1: Identificar candidatos a LABEL (termina com ':' ou tem ':' no meio)."""
    
    def __init__(self):
        super().__init__(name="InitialLabelRule", priority=10)
    
    def apply(self, context: RuleContext) -> None:
        """Identifica candidatos a LABEL."""
        for token in context.tokens:
            token_id = token.id
            text = token.text.strip()
            
            if not text:
                continue
            
            # Se já tem role definido (ex: padrão múltiplos dois pontos), preservar
            existing_role = context.get_role(token_id)
            if existing_role:
                # Se é LABEL, adicionar aos candidatos
                if existing_role == "LABEL":
                    context.label_candidates.append(token_id)
                continue
            
            text_stripped = text.rstrip()
            
            # É candidato a LABEL se termina com separador OU tem ":" no meio
            ends_with_separator = any(text_stripped.endswith(sep) for sep in LABEL_SEPARATORS)
            has_colon_in_middle = token.has_colon_in_middle()
            
            if ends_with_separator or has_colon_in_middle:
                context.label_candidates.append(token_id)
                context.set_role(token_id, "LABEL", source_rule=self.name)


class InitialValueRule(BaseRule):
    """PASSO 2: Para cada LABEL, procurar VALUE à direita (east) ou abaixo (south)."""
    
    def __init__(self):
        super().__init__(name="InitialValueRule", priority=20, dependencies=["InitialLabelRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Procura VALUES para cada LABEL."""
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for label_id in context.label_candidates:
            # Se já tem um VALUE associado (ex: padrão múltiplos dois pontos), pular
            if label_id in context.label_to_value:
                continue
            
            # Procurar VALUE à direita (east) primeiro, depois abaixo (south)
            for direction in ["east", "south"]:
                neighbors = context.adjacency.get_neighbors(label_id, direction)
                
                for neighbor_id in neighbors:
                    # Se este VALUE já está ligado a outro LABEL, pular
                    if neighbor_id in context.value_to_label:
                        continue
                    
                    neighbor_token = context.get_node_by_id(neighbor_id)
                    if not neighbor_token:
                        continue
                    
                    # Se já tem role definido como VALUE (ex: padrão múltiplos dois pontos), usar
                    neighbor_role = context.get_role(neighbor_id)
                    if neighbor_role == "VALUE":
                        context.label_to_value[label_id] = neighbor_id
                        context.value_to_label[neighbor_id] = label_id
                        break
                    
                    neighbor_text = neighbor_token.text.strip()
                    if not neighbor_text:
                        continue
                    
                    # Verificar se é um VALUE válido
                    is_number = neighbor_token.is_number()
                    is_date = bool(date_pattern.search(neighbor_text))
                    has_digits = bool(re.search(r"\d", neighbor_text))
                    tokens_list = neighbor_text.split()
                    is_long_text = len(tokens_list) >= 2
                    
                    # Não é VALUE se termina com separador (é LABEL)
                    ends_with_sep = neighbor_token.ends_with_separator(LABEL_SEPARATORS)
                    
                    if (is_number or is_date or (has_digits and not ends_with_sep) or is_long_text) and not ends_with_sep:
                        # Encontrou um VALUE válido
                        context.label_to_value[label_id] = neighbor_id
                        context.value_to_label[neighbor_id] = label_id
                        context.set_role(neighbor_id, "VALUE", source_rule=self.name)
                        break
                
                # Se já encontrou um VALUE para este LABEL, parar
                if label_id in context.label_to_value:
                    break


class InitialHeaderRule(BaseRule):
    """PASSO 3: Classificar tokens restantes como HEADER."""
    
    def __init__(self):
        super().__init__(name="InitialHeaderRule", priority=30, dependencies=["InitialValueRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Classifica tokens restantes."""
        # Calcular estatísticas de fonte
        font_sizes = [t.font_size for t in context.tokens if t.font_size and t.font_size > 0]
        if not font_sizes:
            avg_font_size = 12.0
        else:
            avg_font_size = sum(font_sizes) / len(font_sizes)
        
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for token in context.tokens:
            token_id = token.id
            
            # Se já foi classificado, pular
            if context.get_role(token_id) is not None:
                continue
            
            text = token.text.strip()
            if not text:
                continue
            
            # Verificar conexões do token
            all_neighbors = context.adjacency.get_all_neighbors(token_id)
            
            neighbor_roles = []
            for neighbor_id in all_neighbors:
                neighbor_role = context.get_role(neighbor_id)
                if neighbor_role:
                    neighbor_roles.append(neighbor_role)
            
            # Se só se conecta a LABELs, é HEADER
            if neighbor_roles and all(role == "LABEL" for role in neighbor_roles):
                context.set_role(token_id, "HEADER")
                continue
            
            # Verificar se tem cor branca (pode indicar HEADER em fundo escuro)
            is_white_color = False
            if token.color:
                color_lower = token.color.lower()
                # Verificar se é branco: #ffffff, #FFFFFF, ou valor RGB alto
                if color_lower in ("#ffffff", "#fff", "white"):
                    is_white_color = True
                elif color_lower.startswith("#"):
                    try:
                        # Converter hex para RGB
                        rgb = int(color_lower[1:], 16)
                        r = (rgb >> 16) & 0xFF
                        g = (rgb >> 8) & 0xFF
                        b = rgb & 0xFF
                        # Considerar branco se todos os componentes são > 240
                        if r > 240 and g > 240 and b > 240:
                            is_white_color = True
                    except:
                        pass
            
            # Verificar se deveria ser HEADER (fonte grande no topo OU cor branca OU isolado)
            if token.font_size and token.font_size > 0:
                y_top = token.bbox.y0
                is_near_top = y_top < 0.20
                is_large_font = token.font_size >= avg_font_size * 1.2
                is_above_avg = token.font_size > avg_font_size
                tokens_list = text.split()
                
                # Se tem cor branca e não é VALUE/LABEL, pode ser HEADER
                if is_white_color:
                    ends_with_separator = token.ends_with_separator(LABEL_SEPARATORS)
                    if not ends_with_separator and not token.is_number() and not token.is_date():
                        context.set_role(token_id, "HEADER")
                        continue
                
                if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                    text_stripped = text.rstrip()
                    ends_with_separator = token.ends_with_separator(LABEL_SEPARATORS)
                    if not ends_with_separator and not token.is_number():
                        context.set_role(token_id, "HEADER")
                        continue
            
            # ANTES de verificar VALUE, verificar se pode ser HEADER
            # Tokens isolados ou com poucas conexões que são texto curto devem ser HEADER primeiro
            ends_with_separator = token.ends_with_separator(LABEL_SEPARATORS)
            is_number = token.is_number()
            is_date = token.is_date()
            has_digits = bool(re.search(r"\d", text))
            tokens_list = text.split()
            is_short_text = len(tokens_list) <= 2
            is_pure_text = not has_digits and not is_number and not is_date
            
            # Se não tem conexões ou tem poucas conexões e não é VALUE/LABEL, pode ser HEADER
            if (not all_neighbors or len(all_neighbors) <= 1) and is_pure_text and is_short_text and not ends_with_separator:
                y_center = token.bbox.center_y()
                # Se está na metade superior da página (y < 0.5) OU é um token isolado (poucas conexões)
                # Tokens isolados com texto curto são frequentemente HEADERs
                if y_center < 0.5 or len(all_neighbors) == 0:
                    context.set_role(token_id, "HEADER")
                    continue
                # Se tem apenas 1 conexão e é texto curto sem dígitos, também pode ser HEADER
                elif len(all_neighbors) == 1:
                    # Verificar se a conexão é de cima (south) - se sim, pode ser HEADER de seção
                    single_neighbor = all_neighbors[0]
                    single_neighbor_token = context.get_node_by_id(single_neighbor)
                    if single_neighbor_token:
                        # Se o vizinho está acima (north), este token pode ser HEADER
                        neighbor_y = single_neighbor_token.bbox.center_y()
                        if neighbor_y < y_center:
                            # Vizinho está acima, este pode ser HEADER de uma nova seção
                            context.set_role(token_id, "HEADER")
                            continue
                    # Se não conseguiu verificar posição, mas é texto curto isolado, também pode ser HEADER
                    # Especialmente se está em uma posição que sugere seção (meio da página)
                    if 0.3 < y_center < 0.9:
                        context.set_role(token_id, "HEADER")
                        continue
            
            # Verificar se é VALUE (número, data, ou tem dígitos)
            # MAS: não classificar como VALUE se é texto puro curto isolado (pode ser HEADER)
            is_long_text = len(tokens_list) >= 2
            ends_with_sep = token.ends_with_separator(LABEL_SEPARATORS)
            
            # Não classificar como VALUE se é texto puro curto isolado (já verificado acima como HEADER)
            is_isolated_short_text = (not all_neighbors or len(all_neighbors) <= 1) and is_pure_text and is_short_text and not ends_with_separator
            
            # Só classificar como VALUE se:
            # 1. É número, data, tem dígitos OU é texto longo
            # 2. NÃO é texto isolado curto (que pode ser HEADER)
            # 3. NÃO está conectado a um LABEL
            if (is_number or is_date or (has_digits and not ends_with_sep) or is_long_text) and not ends_with_sep:
                # Mas só classificar como VALUE se não está conectado a um LABEL já
                # E se não é um texto isolado curto (que pode ser HEADER)
                if token_id not in context.value_to_label and not is_isolated_short_text:
                    # Verificar se está conectado a algum LABEL
                    connected_to_label = False
                    for neighbor_id in all_neighbors:
                        if neighbor_id in context.label_candidates:
                            connected_to_label = True
                            break
                    
                    if not connected_to_label:
                        # Só classificar como VALUE se realmente é um valor (não texto curto isolado)
                        # Texto curto isolado sem dígitos deve ser HEADER, não VALUE
                        if is_long_text or has_digits or is_number or is_date:
                            context.set_role(token_id, "VALUE")
                            continue
            
            # Se não se encaixa em nenhuma categoria, deixar None por enquanto
            context.set_role(token_id, None)


class LabelOnlyConnectionsRule(BaseRule):
    """PASSO 4: Revisar - se um LABEL está conectado apenas a LABELs, é HEADER."""
    
    def __init__(self):
        super().__init__(name="LabelOnlyConnectionsRule", priority=40, dependencies=["InitialHeaderRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Revisa LABELs conectados apenas a LABELs."""
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            # Se é LABEL, verificar se está conectado apenas a LABELs
            if current_role == "LABEL":
                east_neighbors = context.adjacency.get_neighbors(token_id, "east")
                south_neighbors = context.adjacency.get_neighbors(token_id, "south")
                
                all_connected_are_labels = True
                for neighbor_id in east_neighbors + south_neighbors:
                    neighbor_role = context.get_role(neighbor_id)
                    if neighbor_role != "LABEL":
                        all_connected_are_labels = False
                        break
                
                if all_connected_are_labels and (east_neighbors or south_neighbors):
                    # Se está conectado apenas a LABELs, é HEADER
                    context.set_role(token_id, "HEADER")
                    if token_id in context.label_candidates:
                        context.label_candidates.remove(token_id)

