"""Gerenciador de nós usados/não usados durante extração."""

from typing import Set, Dict, Optional
import re


class NodeUsageManager:
    """Gerencia quais nós do grafo já foram usados durante extração.
    
    Permite rastrear nós usados para evitar duplicação, mas também suporta
    reutilização parcial quando um nó contém múltiplos valores.
    """
    
    def __init__(self):
        """Inicializa o gerenciador."""
        # Nós completamente usados (não podem ser reutilizados)
        self._used_nodes: Set[int] = set()
        
        # Nós com reutilização parcial: {node_id: {field_name: extracted_value}}
        self._partial_usage: Dict[int, Dict[str, str]] = {}
        
        # Rastreamento de quais campos usaram quais nós
        self._node_to_fields: Dict[int, Set[str]] = {}
    
    def mark_as_used(self, node_id: int, field_name: str, extracted_value: Optional[str] = None) -> None:
        """Marca um nó como usado para um campo específico.
        
        Args:
            node_id: ID do nó usado
            field_name: Nome do campo que usou o nó
            extracted_value: Valor extraído (opcional, para detecção de reutilização parcial)
        """
        # Adicionar à lista de campos que usaram este nó
        if node_id not in self._node_to_fields:
            self._node_to_fields[node_id] = set()
        self._node_to_fields[node_id].add(field_name)
        
        # Se não há valor extraído, marcar como completamente usado
        if extracted_value is None:
            self._used_nodes.add(node_id)
            return
        
        # Verificar se pode ser reutilizado parcialmente
        if self._can_reuse_partially(node_id, extracted_value):
            # Adicionar ao registro de uso parcial
            if node_id not in self._partial_usage:
                self._partial_usage[node_id] = {}
            self._partial_usage[node_id][field_name] = extracted_value
        else:
            # Não pode ser reutilizado, marcar como completamente usado
            self._used_nodes.add(node_id)
            # Remover de uso parcial se estava lá
            if node_id in self._partial_usage:
                del self._partial_usage[node_id]
    
    def is_available(self, node_id: int) -> bool:
        """Verifica se um nó está disponível para uso.
        
        Args:
            node_id: ID do nó a verificar
            
        Returns:
            True se o nó está disponível (não foi completamente usado)
        """
        return node_id not in self._used_nodes
    
    def can_reuse_partially(self, node_id: int, new_extracted_value: str) -> bool:
        """Verifica se um nó pode ser reutilizado parcialmente.
        
        Um nó pode ser reutilizado parcialmente se:
        - Não está completamente usado
        - Contém múltiplos valores separados (ex: "R$ 1.000,00 - R$ 2.000,00")
        - O novo valor extraído é diferente dos valores já extraídos
        
        Args:
            node_id: ID do nó
            new_extracted_value: Novo valor que se deseja extrair
            
        Returns:
            True se pode reutilizar parcialmente
        """
        # Se está completamente usado, não pode reutilizar
        if not self.is_available(node_id):
            return False
        
        # Se não tem uso parcial anterior, verificar se pode ter
        if node_id not in self._partial_usage:
            return self._has_multiple_values(new_extracted_value)
        
        # Verificar se o novo valor é diferente dos já extraídos
        existing_values = set(self._partial_usage[node_id].values())
        return new_extracted_value not in existing_values
    
    def _can_reuse_partially(self, node_id: int, extracted_value: str) -> bool:
        """Verifica se um nó pode ser marcado como parcialmente usado.
        
        Similar a can_reuse_partially, mas usado internamente.
        """
        # Verificar se o valor contém múltiplos valores
        if not self._has_multiple_values(extracted_value):
            return False
        
        # Se já tem uso parcial, verificar se o valor é novo
        if node_id in self._partial_usage:
            existing_values = set(self._partial_usage[node_id].values())
            # Extrair valores individuais do novo valor
            new_values = self._extract_individual_values(extracted_value)
            # Se há sobreposição completa, não pode reutilizar
            if new_values.issubset(existing_values):
                return False
        
        return True
    
    def _has_multiple_values(self, text: str) -> bool:
        """Verifica se um texto contém múltiplos valores separados.
        
        Detecta padrões como:
        - "R$ 1.000,00 - R$ 2.000,00"
        - "Valor1 / Valor2"
        - Múltiplas datas separadas
        - Múltiplos números separados
        
        Args:
            text: Texto a verificar
            
        Returns:
            True se parece conter múltiplos valores
        """
        if not text or len(text.strip()) < 5:
            return False
        
        text = text.strip()
        
        # Padrões de separadores comuns
        separators = [' - ', ' / ', ' | ', ';', ',']
        for sep in separators:
            parts = text.split(sep)
            if len(parts) > 1:
                # Verificar se as partes são valores independentes
                # (não apenas parte de uma frase)
                if self._are_independent_values(parts):
                    return True
        
        return False
    
    def _are_independent_values(self, parts: list) -> bool:
        """Verifica se partes de texto são valores independentes.
        
        Args:
            parts: Lista de partes do texto
            
        Returns:
            True se parecem ser valores independentes
        """
        if len(parts) < 2:
            return False
        
        # Limpar partes
        parts = [p.strip() for p in parts if p.strip()]
        
        if len(parts) < 2:
            return False
        
        # Verificar se pelo menos 2 partes parecem valores (não palavras soltas)
        value_patterns = [
            r'^\d+[.,]\d+',  # Números com decimais
            r'^R\s*\$',      # Valores monetários
            r'^\d{1,2}[/-]\d{1,2}',  # Datas
            r'^\d{11,14}',   # CPF/CNPJ
        ]
        
        value_count = 0
        for part in parts:
            for pattern in value_patterns:
                if re.search(pattern, part):
                    value_count += 1
                    break
        
        return value_count >= 2
    
    def _extract_individual_values(self, text: str) -> set:
        """Extrai valores individuais de um texto com múltiplos valores.
        
        Args:
            text: Texto com múltiplos valores
            
        Returns:
            Set de valores individuais extraídos
        """
        values = set()
        
        # Tentar separar por separadores comuns
        separators = [' - ', ' / ', ' | ', ';', ',']
        for sep in separators:
            if sep in text:
                parts = text.split(sep)
                for part in parts:
                    part = part.strip()
                    if part:
                        values.add(part)
                break
        
        # Se não encontrou separador, retornar o texto completo
        if not values:
            values.add(text.strip())
        
        return values
    
    def get_used_nodes(self) -> Set[int]:
        """Retorna conjunto de nós completamente usados.
        
        Returns:
            Set de IDs de nós completamente usados
        """
        return self._used_nodes.copy()
        
    
    def get_partially_used_nodes(self) -> Dict[int, Dict[str, str]]:
        """Retorna dicionário de nós com uso parcial.
        
        Returns:
            Dicionário {node_id: {field_name: extracted_value}}
        """
        return self._partial_usage.copy()
    
    def get_nodes_used_by_field(self, field_name: str) -> Set[int]:
        """Retorna nós usados por um campo específico.
        
        Args:
            field_name: Nome do campo
            
        Returns:
            Set de IDs de nós usados pelo campo
        """
        result = set()
        for node_id, fields in self._node_to_fields.items():
            if field_name in fields:
                result.add(node_id)
        return result
    
    def reset(self) -> None:
        """Reseta o gerenciador, limpando todos os registros."""
        self._used_nodes.clear()
        self._partial_usage.clear()
        self._node_to_fields.clear()
    
    def get_usage_summary(self) -> Dict:
        """Retorna resumo do uso de nós.
        
        Returns:
            Dicionário com estatísticas de uso
        """
        return {
            "total_used": len(self._used_nodes),
            "partially_used": len(self._partial_usage),
            "total_tracked": len(self._node_to_fields),
            "used_nodes": list(self._used_nodes),
            "partially_used_nodes": list(self._partial_usage.keys())
        }
