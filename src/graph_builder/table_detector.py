"""Detecção de tabelas implícitas baseadas no layout do grafo."""

from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
from src.graph_builder.models import Token, BBox
from src.graph_builder.adjacency import AdjacencyMatrix


class TableOrientation(Enum):
    """Orientação da tabela."""
    HORIZONTAL = "horizontal"  # Label na primeira linha, valores na segunda
    VERTICAL = "vertical"  # Labels à esquerda, values à direita
    UNKNOWN = "unknown"  # 2x2, não dá para determinar


@dataclass
class TableCell:
    """Célula de uma tabela."""
    token_id: int
    row: int
    col: int
    token: Token


@dataclass
class Table:
    """Representa uma tabela implícita detectada."""
    cells: List[TableCell]
    rows: int
    cols: int
    orientation: TableOrientation
    bbox: BBox  # Bounding box da tabela inteira
    
    def get_cell(self, row: int, col: int) -> Optional[TableCell]:
        """Retorna a célula na posição (row, col)."""
        for cell in self.cells:
            if cell.row == row and cell.col == col:
                return cell
        return None
    
    def get_row(self, row: int) -> List[TableCell]:
        """Retorna todas as células de uma linha."""
        return [cell for cell in self.cells if cell.row == row]
    
    def get_col(self, col: int) -> List[TableCell]:
        """Retorna todas as células de uma coluna."""
        return [cell for cell in self.cells if cell.col == col]


class TableDetector:
    """Detecta tabelas implícitas no grafo de tokens."""
    
    def __init__(self, 
                 alignment_tolerance: float = 0.02,
                 font_size_tolerance: float = 0.5,
                 min_table_size: int = 2):
        """
        Args:
            alignment_tolerance: Tolerância para alinhamento (em coordenadas normalizadas)
            font_size_tolerance: Tolerância para tamanho de fonte (em pontos)
            min_table_size: Tamanho mínimo da tabela (2x2, 2x3, etc.)
        """
        self.alignment_tolerance = alignment_tolerance
        self.font_size_tolerance = font_size_tolerance
        self.min_table_size = min_table_size
    
    def detect_tables(self, tokens: List[Token], graph, adjacency: AdjacencyMatrix) -> List[Table]:
        """Detecta tabelas verificando se cada nó pode ser quina superior esquerda de uma matriz 2x2.
        
        Para cada nó, verifica:
        1. Tem exatamente 1 nó abaixo (south)
        2. Tem exatamente 1 nó à direita (east)
        3. O nó abaixo também tem exatamente 1 nó à direita
        4. O nó à direita também tem exatamente 1 nó abaixo
        
        Isso forma uma matriz 2x2 básica. Depois expande para horizontal ou vertical.
        
        Args:
            tokens: Lista de tokens
            graph: Grafo de tokens
            adjacency: Matriz de adjacência
            
        Returns:
            Lista de tabelas detectadas
        """
        tables = []
        visited_tokens = set()
        
        # Criar mapa de tokens por ID
        token_map = {token.id: token for token in tokens}
        
        # Ordenar tokens por Y (de cima para baixo) para processar até a penúltima linha
        tokens_sorted = sorted(tokens, key=lambda t: t.bbox.y0)
        
        # Para cada token (exceto os da última linha, que não podem ser pivô)
        for token in tokens_sorted:
            if token.id in visited_tokens:
                continue
            
            # Verificar se este token pode ser a quina superior esquerda de uma tabela 2x2
            table_cells = self._check_top_left_corner(token.id, token_map, adjacency, visited_tokens)
            
            if table_cells and len(table_cells) >= 4:  # Mínimo 2x2
                # Determinar orientação e expandir se necessário
                orientation, expanded_cells = self._determine_and_expand_table(
                    table_cells, token_map, adjacency
                )
                
                if expanded_cells:
                    table_cells = expanded_cells
                
                # Criar tabela
                table = self._create_table(table_cells, orientation)
                if table:
                    tables.append(table)
                    # Marcar todos os tokens da tabela como visitados
                    visited_tokens.update(cell.token_id for cell in table_cells)
        
        return tables
    
    def _check_top_left_corner(self, token_id: int, token_map: Dict[int, Token],
                               adjacency: AdjacencyMatrix, visited_tokens: Set[int]) -> List[TableCell]:
        """Verifica se um token pode ser a quina superior esquerda de uma matriz 2x2.
        
        Verifica:
        1. Token tem exatamente 1 nó abaixo (south)
        2. Token tem exatamente 1 nó à direita (east)
        3. O nó abaixo também tem exatamente 1 nó à direita
        4. O nó à direita também tem exatamente 1 nó abaixo
        
        Retorna lista de células da matriz 2x2 se encontrada, senão lista vazia.
        """
        # 1. Verificar se tem exatamente 1 nó abaixo
        south_neighbors = adjacency.get_neighbors(token_id, "south")
        if len(south_neighbors) != 1:
            return []
        
        bottom_left_id = south_neighbors[0]
        
        # 2. Verificar se tem exatamente 1 nó à direita
        east_neighbors = adjacency.get_neighbors(token_id, "east")
        if len(east_neighbors) != 1:
            return []
        
        top_right_id = east_neighbors[0]
        
        # 3. Verificar se o nó abaixo tem exatamente 1 nó à direita
        bottom_left_east = adjacency.get_neighbors(bottom_left_id, "east")
        if len(bottom_left_east) != 1:
            return []
        
        bottom_right_id = bottom_left_east[0]
        
        # 4. Verificar se o nó à direita tem exatamente 1 nó abaixo
        top_right_south = adjacency.get_neighbors(top_right_id, "south")
        if len(top_right_south) != 1:
            return []
        
        # Verificar se o nó abaixo à direita é o mesmo
        if bottom_right_id != top_right_south[0]:
            return []
        
        # Formar matriz 2x2
        cells = [
            TableCell(token_id, 0, 0, token_map[token_id]),  # top-left
            TableCell(top_right_id, 0, 1, token_map[top_right_id]),  # top-right
            TableCell(bottom_left_id, 1, 0, token_map[bottom_left_id]),  # bottom-left
            TableCell(bottom_right_id, 1, 1, token_map[bottom_right_id])  # bottom-right
        ]
        
        return cells
    
    def _determine_and_expand_table(self, base_cells: List[TableCell], 
                                    token_map: Dict[int, Token],
                                    adjacency: AdjacencyMatrix) -> Tuple[TableOrientation, List[TableCell]]:
        """Determina orientação da tabela e expande se for horizontal ou vertical.
        
        Retorna (orientação, células expandidas).
        """
        # Extrair células da matriz 2x2
        top_left = next(c for c in base_cells if c.row == 0 and c.col == 0)
        top_right = next(c for c in base_cells if c.row == 0 and c.col == 1)
        bottom_left = next(c for c in base_cells if c.row == 1 and c.col == 0)
        bottom_right = next(c for c in base_cells if c.row == 1 and c.col == 1)
        
        # Verificar se é horizontal: os dois nós da coluna da direita têm conexão à direita
        # E essas conexões são para nós diferentes que estão ligados verticalmente entre si
        top_right_east = adjacency.get_neighbors(top_right.token_id, "east")
        bottom_right_east = adjacency.get_neighbors(bottom_right.token_id, "east")
        
        is_horizontal = False
        if len(top_right_east) == 1 and len(bottom_right_east) == 1:
            next_top_id = top_right_east[0]
            next_bottom_id = bottom_right_east[0]
            # Verificar se são nós diferentes e estão conectados verticalmente
            if next_top_id != next_bottom_id:
                # Verificar se estão conectados verticalmente (south/north)
                next_top_south = adjacency.get_neighbors(next_top_id, "south")
                next_bottom_north = adjacency.get_neighbors(next_bottom_id, "north")
                is_horizontal = (next_bottom_id in next_top_south or next_top_id in next_bottom_north)
        
        # Verificar se é vertical: os dois nós da linha de baixo têm conexão abaixo
        # E essas conexões são para nós diferentes que estão ligados horizontalmente entre si
        bottom_left_south = adjacency.get_neighbors(bottom_left.token_id, "south")
        bottom_right_south = adjacency.get_neighbors(bottom_right.token_id, "south")
        
        is_vertical = False
        if len(bottom_left_south) == 1 and len(bottom_right_south) == 1:
            next_left_id = bottom_left_south[0]
            next_right_id = bottom_right_south[0]
            # Verificar se são nós diferentes e estão conectados horizontalmente
            if next_left_id != next_right_id:
                # Verificar se estão conectados horizontalmente (east/west)
                next_left_east = adjacency.get_neighbors(next_left_id, "east")
                next_right_west = adjacency.get_neighbors(next_right_id, "west")
                is_vertical = (next_right_id in next_left_east or next_left_id in next_right_west)
        
        cells = base_cells.copy()
        orientation = TableOrientation.UNKNOWN
        
        if is_horizontal:
            # Expandir horizontalmente
            orientation = TableOrientation.HORIZONTAL
            cells = self._expand_horizontal(base_cells, token_map, adjacency)
        elif is_vertical:
            # Expandir verticalmente
            orientation = TableOrientation.VERTICAL
            cells = self._expand_vertical(base_cells, token_map, adjacency)
        
        return orientation, cells
    
    def _expand_horizontal(self, base_cells: List[TableCell], token_map: Dict[int, Token],
                          adjacency: AdjacencyMatrix) -> List[TableCell]:
        """Expande tabela horizontalmente (adiciona colunas à direita).
        
        Para cada nova coluna, verifica que:
        - Todos os nós da coluna atual têm conexão à direita
        - Essas conexões são para nós diferentes
        - Esses nós estão conectados verticalmente entre si (formando uma coluna completa)
        """
        cells = base_cells.copy()
        
        # Encontrar número de linhas e colunas atuais
        max_row = max(c.row for c in cells)
        max_col = max(c.col for c in cells)
        
        # Continuar expandindo enquanto todas as linhas têm conexão à direita
        current_col = max_col
        while True:
            next_col_cells = []
            next_col_token_ids = []
            
            # Para cada linha, verificar se o token da coluna atual tem conexão à direita
            for row in range(max_row + 1):
                # Encontrar célula na linha atual e coluna atual
                current_cell = next((c for c in cells if c.row == row and c.col == current_col), None)
                if not current_cell:
                    break
                
                east_neighbors = adjacency.get_neighbors(current_cell.token_id, "east")
                if len(east_neighbors) != 1:
                    break
                
                next_token_id = east_neighbors[0]
                # Verificar se já está nas células (evitar duplicatas)
                if any(c.token_id == next_token_id for c in cells):
                    break
                
                next_col_token_ids.append(next_token_id)
                next_col_cells.append(TableCell(next_token_id, row, current_col + 1, token_map[next_token_id]))
            
            # Verificar se todas as linhas têm conexão
            if len(next_col_cells) != max_row + 1:
                break
            
            # Verificar se os nós da nova coluna estão conectados verticalmente entre si
            # (formando uma coluna completa)
            is_valid_column = True
            for i in range(len(next_col_token_ids) - 1):
                current_id = next_col_token_ids[i]
                next_id = next_col_token_ids[i + 1]
                
                # Verificar se estão conectados verticalmente (south/north)
                current_south = adjacency.get_neighbors(current_id, "south")
                next_north = adjacency.get_neighbors(next_id, "north")
                
                if not (next_id in current_south or current_id in next_north):
                    is_valid_column = False
                    break
            
            if is_valid_column:
                cells.extend(next_col_cells)
                current_col += 1
            else:
                break
        
        return cells
    
    def _expand_vertical(self, base_cells: List[TableCell], token_map: Dict[int, Token],
                        adjacency: AdjacencyMatrix) -> List[TableCell]:
        """Expande tabela verticalmente (adiciona linhas abaixo).
        
        Para cada nova linha, verifica que:
        - Todos os nós da linha atual têm conexão abaixo
        - Essas conexões são para nós diferentes
        - Esses nós estão conectados horizontalmente entre si (formando uma linha completa)
        """
        cells = base_cells.copy()
        
        # Encontrar número de linhas e colunas atuais
        max_row = max(c.row for c in cells)
        max_col = max(c.col for c in cells)
        
        # Continuar expandindo enquanto todas as colunas têm conexão abaixo
        current_row = max_row
        while True:
            next_row_cells = []
            next_row_token_ids = []
            
            # Para cada coluna, verificar se o token da linha atual tem conexão abaixo
            for col in range(max_col + 1):
                # Encontrar célula na linha atual e coluna atual
                current_cell = next((c for c in cells if c.row == current_row and c.col == col), None)
                if not current_cell:
                    break
                
                south_neighbors = adjacency.get_neighbors(current_cell.token_id, "south")
                if len(south_neighbors) != 1:
                    break
                
                next_token_id = south_neighbors[0]
                # Verificar se já está nas células (evitar duplicatas)
                if any(c.token_id == next_token_id for c in cells):
                    break
                
                next_row_token_ids.append(next_token_id)
                next_row_cells.append(TableCell(next_token_id, current_row + 1, col, token_map[next_token_id]))
            
            # Verificar se todas as colunas têm conexão
            if len(next_row_cells) != max_col + 1:
                break
            
            # Verificar se os nós da nova linha estão conectados horizontalmente entre si
            # (formando uma linha completa)
            is_valid_row = True
            for i in range(len(next_row_token_ids) - 1):
                current_id = next_row_token_ids[i]
                next_id = next_row_token_ids[i + 1]
                
                # Verificar se estão conectados horizontalmente (east/west)
                current_east = adjacency.get_neighbors(current_id, "east")
                next_west = adjacency.get_neighbors(next_id, "west")
                
                if not (next_id in current_east or current_id in next_west):
                    is_valid_row = False
                    break
            
            if is_valid_row:
                cells.extend(next_row_cells)
                current_row += 1
            else:
                break
        
        return cells
    
    def _build_table_from_token(self, start_token_id: int, token_map: Dict[int, Token],
                                adjacency: AdjacencyMatrix, is_vertical: bool,
                                visited_tokens: Set[int]) -> List[TableCell]:
        """Constrói uma tabela começando de um token específico.
        
        Para tabelas verticais:
        - Procura tokens conectados horizontalmente (east/west) na mesma linha
        - Para cada linha, procura tokens abaixo conectados verticalmente (south)
        
        Para tabelas horizontais:
        - Procura tokens conectados verticalmente (south/north) na mesma coluna
        - Para cada coluna, procura tokens à direita conectados horizontalmente (east)
        """
        cells = []
        start_token = token_map[start_token_id]
        
        if is_vertical:
            # Tabela vertical: começar pela primeira linha
            # Encontrar todos os tokens na mesma linha conectados horizontalmente
            first_row_tokens = self._find_connected_row(start_token_id, token_map, adjacency)
            
            if len(first_row_tokens) < 2:
                return []
            
            # Para cada token da primeira linha, procurar tokens abaixo (south)
            rows = [first_row_tokens]
            current_row = first_row_tokens
            
            # Continuar expandindo para baixo enquanto encontrar linhas completas
            while True:
                next_row = []
                for token_id in current_row:
                    south_neighbors = adjacency.get_neighbors(token_id, "south")
                    if south_neighbors:
                        # Escolher o primeiro vizinho sul (deve estar na mesma coluna)
                        next_row.append(south_neighbors[0])
                
                if len(next_row) == len(current_row):  # Linha completa
                    rows.append(next_row)
                    current_row = next_row
                else:
                    break
            
            # Converter para células
            for row_idx, row_tokens in enumerate(rows):
                for col_idx, token_id in enumerate(row_tokens):
                    cells.append(TableCell(token_id, row_idx, col_idx, token_map[token_id]))
        
        else:
            # Tabela horizontal: começar pela primeira coluna
            # Encontrar todos os tokens na mesma coluna conectados verticalmente
            first_col_tokens = self._find_connected_column(start_token_id, token_map, adjacency)
            
            if len(first_col_tokens) < 2:
                return []
            
            # Para cada token da primeira coluna, procurar tokens à direita (east)
            cols = [first_col_tokens]
            current_col = first_col_tokens
            
            # Continuar expandindo para direita enquanto encontrar colunas completas
            while True:
                next_col = []
                for token_id in current_col:
                    east_neighbors = adjacency.get_neighbors(token_id, "east")
                    if east_neighbors:
                        # Escolher o primeiro vizinho leste (deve estar na mesma linha)
                        next_col.append(east_neighbors[0])
                
                if len(next_col) == len(current_col):  # Coluna completa
                    cols.append(next_col)
                    current_col = next_col
                else:
                    break
            
            # Converter para células
            for col_idx, col_tokens in enumerate(cols):
                for row_idx, token_id in enumerate(col_tokens):
                    cells.append(TableCell(token_id, row_idx, col_idx, token_map[token_id]))
        
        return cells
    
    def _find_connected_row(self, start_token_id: int, token_map: Dict[int, Token],
                           adjacency: AdjacencyMatrix) -> List[int]:
        """Encontra todos os tokens na mesma linha conectados horizontalmente."""
        row_tokens = [start_token_id]
        visited = {start_token_id}
        
        # Expandir para esquerda (west)
        current = start_token_id
        while True:
            west_neighbors = adjacency.get_neighbors(current, "west")
            if west_neighbors and west_neighbors[0] not in visited:
                current = west_neighbors[0]
                row_tokens.insert(0, current)
                visited.add(current)
            else:
                break
        
        # Expandir para direita (east)
        current = start_token_id
        while True:
            east_neighbors = adjacency.get_neighbors(current, "east")
            if east_neighbors and east_neighbors[0] not in visited:
                current = east_neighbors[0]
                row_tokens.append(current)
                visited.add(current)
            else:
                break
        
        return row_tokens
    
    def _find_connected_column(self, start_token_id: int, token_map: Dict[int, Token],
                              adjacency: AdjacencyMatrix) -> List[int]:
        """Encontra todos os tokens na mesma coluna conectados verticalmente."""
        col_tokens = [start_token_id]
        visited = {start_token_id}
        
        # Expandir para cima (north)
        current = start_token_id
        while True:
            north_neighbors = adjacency.get_neighbors(current, "north")
            if north_neighbors and north_neighbors[0] not in visited:
                current = north_neighbors[0]
                col_tokens.insert(0, current)
                visited.add(current)
            else:
                break
        
        # Expandir para baixo (south)
        current = start_token_id
        while True:
            south_neighbors = adjacency.get_neighbors(current, "south")
            if south_neighbors and south_neighbors[0] not in visited:
                current = south_neighbors[0]
                col_tokens.append(current)
                visited.add(current)
            else:
                break
        
        return col_tokens
    
    def _group_by_rows(self, tokens: List[Token]) -> Dict[float, List[Token]]:
        """Agrupa tokens por linha (Y similar)."""
        rows = {}
        for token in tokens:
            # Usar y0 arredondado como chave
            y_key = round(token.bbox.y0 / self.alignment_tolerance) * self.alignment_tolerance
            if y_key not in rows:
                rows[y_key] = []
            rows[y_key].append(token)
        
        # Ordenar tokens em cada linha por x0
        for y_key in rows:
            rows[y_key].sort(key=lambda t: t.bbox.x0)
        
        return rows
    
    def _group_by_columns(self, tokens: List[Token]) -> Dict[float, List[Token]]:
        """Agrupa tokens por coluna (X similar)."""
        cols = {}
        for token in tokens:
            # Usar x0 arredondado como chave
            x_key = round(token.bbox.x0 / self.alignment_tolerance) * self.alignment_tolerance
            if x_key not in cols:
                cols[x_key] = []
            cols[x_key].append(token)
        
        # Ordenar tokens em cada coluna por y0
        for x_key in cols:
            cols[x_key].sort(key=lambda t: t.bbox.y0)
        
        return cols
    
    def _detect_vertical_tables(self, tokens: List[Token], rows: Dict[float, List[Token]], 
                                cols: Dict[float, List[Token]], adjacency: AdjacencyMatrix) -> List[Table]:
        """Detecta tabelas verticais (2 ou mais colunas, N linhas)."""
        tables = []
        
        # Encontrar grupos de colunas que formam tabelas
        col_keys = sorted(cols.keys())
        
        # Tentar detectar tabelas com 2 colunas primeiro
        for i in range(len(col_keys) - 1):
            col1_key = col_keys[i]
            col2_key = col_keys[i + 1]
            
            col1_tokens = cols[col1_key]
            col2_tokens = cols[col2_key]
            
            # Verificar se formam uma tabela 2xN
            table_cells = self._match_rows(col1_tokens, col2_tokens, adjacency)
            
            if len(table_cells) >= self.min_table_size * 2:  # Pelo menos 2 linhas
                # Verificar alinhamento e tipografia
                if self._validate_table_structure(table_cells, is_vertical=True):
                    # Tentar expandir para mais colunas (3, 4, etc.)
                    current_col_index = i + 1
                    current_col_key = col2_key
                    current_col_tokens = col2_tokens
                    
                    # Continuar expandindo enquanto encontrar colunas que se alinham
                    while current_col_index + 1 < len(col_keys):
                        next_col_key = col_keys[current_col_index + 1]
                        next_col_tokens = cols[next_col_key]
                        
                        # Verificar se a próxima coluna também se alinha com as linhas da tabela
                        additional_cells = self._match_rows_to_existing_table(
                            current_col_tokens, next_col_tokens, table_cells, adjacency
                        )
                        
                        # Se encontrou pelo menos metade das linhas alinhadas, adicionar
                        num_rows = len(set(c.row for c in table_cells))
                        if len(additional_cells) >= num_rows * 0.5:
                            table_cells.extend(additional_cells)
                            current_col_index += 1
                            current_col_key = next_col_key
                            current_col_tokens = next_col_tokens
                        else:
                            break
                    
                    # Determinar orientação
                    orientation = self._determine_vertical_orientation(table_cells)
                    
                    # Criar tabela
                    table = self._create_table(table_cells, orientation)
                    if table:
                        tables.append(table)
        
        return tables
    
    def _match_rows_to_existing_table(self, col2_tokens: List[Token], col3_tokens: List[Token],
                                      existing_cells: List[TableCell], adjacency: AdjacencyMatrix) -> List[TableCell]:
        """Tenta combinar col3_tokens com as linhas da tabela existente."""
        additional_cells = []
        used_col3 = set()
        
        # Agrupar células existentes por linha
        existing_rows = {}
        for cell in existing_cells:
            if cell.row not in existing_rows:
                existing_rows[cell.row] = []
            existing_rows[cell.row].append(cell)
        
        # Para cada linha da tabela existente, procurar token correspondente em col3
        for row in sorted(existing_rows.keys()):
            # Encontrar token da col2 nesta linha
            col2_cell = next((c for c in existing_rows[row] if c.col == 1), None)
            if not col2_cell:
                continue
            
            col2_token = col2_cell.token
            
            # Procurar token em col3 que está na mesma linha
            best_match = None
            min_y_diff = float('inf')
            
            # Calcular altura média dos tokens da linha para usar como referência
            row_tokens = [c.token for c in existing_rows[row]]
            avg_height = sum(t.bbox.height() for t in row_tokens) / len(row_tokens) if row_tokens else 0.01
            
            for token3 in col3_tokens:
                if token3.id in used_col3:
                    continue
                
                y_diff = abs(col2_token.bbox.center_y() - token3.bbox.center_y())
                # Usar tolerância mais flexível baseada na altura média
                tolerance = max(self.alignment_tolerance * 3, avg_height * 0.5)
                
                if y_diff < tolerance and y_diff < min_y_diff:
                    # Verificar se está alinhado horizontalmente (mesma linha)
                    # Não precisa estar conectado, apenas alinhado
                    best_match = token3
                    min_y_diff = y_diff
            
            if best_match:
                # Determinar o índice da coluna (número de colunas únicas já existentes)
                max_col = max(c.col for c in existing_cells) if existing_cells else -1
                additional_cells.append(TableCell(best_match.id, row, max_col + 1, best_match))
                used_col3.add(best_match.id)
        
        return additional_cells
    
    def _detect_horizontal_tables(self, tokens: List[Token], rows: Dict[float, List[Token]], 
                                  cols: Dict[float, List[Token]], adjacency: AdjacencyMatrix) -> List[Table]:
        """Detecta tabelas horizontais (M linhas, 2 colunas)."""
        tables = []
        
        # Encontrar pares de linhas que formam tabelas
        row_keys = sorted(rows.keys())
        
        for i in range(len(row_keys) - 1):
            row1_key = row_keys[i]
            row2_key = row_keys[i + 1]
            
            row1_tokens = rows[row1_key]
            row2_tokens = rows[row2_key]
            
            # Verificar se formam uma tabela Mx2
            table_cells = self._match_columns(row1_tokens, row2_tokens, adjacency)
            
            if len(table_cells) >= self.min_table_size * 2:  # Pelo menos 2 colunas
                # Verificar alinhamento e tipografia
                if self._validate_table_structure(table_cells, is_vertical=False):
                    # Determinar orientação
                    orientation = self._determine_horizontal_orientation(table_cells)
                    
                    # Criar tabela
                    table = self._create_table(table_cells, orientation)
                    if table:
                        tables.append(table)
        
        return tables
    
    def _match_rows(self, col1_tokens: List[Token], col2_tokens: List[Token], 
                   adjacency: AdjacencyMatrix) -> List[TableCell]:
        """Combina tokens de duas colunas em linhas."""
        cells = []
        used_col2 = set()
        
        for token1 in col1_tokens:
            # Procurar token correspondente na coluna 2 (mesma linha)
            best_match = None
            min_y_diff = float('inf')
            
            for token2 in col2_tokens:
                if token2.id in used_col2:
                    continue
                
                y_diff = abs(token1.bbox.center_y() - token2.bbox.center_y())
                if y_diff < self.alignment_tolerance * 2 and y_diff < min_y_diff:
                    # Verificar se estão conectados ou próximos
                    if (adjacency.are_neighbors(token1.id, token2.id) or 
                        y_diff < self.alignment_tolerance * 2):
                        best_match = token2
                        min_y_diff = y_diff
            
            if best_match:
                # Encontrar índice de linha (baseado na ordem Y)
                row = len(set(c.row for c in cells))
                cells.append(TableCell(token1.id, row, 0, token1))
                cells.append(TableCell(best_match.id, row, 1, best_match))
                used_col2.add(best_match.id)
        
        return cells
    
    def _match_columns(self, row1_tokens: List[Token], row2_tokens: List[Token], 
                     adjacency: AdjacencyMatrix) -> List[TableCell]:
        """Combina tokens de duas linhas em colunas."""
        cells = []
        used_row2 = set()
        
        for token1 in row1_tokens:
            # Procurar token correspondente na linha 2 (mesma coluna)
            best_match = None
            min_x_diff = float('inf')
            
            for token2 in row2_tokens:
                if token2.id in used_row2:
                    continue
                
                x_diff = abs(token1.bbox.center_x() - token2.bbox.center_x())
                if x_diff < self.alignment_tolerance * 2 and x_diff < min_x_diff:
                    # Verificar se estão conectados ou próximos
                    if (adjacency.are_neighbors(token1.id, token2.id) or 
                        x_diff < self.alignment_tolerance * 2):
                        best_match = token2
                        min_x_diff = x_diff
            
            if best_match:
                # Encontrar índice de coluna (baseado na ordem X)
                col = len(set(c.col for c in cells))
                cells.append(TableCell(token1.id, 0, col, token1))
                cells.append(TableCell(best_match.id, 1, col, best_match))
                used_row2.add(best_match.id)
        
        return cells
    
    def _validate_table_structure(self, cells: List[TableCell], is_vertical: bool) -> bool:
        """Valida se as células formam uma estrutura de tabela válida."""
        if len(cells) < 4:  # Mínimo 2x2
            return False
        
        # Verificar alinhamento
        if is_vertical:
            # Verificar alinhamento vertical (mesma coluna)
            for col in set(c.col for c in cells):
                col_cells = [c for c in cells if c.col == col]
                if len(col_cells) < 2:
                    continue
                
                # Verificar alinhamento horizontal (x similar)
                x_positions = [c.token.bbox.x0 for c in col_cells]
                x_std = self._std_dev(x_positions)
                if x_std > self.alignment_tolerance:
                    return False
                
                # Verificar font size similar
                font_sizes = [c.token.font_size for c in col_cells if c.token.font_size]
                if font_sizes:
                    font_std = self._std_dev(font_sizes)
                    if font_std > self.font_size_tolerance:
                        return False
        else:
            # Verificar alinhamento horizontal (mesma linha)
            for row in set(c.row for c in cells):
                row_cells = [c for c in cells if c.row == row]
                if len(row_cells) < 2:
                    continue
                
                # Verificar alinhamento vertical (y similar)
                y_positions = [c.token.bbox.y0 for c in row_cells]
                y_std = self._std_dev(y_positions)
                if y_std > self.alignment_tolerance:
                    return False
                
                # Verificar font size similar
                font_sizes = [c.token.font_size for c in row_cells if c.token.font_size]
                if font_sizes:
                    font_std = self._std_dev(font_sizes)
                    if font_std > self.font_size_tolerance:
                        return False
        
        return True
    
    def _determine_vertical_orientation(self, cells: List[TableCell]) -> TableOrientation:
        """Determina a orientação de uma tabela vertical."""
        # Para tabelas 2xN, verificar se coluna 0 tem labels e coluna 1 tem values
        col0_cells = [c for c in cells if c.col == 0]
        col1_cells = [c for c in cells if c.col == 1]
        
        # Verificar padrões de texto (labels geralmente terminam com ":", values são números/dados)
        col0_has_labels = sum(1 for c in col0_cells if c.token.text.strip().endswith(":")) > len(col0_cells) * 0.3
        col1_has_values = sum(1 for c in col1_cells if c.token.is_number() or c.token.is_date()) > len(col1_cells) * 0.3
        
        if col0_has_labels and col1_has_values:
            return TableOrientation.VERTICAL
        elif len(set(c.row for c in cells)) == 2 and len(set(c.col for c in cells)) == 2:
            return TableOrientation.UNKNOWN
        else:
            return TableOrientation.VERTICAL  # Default para vertical
    
    def _determine_horizontal_orientation(self, cells: List[TableCell]) -> TableOrientation:
        """Determina a orientação de uma tabela horizontal."""
        # Para tabelas Mx2, verificar se linha 0 tem labels e linha 1 tem values
        row0_cells = [c for c in cells if c.row == 0]
        row1_cells = [c for c in cells if c.row == 1]
        
        # Verificar padrões de texto
        row0_has_labels = sum(1 for c in row0_cells if c.token.text.strip().endswith(":")) > len(row0_cells) * 0.3
        row1_has_values = sum(1 for c in row1_cells if c.token.is_number() or c.token.is_date()) > len(row1_cells) * 0.3
        
        if row0_has_labels and row1_has_values:
            return TableOrientation.HORIZONTAL
        elif len(set(c.row for c in cells)) == 2 and len(set(c.col for c in cells)) == 2:
            return TableOrientation.UNKNOWN
        else:
            return TableOrientation.HORIZONTAL  # Default para horizontal
    
    def _create_table(self, cells: List[TableCell], orientation: TableOrientation) -> Optional[Table]:
        """Cria um objeto Table a partir das células."""
        if not cells:
            return None
        
        rows = max(c.row for c in cells) + 1
        cols = max(c.col for c in cells) + 1
        
        # Calcular bbox da tabela
        x0 = min(c.token.bbox.x0 for c in cells)
        y0 = min(c.token.bbox.y0 for c in cells)
        x1 = max(c.token.bbox.x1 for c in cells)
        y1 = max(c.token.bbox.y1 for c in cells)
        
        bbox = BBox(x0, y0, x1, y1)
        
        return Table(cells, rows, cols, orientation, bbox)
    
    def _remove_overlapping_tables(self, tables: List[Table]) -> List[Table]:
        """Remove tabelas sobrepostas, mantendo as maiores."""
        if not tables:
            return []
        
        # Ordenar por tamanho (número de células)
        tables_sorted = sorted(tables, key=lambda t: len(t.cells), reverse=True)
        
        kept = []
        for table in tables_sorted:
            # Verificar se sobrepõe com alguma tabela já mantida
            overlaps = False
            for kept_table in kept:
                if self._tables_overlap(table, kept_table):
                    overlaps = True
                    break
            
            if not overlaps:
                kept.append(table)
        
        return kept
    
    def _tables_overlap(self, table1: Table, table2: Table) -> bool:
        """Verifica se duas tabelas se sobrepõem."""
        # Verificar sobreposição de bbox
        bbox1 = table1.bbox
        bbox2 = table2.bbox
        
        x_overlap = not (bbox1.x1 < bbox2.x0 or bbox1.x0 > bbox2.x1)
        y_overlap = not (bbox1.y1 < bbox2.y0 or bbox1.y0 > bbox2.y1)
        
        if not (x_overlap and y_overlap):
            return False
        
        # Verificar se compartilham células
        table1_ids = {c.token_id for c in table1.cells}
        table2_ids = {c.token_id for c in table2.cells}
        
        return len(table1_ids & table2_ids) > 0
    
    def _std_dev(self, values: List[float]) -> float:
        """Calcula desvio padrão."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        return variance ** 0.5

