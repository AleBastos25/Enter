"""Sistema de aprendizado incremental baseado em documentos anteriores."""

from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from collections import defaultdict
import math
import json
import os
from pathlib import Path


@dataclass
class FieldOccurrence:
    """Uma ocorrência de um campo em um documento."""
    x: Optional[float] = None
    y: Optional[float] = None
    role: Optional[str] = None
    data_type: Optional[str] = None
    strategy: Optional[str] = None
    connections: Optional[int] = None
    found: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "x": self.x,
            "y": self.y,
            "role": self.role,
            "data_type": self.data_type,
            "strategy": self.strategy,
            "connections": self.connections,
            "found": self.found
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldOccurrence":
        """Cria a partir de dicionário."""
        return cls(
            x=data.get("x"),
            y=data.get("y"),
            role=data.get("role"),
            data_type=data.get("data_type"),
            strategy=data.get("strategy"),
            connections=data.get("connections"),
            found=data.get("found", True)
        )


@dataclass
class FieldPattern:
    """Padrão aprendido para um campo específico."""
    field_name: str
    label_type: str
    
    # Histórico de ocorrências
    occurrences: List[FieldOccurrence] = field(default_factory=list)
    
    def add_occurrence(self, occurrence: FieldOccurrence):
        """Adiciona uma ocorrência ao padrão."""
        self.occurrences.append(occurrence)
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "field_name": self.field_name,
            "label_type": self.label_type,
            "occurrences": [occ.to_dict() for occ in self.occurrences]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldPattern":
        """Cria a partir de dicionário."""
        return cls(
            field_name=data["field_name"],
            label_type=data["label_type"],
            occurrences=[FieldOccurrence.from_dict(occ) for occ in data.get("occurrences", [])]
        )
    
    def get_found_occurrences(self) -> List[FieldOccurrence]:
        """Retorna apenas as ocorrências onde o campo foi encontrado."""
        return [occ for occ in self.occurrences if occ.found]
    
    def get_found_rate(self) -> float:
        """Retorna a taxa de sucesso (quantas vezes o campo foi encontrado)."""
        if not self.occurrences:
            return 0.0
        found_count = sum(1 for occ in self.occurrences if occ.found)
        return found_count / len(self.occurrences)
    
    def get_position_stats(self) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Calcula estatísticas de posição (avg_x, avg_y, std_x, std_y)."""
        found_occ = self.get_found_occurrences()
        positions = [(occ.x, occ.y) for occ in found_occ if occ.x is not None and occ.y is not None]
        
        if not positions:
            return None, None, None, None
        
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        
        avg_x = sum(xs) / len(xs)
        avg_y = sum(ys) / len(ys)
        
        if len(positions) > 1:
            std_x = math.sqrt(sum((x - avg_x) ** 2 for x in xs) / len(xs))
            std_y = math.sqrt(sum((y - avg_y) ** 2 for y in ys) / len(ys))
        else:
            std_x = 0.0
            std_y = 0.0
        
        return avg_x, avg_y, std_x, std_y
    
    def get_role_distribution(self) -> Dict[str, float]:
        """Retorna distribuição de roles (normalizada)."""
        found_occ = self.get_found_occurrences()
        role_counts = defaultdict(int)
        for occ in found_occ:
            if occ.role:
                role_counts[occ.role] += 1
        
        total = sum(role_counts.values())
        if total == 0:
            return {}
        
        return {role: count / total for role, count in role_counts.items()}
    
    def get_data_type_distribution(self) -> Dict[str, float]:
        """Retorna distribuição de tipos de dado (normalizada)."""
        found_occ = self.get_found_occurrences()
        type_counts = defaultdict(int)
        for occ in found_occ:
            if occ.data_type:
                type_counts[occ.data_type] += 1
        
        total = sum(type_counts.values())
        if total == 0:
            return {}
        
        return {dtype: count / total for dtype, count in type_counts.items()}
    
    def get_connections_stats(self) -> Tuple[Optional[float], Optional[float]]:
        """Calcula estatísticas de conexões (avg, std)."""
        found_occ = self.get_found_occurrences()
        connections = [occ.connections for occ in found_occ if occ.connections is not None]
        
        if not connections:
            return None, None
        
        avg = sum(connections) / len(connections)
        
        if len(connections) > 1:
            std = math.sqrt(sum((c - avg) ** 2 for c in connections) / len(connections))
        else:
            std = 0.0
        
        return avg, std
    
    def get_rigidity(self) -> float:
        """Calcula a rigidez (inverso da variância) do padrão.
        
        Retorna um valor entre 0 (muito variável) e 1 (muito rígido).
        """
        if len(self.occurrences) < 500:
            return 0.5  # Neutro se não há dados suficientes
        
        found_occ = self.get_found_occurrences()
        if len(found_occ) < 2:
            return 0.5
        
        rigidities = []
        
        # Rigidez de posição
        avg_x, avg_y, std_x, std_y = self.get_position_stats()
        if avg_x is not None and std_x is not None:
            # Normalizar desvio padrão (assumindo página de ~800x600)
            # Usar desvio padrão combinado
            combined_std = math.sqrt(std_x ** 2 + std_y ** 2) if std_y is not None else std_x
            # Normalizar para página típica (assumir ~1000 pixels de largura)
            normalized_std = combined_std / 1000.0
            position_rigidity = max(0.0, 1.0 - min(1.0, normalized_std))
            rigidities.append(position_rigidity)
        
        # Rigidez de role (quanto mais consistente, mais rígido)
        role_dist = self.get_role_distribution()
        if role_dist:
            max_role_prob = max(role_dist.values())
            rigidities.append(max_role_prob)
        
        # Rigidez de tipo de dado
        type_dist = self.get_data_type_distribution()
        if type_dist:
            max_type_prob = max(type_dist.values())
            rigidities.append(max_type_prob)
        
        # Rigidez de conexões
        avg_conn, std_conn = self.get_connections_stats()
        if avg_conn is not None and std_conn is not None and avg_conn > 0:
            normalized_std = std_conn / avg_conn
            connection_rigidity = max(0.0, 1.0 - min(1.0, normalized_std))
            rigidities.append(connection_rigidity)
        
        if not rigidities:
            return 0.5
        
        # Média ponderada (dar mais peso à posição e role)
        if len(rigidities) >= 2:
            # Primeiro elemento é posição, segundo é role
            weighted = (rigidities[0] * 0.4 + rigidities[1] * 0.3 + 
                       sum(rigidities[2:]) * 0.3 / max(1, len(rigidities) - 2))
            return weighted
        else:
            return sum(rigidities) / len(rigidities)
    
    def matches_pattern(
        self,
        x: Optional[float] = None,
        y: Optional[float] = None,
        role: Optional[str] = None,
        data_type: Optional[str] = None,
        connections: Optional[int] = None
    ) -> Tuple[bool, List[str]]:
        """Verifica se um match corresponde ao padrão aprendido.
        
        Returns:
            (matches, reasons) - reasons contém explicações se não corresponder
        """
        found_occ = self.get_found_occurrences()
        if len(found_occ) < 2:
            # Não há padrão suficiente
            return True, []
        
        reasons = []
        matches = True
        
        # Verificar posição
        if x is not None and y is not None:
            avg_x, avg_y, std_x, std_y = self.get_position_stats()
            if avg_x is not None:
                distance = math.sqrt((x - avg_x) ** 2 + (y - avg_y) ** 2)
                # Calcular distância máxima esperada (3 desvios padrão)
                max_std = max(std_x or 100, std_y or 100)
                max_distance = max_std * 3
                
                if distance > max_distance:
                    matches = False
                    reasons.append(f"posição muito diferente (distância: {distance:.0f} vs esperado: <{max_distance:.0f})")
        
        # Verificar role
        if role:
            role_dist = self.get_role_distribution()
            if role_dist:
                most_common_role = max(role_dist.items(), key=lambda x: x[1])[0]
                if role != most_common_role and role_dist.get(most_common_role, 0) > 0.7:
                    # Se o role mais comum tem >70% das ocorrências e o atual é diferente
                    matches = False
                    reasons.append(f"role diferente ({role} vs esperado {most_common_role} com {role_dist[most_common_role]:.0%})")
        
        # Verificar tipo de dado
        if data_type:
            type_dist = self.get_data_type_distribution()
            if type_dist:
                most_common_type = max(type_dist.items(), key=lambda x: x[1])[0]
                if data_type != most_common_type and type_dist.get(most_common_type, 0) > 0.7:
                    matches = False
                    reasons.append(f"tipo diferente ({data_type} vs esperado {most_common_type} com {type_dist[most_common_type]:.0%})")
        
        return matches, reasons


@dataclass
class DocumentTypeLearning:
    """Aprendizado para um tipo de documento específico."""
    label_type: str
    field_patterns: Dict[str, FieldPattern] = field(default_factory=dict)
    document_count: int = 0
    
    def get_field_pattern(self, field_name: str) -> FieldPattern:
        """Obtém ou cria um padrão para um campo."""
        if field_name not in self.field_patterns:
            self.field_patterns[field_name] = FieldPattern(
                field_name=field_name,
                label_type=self.label_type
            )
        return self.field_patterns[field_name]
    
    def to_dict(self) -> Dict[str, Any]:
        """Converte para dicionário."""
        return {
            "label_type": self.label_type,
            "document_count": self.document_count,
            "field_patterns": {
                name: pattern.to_dict() 
                for name, pattern in self.field_patterns.items()
            }
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DocumentTypeLearning":
        """Cria a partir de dicionário."""
        return cls(
            label_type=data["label_type"],
            document_count=data.get("document_count", 0),
            field_patterns={
                name: FieldPattern.from_dict(pattern_data)
                for name, pattern_data in data.get("field_patterns", {}).items()
            }
        )
    
    def should_reject_match(
        self,
        field_name: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        role: Optional[str] = None,
        data_type: Optional[str] = None,
        connections: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Decide se um match deve ser rejeitado baseado no aprendizado.
        
        Returns:
            (should_reject, reason)
        """
        if field_name not in self.field_patterns:
            return False, ""
        
        pattern = self.field_patterns[field_name]
        
        found_rate = pattern.get_found_rate()
        rigidity = pattern.get_rigidity()
        
        # Caso especial: se o campo nunca foi encontrado (found_rate = 0) e temos
        # histórico suficiente (>=2 ocorrências), provavelmente não está no documento
        # Ser mais rigoroso: se nunca foi encontrado em 2+ documentos, rejeitar qualquer match
        if found_rate == 0.0 and len(pattern.occurrences) >= 2:
            # Se nunca foi encontrado, rejeitar qualquer match (independente da rigidez)
            reason = (
                f"Campo nunca foi encontrado em documentos anteriores "
                f"(ocorrências: {len(pattern.occurrences)}, taxa_sucesso: {found_rate:.2f})"
            )
            return True, reason
        
        # Precisa de pelo menos 3 ocorrências para ter confiança em padrões positivos
        if len(pattern.occurrences) < 50:
            return False, ""
        
        # Se o campo foi encontrado na maioria das vezes (>=80%) e o padrão é rígido (>=0.7),
        # mas o match atual não corresponde ao padrão, rejeitar
        if found_rate >= 0.8 and rigidity >= 0.7:
            matches, reasons = pattern.matches_pattern(x, y, role, data_type, connections)
            
            if not matches:
                reason = (
                    f"Match não corresponde ao padrão aprendido "
                    f"(rigidez: {rigidity:.2f}, taxa_sucesso: {found_rate:.2f}, "
                    f"ocorrências: {len(pattern.occurrences)}). "
                    + "; ".join(reasons)
                )
                return True, reason
        
        return False, ""


class DocumentLearner:
    """Sistema de aprendizado incremental de documentos."""
    
    # Caminho padrão para o arquivo de aprendizado
    DEFAULT_LEARNING_FILE = Path.home() / ".graph_extractor" / "learning.json"
    
    # Instância singleton
    _instance: Optional["DocumentLearner"] = None
    
    def __init__(self, learning_file: Optional[Path] = None):
        """Inicializa o aprendizado.
        
        Args:
            learning_file: Caminho para arquivo de persistência. Se None, usa padrão.
        """
        self.type_learnings: Dict[str, DocumentTypeLearning] = {}
        self.learning_file = learning_file or self.DEFAULT_LEARNING_FILE
        
        # Criar diretório se não existir
        if self.learning_file.parent:
            self.learning_file.parent.mkdir(parents=True, exist_ok=True)
        
        # Carregar aprendizado existente
        self.load()
    
    @classmethod
    def get_instance(cls, learning_file: Optional[Path] = None) -> "DocumentLearner":
        """Obtém instância singleton do DocumentLearner.
        
        Args:
            learning_file: Caminho para arquivo de persistência. Só usado na primeira chamada.
            
        Returns:
            Instância singleton do DocumentLearner
        """
        if cls._instance is None:
            cls._instance = cls(learning_file)
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reseta a instância singleton (útil para testes)."""
        cls._instance = None
    
    def save(self) -> bool:
        """Salva o aprendizado em arquivo.
        
        Returns:
            True se salvou com sucesso, False caso contrário
        """
        try:
            data = {
                "type_learnings": {
                    label_type: type_learning.to_dict()
                    for label_type, type_learning in self.type_learnings.items()
                }
            }
            
            with open(self.learning_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            return True
        except Exception as e:
            print(f"[DocumentLearner] Erro ao salvar aprendizado: {e}", flush=True)
            return False
    
    def load(self) -> bool:
        """Carrega aprendizado de arquivo.
        
        Returns:
            True se carregou com sucesso, False caso contrário
        """
        if not self.learning_file.exists():
            return False
        
        try:
            with open(self.learning_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.type_learnings = {
                label_type: DocumentTypeLearning.from_dict(type_data)
                for label_type, type_data in data.get("type_learnings", {}).items()
            }
            
            return True
        except Exception as e:
            print(f"[DocumentLearner] Erro ao carregar aprendizado: {e}", flush=True)
            return False
    
    def learn_from_extraction(
        self,
        label_type: str,
        field_name: str,
        found: bool,
        x: Optional[float] = None,
        y: Optional[float] = None,
        role: Optional[str] = None,
        data_type: Optional[str] = None,
        strategy: Optional[str] = None,
        connections: Optional[int] = None
    ):
        """Aprende de uma extração."""
        if label_type not in self.type_learnings:
            self.type_learnings[label_type] = DocumentTypeLearning(label_type=label_type)
        
        type_learning = self.type_learnings[label_type]
        pattern = type_learning.get_field_pattern(field_name)
        
        occurrence = FieldOccurrence(
            x=x,
            y=y,
            role=role,
            data_type=data_type,
            strategy=strategy,
            connections=connections,
            found=found
        )
        
        pattern.add_occurrence(occurrence)
        type_learning.document_count += 1
        
        # Salvar após cada aprendizado (persistência incremental)
        self.save()
    
    def should_reject_match(
        self,
        label_type: str,
        field_name: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        role: Optional[str] = None,
        data_type: Optional[str] = None,
        connections: Optional[int] = None
    ) -> Tuple[bool, str]:
        """Decide se um match deve ser rejeitado baseado no aprendizado."""
        if label_type not in self.type_learnings:
            return False, ""
        
        return self.type_learnings[label_type].should_reject_match(
            field_name, x, y, role, data_type, connections
        )
    
    def get_field_info(
        self,
        label_type: str,
        field_name: str
    ) -> Optional[Dict[str, Any]]:
        """Obtém informações sobre um campo aprendido."""
        if label_type not in self.type_learnings:
            return None
        
        type_learning = self.type_learnings[label_type]
        if field_name not in type_learning.field_patterns:
            return None
        
        pattern = type_learning.field_patterns[field_name]
        avg_x, avg_y, std_x, std_y = pattern.get_position_stats()
        avg_conn, std_conn = pattern.get_connections_stats()
        role_dist = pattern.get_role_distribution()
        type_dist = pattern.get_data_type_distribution()
        
        return {
            "rigidity": pattern.get_rigidity(),
            "found_rate": pattern.get_found_rate(),
            "occurrence_count": len(pattern.occurrences),
            "found_count": len(pattern.get_found_occurrences()),
            "avg_position": (avg_x, avg_y) if avg_x is not None else None,
            "position_std": (std_x, std_y) if std_x is not None else None,
            "most_common_role": max(role_dist.items(), key=lambda x: x[1])[0] if role_dist else None,
            "role_distribution": role_dist,
            "most_common_type": max(type_dist.items(), key=lambda x: x[1])[0] if type_dist else None,
            "type_distribution": type_dist,
            "avg_connections": avg_conn,
            "std_connections": std_conn,
        }


class NoOpLearner:
    """Learner que não faz nada (quando aprendizado está desabilitado)."""
    
    def learn_from_extraction(self, *args, **kwargs):
        """Não faz nada."""
        pass
    
    def should_reject_match(self, *args, **kwargs) -> Tuple[bool, str]:
        """Não rejeita nada."""
        return False, ""
    
    def get_field_info(self, *args, **kwargs) -> Optional[Dict[str, Any]]:
        """Não retorna nada."""
        return None
