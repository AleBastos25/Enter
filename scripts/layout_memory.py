"""Sistema de memória para padrões de layout por label de documento.

Armazena padrões estruturais aprendidos de PDFs anteriores para acelerar
e melhorar a classificação de roles em novos documentos do mesmo tipo.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, asdict
from collections import defaultdict


@dataclass
class LayoutPattern:
    """Padrão estrutural aprendido de um documento."""
    
    # Identificação
    label: str  # Label do documento (ex: "carteira_oab")
    pattern_hash: str  # Hash do padrão para identificação única
    
    # Características estruturais
    alignment: str  # 'left', 'center', 'right'
    font_size: float
    x0: float  # Posição X normalizada
    y_pattern: float  # Posição Y de referência
    
    # Roles aprendidos
    label_role: str  # Role do token que é LABEL
    value_role: str  # Role do token que é VALUE
    
    # Contagem de ocorrências
    count: int = 1  # Quantas vezes este padrão foi visto


@dataclass
class DocumentLayoutMemory:
    """Memória de layouts por label de documento."""
    
    label: str
    patterns: List[LayoutPattern]
    total_documents: int = 0
    layout_consistency: float = 1.0  # 1.0 = rígido/cold, 0.0 = variável/hot
    
    def find_similar_pattern(self, alignment: str, font_size: float, x0: float, 
                           tolerance_font: float = 2.0, tolerance_x: float = 0.02) -> Optional[LayoutPattern]:
        """Encontra padrão similar na memória."""
        for pattern in self.patterns:
            if pattern.alignment != alignment:
                continue
            
            font_diff = abs(pattern.font_size - font_size)
            x_diff = abs(pattern.x0 - x0)
            
            if font_diff <= tolerance_font and x_diff <= tolerance_x:
                return pattern
        
        return None
    
    def add_pattern(self, pattern: LayoutPattern):
        """Adiciona ou atualiza padrão na memória."""
        similar = self.find_similar_pattern(
            pattern.alignment, pattern.font_size, pattern.x0
        )
        
        if similar:
            # Atualizar padrão existente
            similar.count += 1
            # Atualizar roles se necessário (usar o mais comum)
            if pattern.label_role:
                similar.label_role = pattern.label_role
            if pattern.value_role:
                similar.value_role = pattern.value_role
        else:
            # Adicionar novo padrão
            self.patterns.append(pattern)
    
    def update_consistency(self):
        """Atualiza métrica de consistência do layout."""
        if not self.patterns:
            self.layout_consistency = 1.0
            return
        
        # Se temos muitos padrões diferentes, layout é variável
        # Se temos poucos padrões repetidos, layout é rígido
        total_patterns = sum(p.count for p in self.patterns)
        unique_patterns = len(self.patterns)
        
        if total_patterns == 0:
            self.layout_consistency = 1.0
        else:
            # Consistência = proporção de padrões únicos vs total
            # Menos padrões únicos = mais consistente (cold)
            self.layout_consistency = 1.0 - (unique_patterns / max(total_patterns, 1))


class LayoutMemoryManager:
    """Gerenciador de memória de layouts."""
    
    def __init__(self, memory_file: Optional[Path] = None):
        """Inicializa o gerenciador de memória.
        
        Args:
            memory_file: Caminho para arquivo JSON de memória persistente.
        """
        if memory_file is None:
            project_root = Path(__file__).parent.parent
            memory_file = project_root / ".layout_memory.json"
        
        self.memory_file = memory_file
        self.memories: Dict[str, DocumentLayoutMemory] = {}
        self._load_memory()
    
    def _load_memory(self):
        """Carrega memória do arquivo JSON."""
        if not self.memory_file.exists():
            return
        
        try:
            with open(self.memory_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            for label, mem_data in data.items():
                patterns = [
                    LayoutPattern(**p) for p in mem_data.get('patterns', [])
                ]
                memory = DocumentLayoutMemory(
                    label=label,
                    patterns=patterns,
                    total_documents=mem_data.get('total_documents', 0),
                    layout_consistency=mem_data.get('layout_consistency', 1.0)
                )
                self.memories[label] = memory
        except Exception as e:
            print(f"Erro ao carregar memória: {e}")
    
    def _save_memory(self):
        """Salva memória no arquivo JSON."""
        try:
            data = {}
            for label, memory in self.memories.items():
                data[label] = {
                    'patterns': [asdict(p) for p in memory.patterns],
                    'total_documents': memory.total_documents,
                    'layout_consistency': memory.layout_consistency,
                }
            
            with open(self.memory_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Erro ao salvar memória: {e}")
    
    def get_memory(self, label: str) -> DocumentLayoutMemory:
        """Obtém memória para um label, criando se não existir."""
        if label not in self.memories:
            self.memories[label] = DocumentLayoutMemory(
                label=label,
                patterns=[]
            )
        return self.memories[label]
    
    def learn_patterns(self, label: str, tokens: List[Dict], graph: Dict, roles: Dict[int, str]):
        """Aprende padrões de um documento processado.
        
        Args:
            label: Label do documento.
            tokens: Lista de tokens.
            graph: Grafo de tokens.
            roles: Roles classificados.
        """
        memory = self.get_memory(label)
        memory.total_documents += 1
        
        # Extrair padrões LABEL→VALUE
        edges = graph.get("edges", [])
        edges_by_token: Dict[int, List[Dict]] = {}
        for edge in edges:
            from_id = edge.get("from")
            if from_id not in edges_by_token:
                edges_by_token[from_id] = []
            edges_by_token[from_id].append(edge)
        
        for token in tokens:
            token_id = token["id"]
            role = roles.get(token_id)
            
            if role != "LABEL":
                continue
            
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) < 4:
                continue
            
            # Detectar alinhamento
            from scripts.build_token_graph import _detect_alignment
            alignment = _detect_alignment(bbox)
            font_size = token.get("font_size", 0) or 0
            x0 = bbox[0]
            y0 = bbox[1]
            
            # Procurar VALUE conectado
            for edge in edges_by_token.get(token_id, []):
                if edge.get("relation") not in ("south", "east"):
                    continue
                
                to_id = edge.get("to")
                to_role = roles.get(to_id)
                
                if to_role == "VALUE":
                    # Criar padrão
                    pattern_hash = hashlib.md5(
                        f"{label}:{alignment}:{font_size:.1f}:{x0:.4f}".encode()
                    ).hexdigest()
                    
                    pattern = LayoutPattern(
                        label=label,
                        pattern_hash=pattern_hash,
                        alignment=alignment,
                        font_size=font_size,
                        x0=x0,
                        y_pattern=y0,
                        label_role="LABEL",
                        value_role="VALUE"
                    )
                    
                    memory.add_pattern(pattern)
                    break
        
        # Atualizar consistência
        memory.update_consistency()
        self._save_memory()
    
    def apply_memory(self, label: str, tokens: List[Dict], roles: Dict[int, str], avg_font_size: float = 12.0) -> Dict[int, str]:
        """Aplica padrões aprendidos para melhorar classificação.
        
        IMPORTANTE: HEADER tem prioridade absoluta - nunca sobrescrever HEADER com VALUE da memória.
        
        Args:
            label: Label do documento.
            tokens: Lista de tokens.
            roles: Roles atuais.
            avg_font_size: Tamanho médio de fonte para verificar HEADER.
            
        Returns:
            Roles atualizados usando memória.
        """
        memory = self.get_memory(label)
        
        if not memory.patterns:
            # Sem memória, retornar roles originais
            return roles
        
        roles_updated = roles.copy()
        
        # Aplicar padrões aprendidos
        from scripts.build_token_graph import _detect_alignment
        
        for token in tokens:
            token_id = token["id"]
            current_role = roles_updated.get(token_id)
            text = token.get("text", "").strip()
            
            if not text:
                continue
            
            bbox = token.get("bbox", [0, 0, 0, 0])
            if len(bbox) < 4:
                continue
            
            font_size = token.get("font_size", 0) or 0
            y_top = bbox[1]
            is_near_top = y_top < 0.20
            # Mais permissivo: fonte maior que média OU ≥1.2x
            is_large_font = font_size >= avg_font_size * 1.2
            is_above_avg = font_size > avg_font_size
            tokens_list = text.split()
            
            # PRIMEIRO: Verificar se deveria ser HEADER (nomes no topo com fonte grande)
            # Isso tem prioridade ABSOLUTA sobre padrões de memória
            if is_near_top and (is_large_font or (is_above_avg and len(tokens_list) >= 2)):
                import re
                text_stripped = text.rstrip()
                ends_with_separator = any(text_stripped.endswith(sep) for sep in [":", "—", "–", ".", "•", "/"])
                if not ends_with_separator and not re.match(r"^\d+$", text.strip()):
                    # É HEADER, não VALUE - FORÇAR HEADER
                    roles_updated[token_id] = "HEADER"
                    continue  # Pular memória para este token
            
            # Se já é HEADER, NÃO aplicar memória (HEADER tem prioridade)
            if current_role == "HEADER":
                continue
            
            alignment = _detect_alignment(bbox)
            x0 = bbox[0]
            
            # Procurar padrão similar na memória
            pattern = memory.find_similar_pattern(alignment, font_size, x0)
            
            if pattern:
                # Se o padrão sugere um role diferente, aplicar
                # Mas só se o token ainda não tem role ou está mal classificado
                import re
                ends_with_separator = any(text.rstrip().endswith(sep) for sep in [":", "—", "–", ".", "•", "/"])
                
                if pattern.value_role == "VALUE" and not ends_with_separator:
                    # Se o padrão sugere VALUE e não termina com separador
                    # Mas NÃO aplicar se deveria ser HEADER (já verificado acima)
                    if current_role is None or current_role == "LABEL":
                        tokens_list = text.split()
                        has_digits = bool(re.search(r"\d", text))
                        if has_digits or len(tokens_list) >= 2:
                            roles_updated[token_id] = "VALUE"
        
        return roles_updated
    
    def get_temperature(self, label: str) -> float:
        """Retorna temperatura do layout (1.0 = cold/rigid, 0.0 = hot/variável)."""
        memory = self.get_memory(label)
        return memory.layout_consistency


# Instância global do gerenciador
_memory_manager: Optional[LayoutMemoryManager] = None


def get_memory_manager() -> LayoutMemoryManager:
    """Obtém instância global do gerenciador de memória."""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = LayoutMemoryManager()
    return _memory_manager

