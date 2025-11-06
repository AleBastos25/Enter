"""Construção do grafo de tokens com edges ortogonais."""

from typing import List, Tuple
from src.graph_builder.models import Token, Edge, Graph


class GraphBuilder:
    """Constrói grafo de tokens com edges ortogonais."""
    
    def __init__(
        self,
        threshold_same_line: float = 0.005,
        min_overlap_x_ratio: float = 0.1,
        max_vertical_distance: float = 0.30
    ):
        """Inicializa o construtor de grafo.
        
        Args:
            threshold_same_line: Diferença em Y para considerar mesma linha.
            min_overlap_x_ratio: Overlap mínimo em X (10% do width mínimo) para edges verticais.
            max_vertical_distance: Distância vertical máxima (30% da altura da página).
        """
        self.threshold_same_line = threshold_same_line
        self.min_overlap_x_ratio = min_overlap_x_ratio
        self.max_vertical_distance = max_vertical_distance
    
    def build(self, tokens: List[Token]) -> Graph:
        """Constrói o grafo a partir dos tokens.
        
        Args:
            tokens: Lista de tokens.
        
        Returns:
            Grafo construído.
        """
        graph = Graph(nodes=tokens)
        
        # FASE 1: Agrupar tokens por linhas
        lines = self._group_by_lines(tokens)
        sorted_line_ids = sorted(lines.keys())
        
        # FASE 2: Criar edges horizontais
        horizontal_edges = self._create_horizontal_edges(lines)
        for edge in horizontal_edges:
            graph.add_edge(edge)
        
        # FASE 3: Criar edges verticais
        vertical_edges = self._create_vertical_edges(lines, sorted_line_ids)
        for edge in vertical_edges:
            graph.add_edge(edge)
        
        return graph
    
    def _group_by_lines(self, tokens: List[Token]) -> dict:
        """Agrupa tokens por linhas baseado na posição Y do centro.
        
        Args:
            tokens: Lista de tokens.
        
        Returns:
            Dicionário {line_id: [tokens]}.
        """
        lines = {}
        # Usar threshold maior para agrupamento inicial (0.01 em vez de 0.005)
        # Isso permite que tokens com pequenas diferenças de Y sejam agrupados
        line_threshold = max(self.threshold_same_line, 0.01)
        
        for token in tokens:
            y_center = token.bbox.center_y()
            
            # Encontrar a linha mais próxima ou criar uma nova
            line_id = None
            min_distance = line_threshold
            
            for existing_line_id, line_tokens in lines.items():
                # Pegar o Y médio da linha existente
                existing_y_center = sum(t.bbox.center_y() for t in line_tokens) / len(line_tokens)
                distance = abs(y_center - existing_y_center)
                if distance < min_distance:
                    min_distance = distance
                    line_id = existing_line_id
            
            # Se não encontrou linha próxima, criar nova
            if line_id is None:
                line_id = y_center  # Usar Y como ID da linha
            
            if line_id not in lines:
                lines[line_id] = []
            lines[line_id].append(token)
        
        return lines
    
    def _create_horizontal_edges(self, lines: dict) -> List[Edge]:
        """Cria edges horizontais (east/west) - tokens na mesma linha.
        
        Args:
            lines: Dicionário de linhas.
        
        Returns:
            Lista de edges horizontais.
        """
        edges = []
        
        for line_id, line_tokens in lines.items():
            # Ordenar tokens da linha por X (esquerda para direita)
            sorted_tokens = sorted(line_tokens, key=lambda t: t.bbox.x0)
            
            for i in range(len(sorted_tokens) - 1):
                token1 = sorted_tokens[i]
                token2 = sorted_tokens[i + 1]
                
                # Verificar se estão próximos horizontalmente
                width1 = token1.bbox.width()
                width2 = token2.bbox.width()
                avg_width = (width1 + width2) / 2.0
                gap = token2.bbox.x0 - token1.bbox.x1
                
                # Verificar se estão na mesma linha (Y similar)
                y_diff = abs(token1.bbox.center_y() - token2.bbox.center_y())
                
                # Se estão na mesma linha e gap não é muito grande
                # Aceitar até 3x a largura média (mais permissivo)
                # Mas se estão na mesma linha exata (y_diff muito pequeno), ser mais permissivo
                max_gap_multiplier = 3.0
                if y_diff < 0.01:  # Mesma linha (tolerância maior para pequenas diferenças de Y)
                    max_gap_multiplier = 6.0  # Mais permissivo para mesma linha
                
                if y_diff < self.threshold_same_line and gap < avg_width * max_gap_multiplier:
                    edges.append(Edge(
                        from_id=token1.id,
                        to_id=token2.id,
                        relation="east"
                    ))
        
        return edges
    
    def _create_vertical_edges(
        self,
        lines: dict,
        sorted_line_ids: List[float]
    ) -> List[Edge]:
        """Cria edges verticais (south) - entre linhas.
        
        Usa distribuição de espaçamento vertical entre linhas para evitar conexões
        entre tokens que estão muito distantes (ex: "01310300" e "Telefone Profissional").
        
        Args:
            lines: Dicionário de linhas.
            sorted_line_ids: Lista ordenada de IDs de linhas (de cima para baixo).
        
        Returns:
            Lista de edges verticais.
        """
        edges = []
        
        # Calcular distribuição de espaçamento vertical entre linhas consecutivas
        line_spacings = []
        for line_idx in range(len(sorted_line_ids) - 1):
            current_line_id = sorted_line_ids[line_idx]
            next_line_id = sorted_line_ids[line_idx + 1]
            
            # Calcular distância vertical média entre as duas linhas
            current_tokens = lines[current_line_id]
            next_tokens = lines[next_line_id]
            
            # Para cada token na linha atual, encontrar o token mais próximo na linha seguinte
            min_spacing = float('inf')
            for token1 in current_tokens:
                for token2 in next_tokens:
                    # Calcular distância vertical (do fim do token1 ao início do token2)
                    vertical_gap = token2.bbox.y0 - token1.bbox.y1
                    if vertical_gap > 0:  # Apenas gaps positivos
                        min_spacing = min(min_spacing, vertical_gap)
            
            if min_spacing < float('inf'):
                line_spacings.append(min_spacing)
        
        # Calcular estatísticas de espaçamento vertical
        if line_spacings:
            spacings_sorted = sorted(line_spacings)
            median_spacing = spacings_sorted[len(spacings_sorted) // 2]
            
            # Usar percentil 25 (Q25) para identificar gaps "normais" (ignorar outliers grandes)
            # Isso é mais robusto quando há muitos gaps pequenos e alguns muito grandes
            q25_idx = len(spacings_sorted) // 4
            q25_spacing = spacings_sorted[q25_idx] if q25_idx < len(spacings_sorted) else median_spacing
            
            # Threshold baseado em Q25 com fator maior (mais restritivo)
            # Se a mediana for muito alta (indicando muitos gaps grandes), usar Q25
            if median_spacing > 0.03:  # Se mediana é alta, usar Q25
                base_spacing = q25_spacing
            else:
                base_spacing = median_spacing
            
            # Usar 2.5x o espaçamento base para ser mais restritivo
            vertical_spacing_threshold = base_spacing * 2.5
        else:
            vertical_spacing_threshold = None
        
        # Threshold absoluto baseado no tamanho da página (assumindo coordenadas normalizadas [0,1])
        # Distância vertical não pode ser maior que 4.2% da altura da página (mais restritivo)
        # Isso garante que mesmo quando a mediana é alta, gaps grandes são removidos
        # 0.042 é um bom limite que captura gaps problemáticos como 0.0421, 0.0446, 0.0483
        absolute_vertical_threshold = 0.042
        
        for line_idx in range(len(sorted_line_ids)):
            current_line_id = sorted_line_ids[line_idx]
            current_line_tokens = lines[current_line_id]
            
            # Para cada token na linha atual, encontrar tokens nas linhas abaixo
            for token1 in current_line_tokens:
                candidates = self._find_vertical_candidates(
                    token1, line_idx, sorted_line_ids, lines
                )
                
                # Filtrar candidatos baseado na distribuição de espaçamento
                filtered_candidates = []
                for candidate in candidates:
                    token2 = candidate[0]
                    vertical_gap = candidate[3]  # vertical_gap está na posição 3
                    
                    # Verificar se distância vertical é muito grande comparado à distribuição
                    gap_too_large = False
                    
                    if vertical_spacing_threshold is not None:
                        # Gap é muito grande se for maior que o threshold baseado na distribuição
                        gap_too_large = vertical_gap > vertical_spacing_threshold
                    
                    # Também verificar threshold absoluto (relativo ao tamanho da página)
                    if vertical_gap > absolute_vertical_threshold:
                        gap_too_large = True
                    
                    # Se gap não é muito grande, manter candidato
                    if not gap_too_large:
                        filtered_candidates.append(candidate)
                
                # Se houver candidatos filtrados, escolher o melhor
                if filtered_candidates:
                    best_candidate = max(
                        filtered_candidates,
                        key=lambda c: (c[5], c[2], c[1], -c[4], -c[3], -c[6])
                    )
                    token2 = best_candidate[0]
                    
                    edges.append(Edge(
                        from_id=token1.id,
                        to_id=token2.id,
                        relation="south"
                    ))
        
        return edges
    
    def _find_vertical_candidates(
        self,
        token1: Token,
        line_idx: int,
        sorted_line_ids: List[float],
        lines: dict
    ) -> List[Tuple[Token, float, float, float, float, bool, int]]:
        """Encontra candidatos para edge vertical.
        
        Args:
            token1: Token origem.
            line_idx: Índice da linha atual.
            sorted_line_ids: Lista ordenada de IDs de linhas.
            lines: Dicionário de linhas.
        
        Returns:
            Lista de tuplas (token2, overlap_x, overlap_y, vertical_gap, center_diff, has_y_overlap, line_distance).
        """
        candidates = []
        
        for next_line_idx in range(line_idx + 1, len(sorted_line_ids)):
            next_line_id = sorted_line_ids[next_line_idx]
            next_line_tokens = lines[next_line_id]
            
            # Procurar candidatos na linha seguinte
            for token2 in next_line_tokens:
                # Calcular overlap em X e Y
                overlap_x = max(
                    0.0,
                    min(token1.bbox.x1, token2.bbox.x1) - max(token1.bbox.x0, token2.bbox.x0)
                )
                overlap_y = max(
                    0.0,
                    min(token1.bbox.y1, token2.bbox.y1) - max(token1.bbox.y0, token2.bbox.y0)
                )
                
                # Verificar se há sobreposição Y
                y_overlap = overlap_y > 0
                
                # Calcular distância vertical
                vertical_distance = token2.bbox.y0 - token1.bbox.y1
                
                # Verificar se distância vertical está dentro do limite
                if vertical_distance > self.max_vertical_distance:
                    continue  # Pular se distância for muito grande
                
                # Verificar se token2 está abaixo de token1
                is_below = token2.bbox.y0 >= token1.bbox.y0 - 0.02
                
                if y_overlap or is_below:
                    width1 = token1.bbox.width()
                    width2 = token2.bbox.width()
                    min_width = min(width1, width2)
                    
                    # Calcular diferença de centro
                    center_diff = abs(token1.bbox.center_x() - token2.bbox.center_x())
                    is_aligned = center_diff < max(width1, width2) * 0.6
                    
                    # Se há sobreposição Y, aceitar se há qualquer overlap X ou alinhamento
                    if y_overlap:
                        if overlap_x > 0 or is_aligned:
                            vertical_gap = vertical_distance
                            if vertical_gap < 0:
                                vertical_gap = -overlap_y * 0.001
                            line_distance = next_line_idx - line_idx
                            candidates.append((
                                token2, overlap_x, overlap_y, vertical_gap,
                                center_diff, True, line_distance
                            ))
                    elif overlap_x >= min_width * self.min_overlap_x_ratio or is_aligned:
                        # Sem sobreposição Y, só aceitar se for linha adjacente
                        if next_line_idx == line_idx + 1:
                            vertical_gap = max(0.0, vertical_distance)
                            candidates.append((
                                token2, overlap_x, 0.0, vertical_gap,
                                center_diff, False, 1
                            ))
            
            # Se encontrou um candidato com overlap Y, parar de procurar
            if candidates and any(c[5] for c in candidates):
                break
        
        return candidates

