"""Orquestrador de classificação de roles."""

from typing import List, Dict, Optional, Tuple
from src.graph_builder.models import Token, Graph
from src.graph_builder.adjacency import AdjacencyMatrix
from src.graph_builder.rules.base import BaseRule, RuleContext
from src.graph_builder.rules.initial import (
    InitialLabelRule,
    InitialValueRule,
    InitialHeaderRule,
    LabelOnlyConnectionsRule
)
from src.graph_builder.rules.final import (
    HeaderPreservationRule,
    ValueLabelUniquenessRule,
    TypographicHierarchyRule,
    NumericCodeLabelRule,
    DateLabelCleanupRule,
    LabelWithoutEdgesRule,
    IsolatedShortTextHeaderRule,
    ValueLabelGuaranteeRule,
    ValueMustHaveLabelRule,
    ColonRecursiveRule,
    HeaderNoNorthWestRule,
    HeaderNoNorthRule,
    ValueNoLabelConnectionsRule,
    LabelSingleValueRule,
    SeparatedPairIsolationRule
)
from src.graph_builder.table_detector import TableDetector, Table, TableOrientation


class RoleClassifier:
    """Orquestrador principal de classificação de roles."""
    
    def __init__(self):
        """Inicializa o classificador com todas as regras."""
        self.rules: List[BaseRule] = []
        self.rule_registry: Dict[str, BaseRule] = {}
        self._register_default_rules()
    
    def _register_default_rules(self) -> None:
        """Registra todas as regras padrão."""
        default_rules = [
            InitialLabelRule(),
            InitialValueRule(),
            InitialHeaderRule(),
            LabelOnlyConnectionsRule(),
            SeparatedPairIsolationRule(),  # Isola pares LABEL-VALUE separados de um único span
            HeaderPreservationRule(),
            ValueLabelUniquenessRule(),
            TypographicHierarchyRule(),
            NumericCodeLabelRule(),
            DateLabelCleanupRule(),
            LabelWithoutEdgesRule(),
            IsolatedShortTextHeaderRule(),  # Reclassifica tokens isolados de VALUE para HEADER
            ValueLabelGuaranteeRule(),
            ValueMustHaveLabelRule(),  # ALTA PRIORIDADE: Garante que VALUE sempre tem LABEL
            ColonRecursiveRule(),
            HeaderNoNorthRule(),
            ValueNoLabelConnectionsRule(),
            LabelSingleValueRule(),  # Remove edges extras de LABEL para VALUE
            HeaderNoNorthWestRule(),  # PRIORIDADE MÁXIMA - Remove edges de HEADER para north/west (executar no final)
        ]
        
        for rule in default_rules:
            self.register_rule(rule)
    
    def register_rule(self, rule: BaseRule) -> None:
        """Registra uma regra.
        
        Args:
            rule: Regra a ser registrada.
        """
        self.rules.append(rule)
        self.rule_registry[rule.name] = rule
    
    def classify(
        self,
        tokens: List[Token],
        graph: Graph,
        label: Optional[str] = None
    ) -> Tuple[Dict[int, str], List[Table]]:
        """Classifica roles de todos os tokens e detecta tabelas.
        
        Args:
            tokens: Lista de tokens.
            graph: Grafo com nodes e edges.
            label: Label do documento (opcional, para memória).
        
        Returns:
            Tupla (dicionário mapping token_id -> role, lista de tabelas detectadas).
        """
        # Criar contexto
        adjacency = AdjacencyMatrix(graph)
        
        # Detectar tabelas
        table_detector = TableDetector()
        tables = table_detector.detect_tables(tokens, graph, adjacency)
        
        # Inicializar roles com roles já definidos nos tokens (ex: padrão múltiplos dois pontos)
        initial_roles = {}
        for token in tokens:
            if token.role:
                initial_roles[token.id] = token.role
        
        # Inicializar role_sources para roles já definidos (ex: padrão múltiplos dois pontos)
        initial_role_sources = {}
        for token in tokens:
            if token.role:
                # Marcar como vindo da extração (padrão múltiplos dois pontos)
                initial_role_sources[token.id] = "TokenExtractor"
        
        context = RuleContext(
            tokens=tokens,
            graph=graph,
            roles=initial_roles,  # Preservar roles já definidos
            adjacency=adjacency,
            label_candidates=[],
            label_to_value={},
            value_to_label={},
            label=label,
            role_sources=initial_role_sources  # Rastrear origem dos roles
        )
        
        # Ordenar regras por prioridade e dependências
        sorted_rules = self._sort_rules_by_priority()
        
        # Aplicar classificação baseada em tabelas ANTES das regras (alta prioridade)
        self._apply_table_classification(context, tables)
        
        # Salvar roles definidos por tabelas para preservá-los
        table_roles = {}
        for table in tables:
            if table.orientation == TableOrientation.UNKNOWN:
                continue
            for cell in table.cells:
                if table.orientation == TableOrientation.VERTICAL:
                    if cell.col == 0:
                        table_roles[cell.token_id] = "LABEL"
                    elif cell.col == 1:
                        table_roles[cell.token_id] = "VALUE"
                elif table.orientation == TableOrientation.HORIZONTAL:
                    if cell.row == 0:
                        table_roles[cell.token_id] = "LABEL"
                    elif cell.row == 1:
                        table_roles[cell.token_id] = "VALUE"
        
        # Executar regras na ordem
        executed_rules = []
        for rule in sorted_rules:
            # Verificar se pode executar (dependências satisfeitas)
            if rule.can_apply(executed_rules):
                rule.apply(context)
                executed_rules.append(rule.name)
        
        # Restaurar roles de tabelas (prioridade máxima - não podem ser sobrescritos)
        for token_id, role in table_roles.items():
            context.set_role(token_id, role, source_rule="TableDetector")
        
        # Aplicar roles aos tokens
        # IMPORTANTE: Preservar roles já definidos durante extração (padrão múltiplos dois pontos)
        # Esses roles têm prioridade sobre as regras de classificação
        for token in tokens:
            token_id = token.id
            # Se o token já tinha role definido durante extração, preservar
            original_role = token.role
            if original_role and token_id in context.roles:
                # Se o role no contexto é diferente do original, restaurar o original
                if context.roles[token_id] != original_role:
                    context.roles[token_id] = original_role
                    token.role = original_role
                else:
                    token.role = context.roles[token_id]
            elif token_id in context.roles:
                token.role = context.roles[token_id]
        
        return context.roles, tables
    
    def _apply_table_classification(self, context: RuleContext, tables: List[Table]) -> None:
        """Aplica classificação de roles baseada em tabelas detectadas.
        
        Regras:
        - Tabelas verticais (2+ colunas): primeira coluna = LABEL, segunda coluna = VALUE
        - Tabelas horizontais (2+ linhas): primeira linha = LABEL, segunda linha = VALUE
        - Tabelas 2x2 (UNKNOWN): não aplicar classificação automática
        """
        for table in tables:
            # Pular tabelas 2x2 (UNKNOWN)
            if table.orientation == TableOrientation.UNKNOWN:
                continue
            
            if table.orientation == TableOrientation.VERTICAL:
                # Tabela vertical: primeira coluna (col 0) = LABELs, segunda coluna (col 1) = VALUEs
                for cell in table.cells:
                    if cell.col == 0:
                        # Primeira coluna: LABELs
                        context.set_role(cell.token_id, "LABEL", source_rule="TableDetector")
                        if cell.token_id not in context.label_candidates:
                            context.label_candidates.append(cell.token_id)
                    elif cell.col == 1:
                        # Segunda coluna: VALUEs
                        context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                        # Associar LABEL da mesma linha
                        label_cell = table.get_cell(cell.row, 0)
                        if label_cell:
                            context.value_to_label[cell.token_id] = label_cell.token_id
                            context.label_to_value[label_cell.token_id] = cell.token_id
            
            elif table.orientation == TableOrientation.HORIZONTAL:
                # Tabela horizontal: primeira linha (row 0) = LABELs, segunda linha (row 1) = VALUEs
                for cell in table.cells:
                    if cell.row == 0:
                        # Primeira linha: LABELs
                        context.set_role(cell.token_id, "LABEL", source_rule="TableDetector")
                        if cell.token_id not in context.label_candidates:
                            context.label_candidates.append(cell.token_id)
                    elif cell.row == 1:
                        # Segunda linha: VALUEs
                        context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                        # Associar LABEL da mesma coluna
                        label_cell = table.get_cell(0, cell.col)
                        if label_cell:
                            context.value_to_label[cell.token_id] = label_cell.token_id
                            context.label_to_value[label_cell.token_id] = cell.token_id
    
    def _sort_rules_by_priority(self) -> List[BaseRule]:
        """Ordena regras por prioridade e dependências.
        
        Returns:
            Lista de regras ordenadas.
        """
        # Ordenar por prioridade primeiro
        sorted_rules = sorted(self.rules, key=lambda r: r.priority)
        
        # Verificar dependências e reordenar se necessário
        # Usar algoritmo de ordenação topológica simples
        result = []
        remaining = sorted_rules.copy()
        executed_names = set()
        
        while remaining:
            # Encontrar regra sem dependências não satisfeitas
            found = False
            for rule in remaining:
                if rule.can_apply(list(executed_names)):
                    result.append(rule)
                    remaining.remove(rule)
                    executed_names.add(rule.name)
                    found = True
                    break
            
            if not found:
                # Se não encontrou, adicionar a de menor prioridade (pode ter dependência circular)
                rule = remaining[0]
                result.append(rule)
                remaining.remove(rule)
                executed_names.add(rule.name)
        
        return result

