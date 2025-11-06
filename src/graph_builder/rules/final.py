"""Regras finais de classificação de roles (Passagens FINAL 1-10)."""

import re
from typing import List, Set, Optional, Tuple
from src.graph_builder.rules.base import BaseRule, RuleContext
from src.graph_builder.models import Token
from src.graph_builder.adjacency import AdjacencyMatrix

LABEL_SEPARATORS = [":", "—", "–", ".", "•", "/"]


class HeaderPreservationRule(BaseRule):
    """Passagem FINAL 1: Garantir que HEADER não foi sobrescrito."""
    
    def __init__(self):
        super().__init__(name="HeaderPreservationRule", priority=50)
    
    def apply(self, context: RuleContext) -> None:
        """Garante que HEADERs no topo com fonte grande não foram sobrescritos."""
        # Calcular estatísticas de fonte
        font_sizes = [t.font_size for t in context.tokens if t.font_size and t.font_size > 0]
        if not font_sizes:
            avg_font_size = 12.0
        else:
            avg_font_size = sum(font_sizes) / len(font_sizes)
        
        for token in context.tokens:
            token_id = token.id
            text = token.text.strip()
            current_role = context.get_role(token_id)
            
            if not text:
                continue
            
            if token.font_size and token.font_size > 0:
                y_top = token.bbox.y0
                is_near_top = y_top < 0.20
                is_large_font = token.font_size >= avg_font_size * 1.2
                is_above_avg = token.font_size > avg_font_size
                tokens_list = text.split()
                
                # Se está no topo e tem fonte maior que média, DEVE ser HEADER
                if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                    text_stripped = text.rstrip()
                    ends_with_separator = token.ends_with_separator(LABEL_SEPARATORS)
                    if not ends_with_separator and not token.is_number():
                        # Se não é HEADER, forçar HEADER
                        if current_role != "HEADER":
                            context.set_role(token_id, "HEADER")


class ValueLabelUniquenessRule(BaseRule):
    """Passagem FINAL 2: Garantir que todo VALUE tem LABEL (OBRIGATÓRIO E ÚNICO)."""
    
    def __init__(self):
        super().__init__(name="ValueLabelUniquenessRule", priority=60)
    
    def apply(self, context: RuleContext) -> None:
        """Garante que todo VALUE tem um LABEL único acima ou à esquerda."""
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            token_text = token.text.strip()
            
            is_date = bool(date_pattern.search(token_text))
            is_value = current_role == "VALUE"
            
            if is_value or is_date:
                if is_date and not is_value:
                    context.set_role(token_id, "VALUE")
                    current_role = "VALUE"
                
                if token_id not in context.value_to_label:
                    # Procurar tokens acima ou à esquerda
                    candidates_above = []
                    candidates_left = []
                    
                    value_bbox = token.bbox
                    value_center_x = value_bbox.center_x()
                    value_center_y = value_bbox.center_y()
                    
                    for other_token in context.tokens:
                        other_id = other_token.id
                        if other_id == token_id:
                            continue
                        
                        other_bbox = other_token.bbox
                        other_role = context.get_role(other_id)
                        other_text = other_token.text.strip()
                        
                        # Verificar se é texto puro
                        if not other_token.is_text_only():
                            continue
                        
                        # Verificar se está acima (north)
                        x_overlap = not (other_bbox.x1 < value_bbox.x0 or other_bbox.x0 > value_bbox.x1)
                        is_above = other_bbox.y1 < value_bbox.y0
                        
                        if is_above and x_overlap:
                            vertical_distance = value_bbox.y0 - other_bbox.y1
                            horizontal_distance = abs(other_bbox.center_x() - value_center_x)
                            candidates_above.append((
                                other_id, other_token, other_role, other_text,
                                vertical_distance, horizontal_distance
                            ))
                        
                        # Verificar se está à esquerda (west)
                        y_overlap = not (other_bbox.y1 < value_bbox.y0 or other_bbox.y0 > value_bbox.y1)
                        is_left = other_bbox.x1 < value_bbox.x0
                        
                        if is_left and y_overlap and not is_above:
                            horizontal_distance = value_bbox.x0 - other_bbox.x1
                            vertical_distance = abs(other_bbox.center_y() - value_center_y)
                            candidates_left.append((
                                other_id, other_token, other_role, other_text,
                                horizontal_distance, vertical_distance
                            ))
                    
                    # Escolher melhor candidato (priorizar acima sobre esquerda)
                    best_candidate = None
                    if candidates_above:
                        # Priorizar: menor distância vertical, menor distância horizontal
                        best_candidate = min(candidates_above, key=lambda c: (c[4], c[5]))
                    elif candidates_left:
                        # Priorizar: menor distância horizontal, menor distância vertical
                        best_candidate = min(candidates_left, key=lambda c: (c[4], c[5]))
                    
                    if best_candidate:
                        candidate_id, candidate_token, candidate_role, candidate_text, _, _ = best_candidate
                        is_date_candidate = bool(date_pattern.search(candidate_text))
                        is_number_candidate = candidate_token.is_number()
                        
                        if candidate_role == "LABEL":
                            # Já é LABEL, criar ligação
                            context.label_to_value[candidate_id] = token_id
                            context.value_to_label[token_id] = candidate_id
                        elif (candidate_role is None or candidate_role == "") and not is_date_candidate and not is_number_candidate:
                            # Classificar como LABEL
                            context.set_role(candidate_id, "LABEL")
                            if candidate_id not in context.label_candidates:
                                context.label_candidates.append(candidate_id)
                            context.label_to_value[candidate_id] = token_id
                            context.value_to_label[token_id] = candidate_id
                        elif candidate_role == "VALUE" and not is_date_candidate and not is_number_candidate:
                            # Reclassificar: text token acima/left de VALUE/date deve ser LABEL
                            context.set_role(candidate_id, "LABEL")
                            if candidate_id not in context.label_candidates:
                                context.label_candidates.append(candidate_id)
                            context.label_to_value[candidate_id] = token_id
                            context.value_to_label[token_id] = candidate_id


class TypographicHierarchyRule(BaseRule):
    """Passagem FINAL 3: Propagação de roles por hierarquia tipográfica."""
    
    def __init__(self):
        super().__init__(name="TypographicHierarchyRule", priority=70, dependencies=["ValueLabelUniquenessRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Propaga roles para tokens na mesma linha com estilo similar."""
        Y_TOLERANCE_SAME_LINE = 0.01
        FONT_SIZE_TOLERANCE = 1.0
        
        # Agrupar tokens por linha e estilo
        line_style_groups = {}
        
        for token in context.tokens:
            token_id = token.id
            y_center = token.bbox.center_y()
            font_size = token.font_size or 0
            bold = token.bold
            italic = token.italic
            color = token.color
            
            y_rounded = round(y_center / Y_TOLERANCE_SAME_LINE) * Y_TOLERANCE_SAME_LINE
            font_base = round(font_size / FONT_SIZE_TOLERANCE) * FONT_SIZE_TOLERANCE if font_size > 0 else 0
            
            # Tentar encontrar grupo existente com font size dentro da tolerância
            found_group = False
            for (group_y, group_font, group_bold, group_italic, group_color), group_tokens in line_style_groups.items():
                if (group_y == y_rounded and group_bold == bold and 
                    group_italic == italic and group_color == color):
                    if abs(font_size - group_font) <= FONT_SIZE_TOLERANCE:
                        group_tokens.append(token_id)
                        found_group = True
                        break
            
            if not found_group:
                key = (y_rounded, font_base, bold, italic, color)
                if key not in line_style_groups:
                    line_style_groups[key] = []
                line_style_groups[key].append(token_id)
        
        # Processar cada grupo
        for (group_y, group_font, group_bold, group_italic, group_color), token_ids in line_style_groups.items():
            if len(token_ids) < 2:
                continue
            
            # Ordenar tokens por X
            tokens_with_x = [(tid, context.get_node_by_id(tid)) for tid in token_ids]
            tokens_with_x = [(tid, t) for tid, t in tokens_with_x if t is not None]
            tokens_with_x.sort(key=lambda x: x[1].bbox.x0)
            
            # Coletar roles
            group_roles = {}
            for tid, token_obj in tokens_with_x:
                role = context.get_role(tid)
                if role:
                    group_roles[role] = group_roles.get(role, 0) + 1
            
            if not group_roles:
                continue
            
            # Role dominante
            has_header = "HEADER" in group_roles
            dominant_role = "HEADER" if has_header else max(group_roles.items(), key=lambda x: x[1])[0]
            
            # Verificar edges east e propagar roles
            for i in range(len(tokens_with_x) - 1):
                token1_id, token1_obj = tokens_with_x[i]
                token2_id, token2_obj = tokens_with_x[i + 1]
                
                token1_role = context.get_role(token1_id)
                token2_role = context.get_role(token2_id)
                
                # Verificar se há edge east
                has_east_edge = context.adjacency.has_connection(token1_id, token2_id, "east")
                
                if has_east_edge and token1_role:
                    if token2_role != "HEADER":
                        if token1_role in ("LABEL", "VALUE", "HEADER"):
                            token2_text = token2_obj.text.strip()
                            date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
                            is_date = bool(date_pattern.search(token2_text))
                            is_number = token2_obj.is_number()
                            
                            # Verificar se token2 é código numérico
                            is_numeric_code_token2 = token2_obj.is_numeric_code() and not is_date
                            
                            if is_date or is_number:
                                if token1_role == "LABEL":
                                    context.set_role(token2_id, "VALUE")
                            elif is_numeric_code_token2:
                                # Token2 é código numérico, não propagar LABEL
                                if token1_role == "LABEL":
                                    context.set_role(token2_id, "VALUE")
                            else:
                                # Token2 não é código numérico, pode propagar role
                                if token1_role == "LABEL":
                                    if token2_role is None or token2_role == "" or token2_role == "VALUE" or (token2_role != "HEADER"):
                                        context.set_role(token2_id, "LABEL")
                                        if token2_id not in context.label_candidates:
                                            context.label_candidates.append(token2_id)
                                elif token1_role == "VALUE":
                                    if token2_role is None or token2_role == "":
                                        context.set_role(token2_id, "VALUE")
                                elif token1_role == "HEADER":
                                    if token2_role is None or token2_role == "":
                                        context.set_role(token2_id, "HEADER")


class NumericCodeLabelRule(BaseRule):
    """Passagem FINAL 4: Detecção de código numérico e classificação de LABELs adjacentes."""
    
    def __init__(self):
        super().__init__(name="NumericCodeLabelRule", priority=80, dependencies=["TypographicHierarchyRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Detecta códigos numéricos e classifica tokens adjacentes como LABEL."""
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for token in context.tokens:
            token_id = token.id
            token_text = token.text.strip()
            
            if not token_text:
                continue
            
            if not token.is_numeric_code():
                continue
            
            # Token é código numérico, procurar tokens adjacentes que são só texto
            candidates = []
            
            # 1. Verificar token acima (north)
            north_neighbors = context.adjacency.get_neighbors(token_id, "north")
            for neighbor_id in north_neighbors:
                neighbor_token = context.get_node_by_id(neighbor_id)
                if not neighbor_token:
                    continue
                
                neighbor_text = neighbor_token.text.strip()
                if date_pattern.search(neighbor_text):
                    continue
                
                if neighbor_token.is_text_only():
                    neighbor_role = context.get_role(neighbor_id)
                    if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                        candidates.append((neighbor_id, "north", neighbor_token))
            
            # 2. Verificar token à esquerda (west)
            west_neighbors = context.adjacency.get_neighbors(token_id, "west")
            for neighbor_id in west_neighbors:
                neighbor_token = context.get_node_by_id(neighbor_id)
                if not neighbor_token:
                    continue
                
                neighbor_text = neighbor_token.text.strip()
                if date_pattern.search(neighbor_text):
                    continue
                
                if neighbor_token.is_text_only():
                    neighbor_role = context.get_role(neighbor_id)
                    if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                        candidates.append((neighbor_id, "west", neighbor_token))
            
            # 3. Verificar token à direita (east)
            east_neighbors = context.adjacency.get_neighbors(token_id, "east")
            for neighbor_id in east_neighbors:
                neighbor_token = context.get_node_by_id(neighbor_id)
                if not neighbor_token:
                    continue
                
                neighbor_text = neighbor_token.text.strip()
                if date_pattern.search(neighbor_text):
                    continue
                
                if neighbor_token.is_text_only():
                    neighbor_role = context.get_role(neighbor_id)
                    if neighbor_role is None or neighbor_role == "" or neighbor_role == "VALUE":
                        candidates.append((neighbor_id, "east", neighbor_token))
            
            # Ordenar por prioridade: north > west > east
            if candidates:
                priority_order = {"north": 0, "west": 1, "east": 2}
                candidates.sort(key=lambda x: priority_order.get(x[1], 99))
                
                best_candidate_id, best_direction, best_neighbor = candidates[0]
                current_role = context.get_role(best_candidate_id)
                
                if current_role == "VALUE":
                    context.set_role(best_candidate_id, "LABEL")
                elif current_role is None or current_role == "":
                    context.set_role(best_candidate_id, "LABEL")
                
                if best_candidate_id not in context.label_candidates:
                    context.label_candidates.append(best_candidate_id)
                
                context.label_to_value[best_candidate_id] = token_id
                context.value_to_label[token_id] = best_candidate_id
                
                # Garantir que o token de código numérico seja VALUE
                context.set_role(token_id, "VALUE")
                
                if token_id in context.label_candidates:
                    context.label_candidates.remove(token_id)


class DateLabelCleanupRule(BaseRule):
    """Passagem FINAL 5: Limpeza - remover classificação LABEL incorreta de tokens adjacentes apenas a datas."""
    
    def __init__(self):
        super().__init__(name="DateLabelCleanupRule", priority=90, dependencies=["NumericCodeLabelRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Remove classificação LABEL incorreta de tokens adjacentes apenas a datas."""
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            if current_role == "LABEL":
                all_neighbors = context.adjacency.get_all_neighbors(token_id)
                
                has_numeric_code_neighbor = False
                has_date_neighbor = False
                
                for neighbor_id in all_neighbors:
                    neighbor_token = context.get_node_by_id(neighbor_id)
                    if not neighbor_token:
                        continue
                    
                    neighbor_text = neighbor_token.text.strip()
                    if date_pattern.search(neighbor_text):
                        has_date_neighbor = True
                    elif neighbor_token.is_numeric_code():
                        has_numeric_code_neighbor = True
                
                if has_date_neighbor and not has_numeric_code_neighbor:
                    token_text = token.text.strip()
                    ends_with_separator = token.ends_with_separator(LABEL_SEPARATORS)
                    has_colon_in_middle = token.has_colon_in_middle()
                    
                    is_linked_to_date = False
                    for neighbor_id in all_neighbors:
                        if neighbor_id in context.value_to_label and context.value_to_label[neighbor_id] == token_id:
                            neighbor_token = context.get_node_by_id(neighbor_id)
                            if neighbor_token:
                                neighbor_text = neighbor_token.text.strip()
                                if date_pattern.search(neighbor_text):
                                    is_linked_to_date = True
                                    break
                    
                    if not ends_with_separator and not has_colon_in_middle and not is_linked_to_date:
                        if token_id in context.label_candidates:
                            context.label_candidates.remove(token_id)
                        context.set_role(token_id, None)


class LabelWithoutEdgesRule(BaseRule):
    """Passagem FINAL 6: Reclassificar LABELs sem edges como HEADER."""
    
    def __init__(self):
        super().__init__(name="LabelWithoutEdgesRule", priority=100)
    
    def apply(self, context: RuleContext) -> None:
        """Reclassifica LABELs sem edges como HEADER."""
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            if current_role == "LABEL":
                has_edges = len(context.graph.get_edges_connected(token_id)) > 0
                
                if not has_edges:
                    context.set_role(token_id, "HEADER")
                    if token_id in context.label_candidates:
                        context.label_candidates.remove(token_id)


class IsolatedShortTextHeaderRule(BaseRule):
    """Regra: Tokens isolados com texto curto devem ser HEADER, não VALUE."""
    
    def __init__(self):
        super().__init__(name="IsolatedShortTextHeaderRule", priority=105, dependencies=["LabelWithoutEdgesRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Reclassifica tokens isolados com texto curto de VALUE para HEADER."""
        import re
        from src.graph_builder.rules.initial import LABEL_SEPARATORS
        
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            # Se já é HEADER, pular
            if current_role == "HEADER":
                continue
            
            # Se é VALUE ou None, verificar se deveria ser HEADER
            if current_role in ("VALUE", None):
                text = token.text.strip()
                if not text:
                    continue
                
                # Verificar se é texto curto isolado
                all_neighbors = context.adjacency.get_all_neighbors(token_id)
                tokens_list = text.split()
                is_short_text = len(tokens_list) <= 2
                has_digits = bool(re.search(r"\d", text))
                is_number = token.is_number()
                is_date = token.is_date()
                is_pure_text = not has_digits and not is_number and not is_date
                ends_with_sep = token.ends_with_separator(LABEL_SEPARATORS)
                
                # Se é texto puro curto isolado, deve ser HEADER
                if ((not all_neighbors or len(all_neighbors) <= 1) and 
                    is_pure_text and is_short_text and not ends_with_sep):
                    y_center = token.bbox.center_y()
                    # Se está em posição que sugere HEADER (não muito no final)
                    if y_center < 0.95:
                        context.set_role(token_id, "HEADER", source_rule=self.name)
                        # Se estava como VALUE, remover de value_to_label e label_to_value
                        if token_id in context.value_to_label:
                            old_label_id = context.value_to_label[token_id]
                            if old_label_id in context.label_to_value:
                                del context.label_to_value[old_label_id]
                            del context.value_to_label[token_id]
                        if token_id in context.label_to_value:
                            old_value_id = context.label_to_value[token_id]
                            if old_value_id in context.value_to_label:
                                del context.value_to_label[old_value_id]
                            del context.label_to_value[token_id]


class ValueLabelGuaranteeRule(BaseRule):
    """Passagem FINAL 7: Garantir que tokens de texto acima de VALUE/datas sejam LABEL."""
    
    def __init__(self):
        super().__init__(name="ValueLabelGuaranteeRule", priority=110)
    
    def apply(self, context: RuleContext) -> None:
        """Garante que tokens acima de VALUE/datas sejam LABEL."""
        date_pattern = re.compile(r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}")
        
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            token_text = token.text.strip()
            
            is_date = bool(date_pattern.search(token_text))
            is_value = current_role == "VALUE"
            
            if is_value or is_date:
                if is_date and not is_value:
                    context.set_role(token_id, "VALUE")
                    current_role = "VALUE"
                
                if token_id not in context.value_to_label:
                    # Procurar tokens acima
                    value_bbox = token.bbox
                    
                    for other_token in context.tokens:
                        other_id = other_token.id
                        if other_id == token_id:
                            continue
                        
                        other_bbox = other_token.bbox
                        other_role = context.get_role(other_id)
                        other_text = other_token.text.strip()
                        
                        if not other_token.is_text_only():
                            continue
                        
                        x_overlap = not (other_bbox.x1 < value_bbox.x0 or other_bbox.x0 > value_bbox.x1)
                        is_above = other_bbox.y1 < value_bbox.y0
                        
                        if is_above and x_overlap:
                            is_date_neighbor = bool(date_pattern.search(other_text))
                            is_number_neighbor = other_token.is_number()
                            
                            if not is_date_neighbor and not is_number_neighbor:
                                if other_role is None or other_role == "" or other_role == "VALUE":
                                    context.set_role(other_id, "LABEL")
                                    if other_id not in context.label_candidates:
                                        context.label_candidates.append(other_id)
                                    context.label_to_value[other_id] = token_id
                                    context.value_to_label[token_id] = other_id
                                    break


class ColonRecursiveRule(BaseRule):
    """Passagem FINAL 8: Regra recursiva para tokens que terminam com dois pontos."""
    
    def __init__(self):
        super().__init__(name="ColonRecursiveRule", priority=120)
    
    def apply(self, context: RuleContext) -> None:
        """Aplica regra recursiva para tokens que terminam com ':'."""
        def find_value_recursive(token_id: int, visited: Set[int]) -> Optional[int]:
            """Encontra recursivamente um VALUE seguindo edges south/east."""
            if token_id in visited:
                return None
            
            visited.add(token_id)
            token_obj = context.get_node_by_id(token_id)
            if not token_obj:
                return None
            
            if not token_obj.ends_with_colon():
                return token_id
            
            # Se termina com ":", seguir pelos edges south e east
            for direction in ["south", "east"]:
                neighbors = context.adjacency.get_neighbors(token_id, direction)
                for neighbor_id in neighbors:
                    result = find_value_recursive(neighbor_id, visited.copy())
                    if result is not None:
                        return result
            
            return None
        
        # Para cada token que termina com ":", encontrar seu VALUE recursivamente
        for token in context.tokens:
            token_id = token.id
            
            if not token.ends_with_colon():
                continue
            
            value_id = find_value_recursive(token_id, set())
            
            if value_id is not None:
                context.set_role(token_id, "LABEL")
                if token_id not in context.label_candidates:
                    context.label_candidates.append(token_id)
                
                value_role = context.get_role(value_id)
                value_token = context.get_node_by_id(value_id)
                value_text = value_token.text.strip() if value_token else ""
                
                if not value_text.endswith(":"):
                    context.set_role(value_id, "VALUE")
                    context.label_to_value[token_id] = value_id
                    context.value_to_label[value_id] = token_id
                    
                    if value_id in context.label_candidates:
                        context.label_candidates.remove(value_id)


class HeaderNoNorthWestRule(BaseRule):
    """REGRA DE PRIORIDADE MÁXIMA: HEADERs não podem ter conexões para cima (north) ou esquerda (west).
    
    Esta regra REMOVE edges, não apenas reclassifica. É uma regra que nunca pode ser quebrada.
    Deve ser executada no FINAL, após todas as classificações, para garantir que todos os HEADERs
    sejam verificados.
    """
    
    def __init__(self):
        super().__init__(
            name="HeaderNoNorthWestRule", 
            priority=250,  # Prioridade muito alta - executar no final
            dependencies=["HeaderNoNorthRule", "LabelSingleValueRule"]  # Executar depois de todas as outras
        )
    
    def apply(self, context: RuleContext) -> None:
        """Remove edges de HEADER para north/west e reclassifica se necessário.
        
        Esta regra verifica TODOS os tokens que são HEADER (no contexto ou no token original)
        e remove edges inválidas. Também verifica tokens que TÊM edges para cima/esquerda
        e os reclassifica se necessário.
        """
        edges_to_remove = []
        
        # Primeiro, identificar todos os HEADERs
        header_tokens = []
        for token in context.tokens:
            token_id = token.id
            # Verificar role no contexto (pode ter sido definido por outras regras)
            current_role = context.get_role(token_id)
            
            # Também verificar role original do token (definido durante extração)
            token_obj = context.get_node_by_id(token_id)
            if token_obj and token_obj.role:
                # Se o token tem role original, usar ele (tem prioridade)
                current_role = token_obj.role
            
            if current_role == "HEADER":
                header_tokens.append(token_id)
        
        # Agora verificar e remover edges inválidas de HEADERs
        for token_id in header_tokens:
            token = context.get_node_by_id(token_id)
            if not token:
                continue
            
            # Verificar e remover edges north/west
            for edge in list(context.graph.edges):  # Usar list() para evitar modificar durante iteração
                # Edge saindo do HEADER para north/west
                if edge.from_id == token_id and edge.relation in ("north", "west"):
                    edges_to_remove.append(edge)
                # Edge chegando no HEADER de south/east (reverso) - isso significa conexão vinda de cima/esquerda
                elif edge.to_id == token_id and edge.relation in ("south", "east"):
                    # Verificar se o token de origem é um HEADER também
                    from_token = context.get_node_by_id(edge.from_id)
                    if from_token:
                        from_role = from_token.role if from_token.role else context.get_role(edge.from_id)
                        if from_role == "HEADER":
                            # Não remover se ambos são HEADERs (pode ser conexão horizontal entre HEADERs)
                            continue
                    # Remover edge - HEADER não pode ter conexão vinda de cima (south) ou esquerda (east)
                    edges_to_remove.append(edge)
        
        # Também verificar tokens que TÊM edges para cima/esquerda mas não são HEADER
        # Se um token tem edge vindo de cima/esquerda e não é VALUE/LABEL, pode ser que deveria ser HEADER
        # mas foi classificado incorretamente. Nesse caso, remover a edge inválida.
        for edge in list(context.graph.edges):
            # Edge chegando em um token de south/east (vindo de cima/esquerda)
            if edge.relation in ("south", "east"):
                to_token_id = edge.to_id
                to_token = context.get_node_by_id(to_token_id)
                if not to_token:
                    continue
                
                to_role = to_token.role if to_token.role else context.get_role(to_token_id)
                
                # Se o token de destino é HEADER, remover a edge (já tratado acima, mas garantir)
                if to_role == "HEADER":
                    from_token = context.get_node_by_id(edge.from_id)
                    if from_token:
                        from_role = from_token.role if from_token.role else context.get_role(edge.from_id)
                        if from_role != "HEADER":
                            # HEADER não pode ter conexão vinda de não-HEADER
                            if edge not in edges_to_remove:
                                edges_to_remove.append(edge)
        
        # Remover edges primeiro
        for edge in edges_to_remove:
            if edge in context.graph.edges:
                context.graph.edges.remove(edge)
            # Também remover edge reversa se existir
            reverse_edge = edge.reverse()
            if reverse_edge in context.graph.edges:
                context.graph.edges.remove(reverse_edge)
        
        # Atualizar adjacency após remover edges
        context.adjacency = AdjacencyMatrix(context.graph)
        
        # Agora, se algum HEADER ainda tem conexões north/west após remoção, reclassificar
        for token_id in header_tokens:
            token = context.get_node_by_id(token_id)
            if not token:
                continue
            
            # Verificar se ainda tem conexões north/west (após remoção)
            north_neighbors = context.adjacency.get_neighbors(token_id, "north")
            west_neighbors = context.adjacency.get_neighbors(token_id, "west")
            
            if north_neighbors or west_neighbors:
                token_text = token.text.strip()
                
                if token.ends_with_colon():
                    context.set_role(token_id, "LABEL", source_rule=self.name)
                    if token_id not in context.label_candidates:
                        context.label_candidates.append(token_id)
                else:
                    if token.is_date() or token.is_number() or token.is_numeric_code():
                        context.set_role(token_id, "VALUE", source_rule=self.name)
                    else:
                        # Verificar se tem conexões south/east que são LABELs
                        has_label_connections = False
                        south_neighbors = context.adjacency.get_neighbors(token_id, "south")
                        east_neighbors = context.adjacency.get_neighbors(token_id, "east")
                        
                        for neighbor_id in south_neighbors + east_neighbors:
                            neighbor_token = context.get_node_by_id(neighbor_id)
                            neighbor_role = neighbor_token.role if neighbor_token and neighbor_token.role else context.get_role(neighbor_id)
                            if neighbor_role == "LABEL":
                                has_label_connections = True
                                break
                        
                        if has_label_connections:
                            context.set_role(token_id, "VALUE", source_rule=self.name)
                        else:
                            context.set_role(token_id, "LABEL", source_rule=self.name)
                            if token_id not in context.label_candidates:
                                context.label_candidates.append(token_id)
        
        # Remover edges
        for edge in edges_to_remove:
            if edge in context.graph.edges:
                context.graph.edges.remove(edge)
            # Também remover edge reversa se existir
            reverse_edge = edge.reverse()
            if reverse_edge in context.graph.edges:
                context.graph.edges.remove(reverse_edge)
        
        # Atualizar adjacency após remover edges
        context.adjacency = AdjacencyMatrix(context.graph)


class HeaderNoNorthRule(BaseRule):
    """Passagem FINAL 9: HEADERs não devem ter conexões verticais para cima (north)."""
    
    def __init__(self):
        super().__init__(name="HeaderNoNorthRule", priority=130)
    
    def apply(self, context: RuleContext) -> None:
        """Reclassifica HEADERs com conexões north."""
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            if current_role != "HEADER":
                continue
            
            # Verificar se tem conexões north
            has_north_connections = False
            north_neighbors = context.adjacency.get_neighbors(token_id, "north")
            
            # Também verificar edges reversos
            for edge in context.graph.edges:
                if edge.to_id == token_id and edge.relation == "south":
                    has_north_connections = True
                    break
            
            if north_neighbors:
                has_north_connections = True
            
            if has_north_connections:
                token_text = token.text.strip()
                
                if token.ends_with_colon():
                    context.set_role(token_id, "LABEL")
                    if token_id not in context.label_candidates:
                        context.label_candidates.append(token_id)
                else:
                    if token.is_date() or token.is_number() or token.is_numeric_code():
                        context.set_role(token_id, "VALUE")
                    else:
                        # Verificar se tem conexões south/east que são LABELs
                        has_label_connections = False
                        south_neighbors = context.adjacency.get_neighbors(token_id, "south")
                        east_neighbors = context.adjacency.get_neighbors(token_id, "east")
                        
                        for neighbor_id in south_neighbors + east_neighbors:
                            neighbor_role = context.get_role(neighbor_id)
                            if neighbor_role == "LABEL":
                                has_label_connections = True
                                break
                        
                        if has_label_connections:
                            context.set_role(token_id, "VALUE")
                        else:
                            context.set_role(token_id, "LABEL")
                            if token_id not in context.label_candidates:
                                context.label_candidates.append(token_id)


class LabelSingleValueRule(BaseRule):
    """Regra: Um LABEL não pode ter múltiplos VALUES - remover edges extras."""
    
    def __init__(self):
        super().__init__(
            name="LabelSingleValueRule",
            priority=200,  # Alta prioridade - executar depois das outras regras
            dependencies=["ValueLabelUniquenessRule", "ValueNoLabelConnectionsRule"]
        )
    
    def apply(self, context: RuleContext) -> None:
        """Remove edges de LABEL para VALUE quando já existe um VALUE associado.
        
        REGRA FORTE: Um LABEL não pode ter múltiplos VALUES.
        Se um LABEL já tem um VALUE (definido por qualquer regra), remover outras conexões.
        """
        edges_to_remove = []
        
        # Primeiro, identificar todos os LABELs e seus VALUES oficiais
        label_to_official_value = {}
        
        # Para cada LABEL, encontrar seu VALUE oficial (prioridade: east > south > north > west)
        # NÃO copiar associações existentes - recalcular com prioridade correta
        for token in context.tokens:
            token_id = token.id
            token_role = context.get_role(token_id)
            
            if token_role == "LABEL":
                
                # Procurar VALUES conectados (prioridade: east > south > north > west)
                east_neighbors = context.adjacency.get_neighbors(token_id, "east")
                south_neighbors = context.adjacency.get_neighbors(token_id, "south")
                north_neighbors = context.adjacency.get_neighbors(token_id, "north")
                west_neighbors = context.adjacency.get_neighbors(token_id, "west")
                
                # Usar role do token original (definido durante extração) se disponível
                def get_token_role(nid):
                    neighbor_token = context.get_node_by_id(nid)
                    if neighbor_token and neighbor_token.role:
                        return neighbor_token.role
                    return context.get_role(nid)
                
                east_values = [nid for nid in east_neighbors if get_token_role(nid) == "VALUE"]
                south_values = [nid for nid in south_neighbors if get_token_role(nid) == "VALUE"]
                north_values = [nid for nid in north_neighbors if get_token_role(nid) == "VALUE"]
                west_values = [nid for nid in west_neighbors if get_token_role(nid) == "VALUE"]
                
                # Escolher o primeiro VALUE encontrado (prioridade: east > south > north > west)
                official_value_id = None
                if east_values:
                    official_value_id = east_values[0]
                elif south_values:
                    official_value_id = south_values[0]
                elif north_values:
                    official_value_id = north_values[0]
                elif west_values:
                    official_value_id = west_values[0]
                
                if official_value_id:
                    label_to_official_value[token_id] = official_value_id
                    context.label_to_value[token_id] = official_value_id
                    context.value_to_label[official_value_id] = token_id
        
        # Atualizar context.label_to_value e context.value_to_label com os valores oficiais
        for label_id, value_id in label_to_official_value.items():
            context.label_to_value[label_id] = value_id
            context.value_to_label[value_id] = label_id
        
        # Agora remover edges extras
        for edge in context.graph.edges:
            from_token = context.get_node_by_id(edge.from_id)
            to_token = context.get_node_by_id(edge.to_id)
            
            if not from_token or not to_token:
                continue
            
            # Usar role do token original se disponível
            from_token_obj = context.get_node_by_id(edge.from_id)
            to_token_obj = context.get_node_by_id(edge.to_id)
            from_role = from_token_obj.role if from_token_obj and from_token_obj.role else context.get_role(edge.from_id)
            to_role = to_token_obj.role if to_token_obj and to_token_obj.role else context.get_role(edge.to_id)
            
            # Se é um LABEL conectado a um VALUE
            if from_role == "LABEL" and to_role == "VALUE":
                label_id = edge.from_id
                value_id = edge.to_id
                
                # Se este LABEL já tem um VALUE oficial
                if label_id in label_to_official_value:
                    official_value_id = label_to_official_value[label_id]
                    # Se o VALUE conectado não é o VALUE oficial, remover edge
                    if value_id != official_value_id:
                        edges_to_remove.append(edge)
        
        # Remover edges
        for edge in edges_to_remove:
            if edge in context.graph.edges:
                context.graph.edges.remove(edge)
            # Também remover edge reversa se existir
            reverse_edge = edge.reverse()
            if reverse_edge in context.graph.edges:
                context.graph.edges.remove(reverse_edge)
        
        # Atualizar adjacency após remover edges
        # Recriar adjacency matrix para refletir as mudanças
        context.adjacency = AdjacencyMatrix(context.graph)


class ValueMustHaveLabelRule(BaseRule):
    """Regra de ALTA PRIORIDADE: Um VALUE sempre deve ter um LABEL à esquerda ou acima."""
    
    def __init__(self):
        super().__init__(
            name="ValueMustHaveLabelRule",
            priority=150,  # Alta prioridade, executar antes de outras regras finais
            dependencies=["ValueLabelUniquenessRule", "ValueLabelGuaranteeRule"]
        )
    
    def apply(self, context: RuleContext) -> None:
        """Garante que cada VALUE tem um LABEL à esquerda ou acima."""
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            # Verificar se é VALUE
            if current_role != "VALUE":
                continue
            
            # Verificar se já tem um LABEL associado
            if token_id in context.value_to_label:
                label_id = context.value_to_label[token_id]
                label_role = context.get_role(label_id)
                if label_role == "LABEL":
                    # Já tem LABEL, verificar se está à esquerda ou acima
                    label_token = context.get_node_by_id(label_id)
                    if label_token:
                        # Verificar posição relativa
                        value_bbox = token.bbox
                        label_bbox = label_token.bbox
                        
                        # Verificar se está à esquerda (west) ou acima (north)
                        is_left = label_bbox.x1 <= value_bbox.x0
                        is_above = label_bbox.y1 <= value_bbox.y0
                        
                        # Verificar sobreposição horizontal para "acima"
                        x_overlap = not (label_bbox.x1 < value_bbox.x0 or label_bbox.x0 > value_bbox.x1)
                        
                        if is_left or (is_above and x_overlap):
                            # LABEL está na posição correta
                            continue
            
            # VALUE não tem LABEL ou LABEL não está na posição correta
            # Procurar por um LABEL à esquerda ou acima
            value_bbox = token.bbox
            candidate_labels = []
            
            for other_token in context.tokens:
                other_id = other_token.id
                if other_id == token_id:
                    continue
                
                other_role = context.get_role(other_id)
                other_bbox = other_token.bbox
                
                # Verificar se está à esquerda (west)
                is_left = other_bbox.x1 <= value_bbox.x0
                y_overlap_left = not (other_bbox.y1 < value_bbox.y0 or other_bbox.y0 > value_bbox.y1)
                
                # Verificar se está acima (north)
                is_above = other_bbox.y1 <= value_bbox.y0
                x_overlap_above = not (other_bbox.x1 < value_bbox.x0 or other_bbox.x0 > value_bbox.x1)
                
                # Se é LABEL e está à esquerda ou acima
                if other_role == "LABEL" and (is_left or (is_above and x_overlap_above)):
                    # Calcular distância
                    if is_left:
                        distance = value_bbox.x0 - other_bbox.x1
                    else:
                        distance = value_bbox.y0 - other_bbox.y1
                    
                    candidate_labels.append((other_id, distance, is_left))
            
            # Ordenar por distância (mais próximo primeiro)
            candidate_labels.sort(key=lambda x: x[1])
            
            if candidate_labels:
                # Usar o LABEL mais próximo
                label_id, distance, is_left = candidate_labels[0]
                context.value_to_label[token_id] = label_id
                context.label_to_value[label_id] = token_id
            else:
                # Não encontrou LABEL, procurar por tokens de texto que possam ser LABELs
                for other_token in context.tokens:
                    other_id = other_token.id
                    if other_id == token_id:
                        continue
                    
                    other_role = context.get_role(other_id)
                    other_bbox = other_token.bbox
                    other_text = other_token.text.strip()
                    
                    # Verificar se está à esquerda ou acima
                    is_left = other_bbox.x1 <= value_bbox.x0
                    is_above = other_bbox.y1 <= value_bbox.y0
                    x_overlap_above = not (other_bbox.x1 < value_bbox.x0 or other_bbox.x0 > value_bbox.x1)
                    
                    # Se é texto puro (não número, não data) e está à esquerda ou acima
                    if (other_role in (None, "") and 
                        (is_left or (is_above and x_overlap_above)) and
                        not other_token.is_number() and not other_token.is_date() and
                        not bool(re.search(r"\d", other_text))):
                        # Classificar como LABEL
                        context.set_role(other_id, "LABEL", source_rule=self.name)
                        if other_id not in context.label_candidates:
                            context.label_candidates.append(other_id)
                        context.value_to_label[token_id] = other_id
                        context.label_to_value[other_id] = token_id
                        break
            
            # Se ainda não encontrou LABEL, verificar se há um token acima que não foi classificado
            if token_id not in context.value_to_label:
                # Procurar tokens acima com sobreposição horizontal
                for other_token in context.tokens:
                    other_id = other_token.id
                    if other_id == token_id:
                        continue
                    
                    other_role = context.get_role(other_id)
                    other_bbox = other_token.bbox
                    other_text = other_token.text.strip()
                    
                    # Verificar se está acima com sobreposição horizontal
                    is_above = other_bbox.y1 <= value_bbox.y0
                    x_overlap_above = not (other_bbox.x1 < value_bbox.x0 or other_bbox.x0 > value_bbox.x1)
                    
                    if is_above and x_overlap_above:
                        # Se é texto puro e não foi classificado, pode ser LABEL
                        if (other_role in (None, "") and
                            not other_token.is_number() and not other_token.is_date() and
                            not bool(re.search(r"\d", other_text))):
                            context.set_role(other_id, "LABEL", source_rule=self.name)
                            if other_id not in context.label_candidates:
                                context.label_candidates.append(other_id)
                            context.value_to_label[token_id] = other_id
                            context.label_to_value[other_id] = token_id
                            break


class SeparatedPairIsolationRule(BaseRule):
    """Remove todas as conexões de tokens separados, exceto a conexão horizontal entre LABEL e VALUE.
    
    Quando separamos "Label: Value" em dois tokens, eles devem formar um par isolado:
    - LABEL conecta apenas ao VALUE (east)
    - VALUE conecta apenas ao LABEL (west)
    - Remover todas as outras conexões (south, north, etc.)
    """
    
    def __init__(self):
        super().__init__(name="SeparatedPairIsolationRule", priority=35, dependencies=["InitialValueRule"])
    
    def apply(self, context: RuleContext) -> None:
        """Remove conexões extras de tokens separados."""
        # Encontrar todos os tokens que foram separados
        separated_tokens = [t for t in context.tokens if t.separated_pair]
        
        if not separated_tokens:
            return
        
        # Agrupar tokens separados em pares (LABEL-VALUE adjacentes)
        separated_pairs = []
        for token in separated_tokens:
            token_id = token.id
            role = context.get_role(token_id)
            
            if role == "LABEL":
                # Procurar VALUE à direita (east)
                east_neighbors = context.adjacency.get_neighbors(token_id, "east")
                for value_id in east_neighbors:
                    value_token = context.get_node_by_id(value_id)
                    if value_token and value_token.separated_pair and context.get_role(value_id) == "VALUE":
                        separated_pairs.append((token_id, value_id))
                        break
        
        # Para cada par separado, remover todas as conexões exceto LABEL-VALUE (east/west)
        for label_id, value_id in separated_pairs:
            # Remover conexões verticais (south/north) do LABEL
            south_neighbors = list(context.adjacency.get_neighbors(label_id, "south"))
            for neighbor_id in south_neighbors:
                if neighbor_id != value_id:  # Manter apenas conexão com VALUE se houver
                    context.graph.remove_edge(label_id, neighbor_id, "south")
                    context.adjacency.remove_edge(label_id, neighbor_id, "south")
            
            north_neighbors = list(context.adjacency.get_neighbors(label_id, "north"))
            for neighbor_id in north_neighbors:
                if neighbor_id != value_id:
                    context.graph.remove_edge(neighbor_id, label_id, "north")
                    context.adjacency.remove_edge(neighbor_id, label_id, "north")
            
            # Remover conexões verticais (south/north) do VALUE
            south_neighbors = list(context.adjacency.get_neighbors(value_id, "south"))
            for neighbor_id in south_neighbors:
                if neighbor_id != label_id:
                    context.graph.remove_edge(value_id, neighbor_id, "south")
                    context.adjacency.remove_edge(value_id, neighbor_id, "south")
            
            north_neighbors = list(context.adjacency.get_neighbors(value_id, "north"))
            for neighbor_id in north_neighbors:
                if neighbor_id != label_id:
                    context.graph.remove_edge(neighbor_id, value_id, "north")
                    context.adjacency.remove_edge(neighbor_id, value_id, "north")
            
            # Garantir que LABEL e VALUE estão conectados horizontalmente (east/west)
            # Se não estão, adicionar conexão
            if value_id not in context.adjacency.get_neighbors(label_id, "east"):
                from src.graph_builder.models import Edge
                edge = Edge(from_id=label_id, to_id=value_id, relation="east")
                context.graph.add_edge(edge)
                context.adjacency.add_edge(label_id, value_id, "east")


class ValueNoLabelConnectionsRule(BaseRule):
    """Passagem FINAL 10: VALUES não devem ligar para baixo (south) ou direita (east) com LABELs."""
    
    def __init__(self):
        super().__init__(name="ValueNoLabelConnectionsRule", priority=140)
    
    def apply(self, context: RuleContext) -> None:
        """Reclassifica LABELs conectados abaixo/direita de VALUES como VALUE."""
        for token in context.tokens:
            token_id = token.id
            current_role = context.get_role(token_id)
            
            if current_role != "VALUE":
                continue
            
            # Verificar conexões south e east
            south_neighbors = context.adjacency.get_neighbors(token_id, "south")
            east_neighbors = context.adjacency.get_neighbors(token_id, "east")
            
            # Verificar se algum vizinho south/east é LABEL
            for neighbor_id in south_neighbors + east_neighbors:
                neighbor_role = context.get_role(neighbor_id)
                
                if neighbor_role == "LABEL":
                    neighbor_token = context.get_node_by_id(neighbor_id)
                    if neighbor_token:
                        neighbor_text = neighbor_token.text.strip()
                        
                        # Se não termina com ":", reclassificar como VALUE
                        if not neighbor_text.endswith(":"):
                            context.set_role(neighbor_id, "VALUE")
                            
                            if neighbor_id in context.label_candidates:
                                context.label_candidates.remove(neighbor_id)
                            
                            # Remover ligações LABEL->VALUE se existirem
                            if neighbor_id in context.label_to_value:
                                old_value_id = context.label_to_value[neighbor_id]
                                if old_value_id in context.value_to_label:
                                    del context.value_to_label[old_value_id]
                                del context.label_to_value[neighbor_id]

