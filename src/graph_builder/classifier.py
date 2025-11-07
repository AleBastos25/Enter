"""Orquestrador de classificação de roles."""

import re
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
    SeparatedPairIsolationRule,
    AdjacentHeadersToLabelValueRule
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
            AdjacentHeadersToLabelValueRule(),  # ÚLTIMA: Converte HEADERs adjacentes em LABEL + VALUE
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
        # IMPORTANTE: Usar os roles já definidos em context.roles (que foram aplicados por _apply_table_classification)
        table_roles = {}
        for table in tables:
            if table.orientation == TableOrientation.UNKNOWN:
                continue
            
            # Verificar se tem padrão de duas colunas de labels
            has_double_label_pattern = self._detect_double_label_pattern(table, context)
            
            for cell in table.cells:
                # Usar o role já definido em context.roles (aplicado por _apply_table_classification)
                if cell.token_id in context.roles:
                    table_roles[cell.token_id] = context.roles[cell.token_id]
        
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
    
    def _detect_double_label_pattern(self, table: Table, context: RuleContext) -> bool:
        """Detecta se uma tabela tem padrão de duas colunas de labels (não label-value).
        
        Padrões que indicam duas colunas de labels:
        1. Última linha tem dois valores (números, datas, valores monetários)
        2. Qualquer linha tem dois valores do mesmo tipo (dois números, duas datas, etc.)
        3. Padrões de linguagem que indicam que ambos são labels (ex: "produto refinanciamento" e "sistema consignado")
        
        Args:
            table: Tabela a verificar
            context: Contexto com tokens e roles
            
        Returns:
            True se detectou padrão de duas colunas de labels
        """
        if table.orientation == TableOrientation.VERTICAL:
            max_row = max(cell.row for cell in table.cells)
            max_col = max(cell.col for cell in table.cells)
            
            if max_col < 1:
                return False
            
            # Verificar cada linha
            for row in range(max_row + 1):
                col0_cell = table.get_cell(row, 0)
                col1_cell = table.get_cell(row, 1)
                
                if not col0_cell or not col1_cell:
                    continue
                
                token0 = col0_cell.token
                token1 = col1_cell.token
                
                # Padrão 1: Última linha tem dois valores
                if row == max_row:
                    # Verificar se ambos são valores (números, datas, valores monetários)
                    is_value0 = token0.is_date() or token0.is_numeric_code() or token0.is_number()
                    is_value1 = token1.is_date() or token1.is_numeric_code() or token1.is_number()
                    
                    if is_value0 and is_value1:
                        return True
                
                # Padrão 2: Dois valores do mesmo tipo na mesma linha
                if token0.is_date() and token1.is_date():
                    return True
                if token0.is_numeric_code() and token1.is_numeric_code():
                    return True
                if token0.is_number() and token1.is_number():
                    return True
                
                # Padrão 3: Padrões de linguagem que indicam labels
                # Ex: "produto refinanciamento" e "sistema consignado"
                text0 = token0.text.strip().lower()
                text1 = token1.text.strip().lower()
                
                # Verificar se ambos são textos (não valores) e têm características de labels
                if (not token0.is_date() and not token0.is_numeric_code() and not token0.is_number() and
                    not token1.is_date() and not token1.is_numeric_code() and not token1.is_number()):
                    # Ambos são textos - verificar se têm características de labels
                    # Labels geralmente são substantivos ou frases curtas
                    # Se ambos são textos e não terminam com ":", podem ser labels
                    if (not text0.endswith(":") and not text1.endswith(":") and
                        len(text0.split()) <= 4 and len(text1.split()) <= 4):
                        # Verificar se há palavras-chave comuns em labels
                        label_keywords = ["produto", "sistema", "tipo", "categoria", "classe", "grupo", 
                                        "refinanciamento", "consignado", "operacao", "operação"]
                        # Se ambos contêm palavras-chave de label, são labels
                        has_keyword0 = any(kw in text0 for kw in label_keywords)
                        has_keyword1 = any(kw in text1 for kw in label_keywords)
                        
                        if has_keyword0 and has_keyword1:
                            return True
                        
                        # Também verificar se ambos são substantivos/frases curtas sem números
                        # e não parecem valores (não começam com números, não têm símbolos monetários)
                        if (not re.match(r'^\d', text0) and not re.match(r'^\d', text1) and
                            not any(c in text0 for c in ['$', '€', '£', 'R$']) and
                            not any(c in text1 for c in ['$', '€', '£', 'R$']) and
                            len(text0) > 3 and len(text1) > 3):
                            # Se ambos são textos significativos e não valores, podem ser labels
                            # Verificar se pelo menos um tem palavra-chave
                            if has_keyword0 or has_keyword1:
                                return True
        
        elif table.orientation == TableOrientation.HORIZONTAL:
            max_row = max(cell.row for cell in table.cells)
            max_col = max(cell.col for cell in table.cells)
            
            if max_row < 1:
                return False
            
            # Verificar se a linha 1 (segunda linha) tem principalmente valores
            # Se a linha 1 tem muitos valores (datas, números, valores monetários),
            # isso indica que ambas as linhas 0 e 1 são LABELs, não label-value
            row1_value_count = 0
            row1_total = 0
            row0_label_count = 0
            row0_total = 0
            
            for col in range(max_col + 1):
                row0_cell = table.get_cell(0, col)
                row1_cell = table.get_cell(1, col)
                
                if row1_cell:
                    row1_total += 1
                    token1 = row1_cell.token
                    if token1.is_date() or token1.is_numeric_code() or token1.is_number():
                        row1_value_count += 1
                
                if row0_cell:
                    row0_total += 1
                    token0 = row0_cell.token
                    # Verificar se é label (texto, não valor)
                    if (not token0.is_date() and not token0.is_numeric_code() and not token0.is_number() and
                        not token0.text.strip().endswith(":")):
                        row0_label_count += 1
            
            # Se a linha 1 tem principalmente valores (mais de 50% são valores),
            # e a linha 0 tem principalmente labels, então ambas são labels
            if row1_total > 0 and row0_total > 0:
                row1_value_ratio = row1_value_count / row1_total
                row0_label_ratio = row0_label_count / row0_total
                
                if row1_value_ratio > 0.5 and row0_label_ratio > 0.5:
                    return True
            
            # Verificar cada coluna
            for col in range(max_col + 1):
                row0_cell = table.get_cell(0, col)
                row1_cell = table.get_cell(1, col)
                
                if not row0_cell or not row1_cell:
                    continue
                
                token0 = row0_cell.token
                token1 = row1_cell.token
                
                # Padrão 1: Última coluna tem dois valores
                if col == max_col:
                    is_value0 = token0.is_date() or token0.is_numeric_code() or token0.is_number()
                    is_value1 = token1.is_date() or token1.is_numeric_code() or token1.is_number()
                    
                    if is_value0 and is_value1:
                        return True
                
                # Padrão 2: Dois valores do mesmo tipo na mesma coluna
                if token0.is_date() and token1.is_date():
                    return True
                if token0.is_numeric_code() and token1.is_numeric_code():
                    return True
                if token0.is_number() and token1.is_number():
                    return True
                
                # Padrão 3: Padrões de linguagem
                text0 = token0.text.strip().lower()
                text1 = token1.text.strip().lower()
                
                if (not token0.is_date() and not token0.is_numeric_code() and not token0.is_number() and
                    not token1.is_date() and not token1.is_numeric_code() and not token1.is_number()):
                    if (not text0.endswith(":") and not text1.endswith(":") and
                        len(text0.split()) <= 4 and len(text1.split()) <= 4):
                        label_keywords = ["produto", "sistema", "tipo", "categoria", "classe", "grupo",
                                         "refinanciamento", "consignado", "operacao", "operação"]
                        has_keyword0 = any(kw in text0 for kw in label_keywords)
                        has_keyword1 = any(kw in text1 for kw in label_keywords)
                        
                        if has_keyword0 and has_keyword1:
                            return True
                        
                        # Verificar se ambos são textos significativos
                        if (not re.match(r'^\d', text0) and not re.match(r'^\d', text1) and
                            not any(c in text0 for c in ['$', '€', '£', 'R$']) and
                            not any(c in text1 for c in ['$', '€', '£', 'R$']) and
                            len(text0) > 3 and len(text1) > 3):
                            if has_keyword0 or has_keyword1:
                                return True
        
        return False
    
    def _apply_table_classification(self, context: RuleContext, tables: List[Table]) -> None:
        """Aplica classificação de roles baseada em tabelas detectadas.
        
        Regras:
        - Tabelas verticais (2+ colunas): primeira coluna = LABEL, segunda coluna = VALUE
        - Tabelas horizontais (2+ linhas): primeira linha = LABEL, segunda linha = VALUE
        - Tabelas 2x2 (UNKNOWN): não aplicar classificação automática
        
        Exceção: Se detectar padrão de duas colunas de labels, classificar como:
        - Tabelas verticais: colunas pares (0, 2, 4...) = LABELs, colunas ímpares (1, 3, 5...) = VALUEs
        - Tabelas horizontais: linhas pares (0, 2, 4...) = LABELs, linhas ímpares (1, 3, 5...) = VALUEs
        """
        for table in tables:
            # Pular tabelas 2x2 (UNKNOWN)
            if table.orientation == TableOrientation.UNKNOWN:
                continue
            
            # Verificar se tem padrão de duas colunas de labels
            has_double_label_pattern = self._detect_double_label_pattern(table, context)
            
            if table.orientation == TableOrientation.VERTICAL:
                if has_double_label_pattern:
                    # Padrão de duas colunas de labels: primeira linha tem duas colunas de LABELs
                    # Estrutura: 
                    # Linha 0: Label (col 0), Label (col 1)
                    # Linha 1: Value (col 0, de Label col 0), Value (col 1, de Label col 1)
                    # Linha 2: Label (col 0), Label (col 1)
                    # Linha 3: Value (col 0, de Label col 0), Value (col 1, de Label col 1)
                    # etc.
                    max_col = max(cell.col for cell in table.cells)
                    max_row = max(cell.row for cell in table.cells)
                    
                    for cell in table.cells:
                        # Se está nas duas primeiras colunas (0 ou 1)
                        if cell.col < 2:
                            # Linhas pares (0, 2, 4...) = LABELs
                            # Linhas ímpares (1, 3, 5...) = VALUEs
                            if cell.row % 2 == 0:
                                context.set_role(cell.token_id, "LABEL", source_rule="TableDetector")
                                if cell.token_id not in context.label_candidates:
                                    context.label_candidates.append(cell.token_id)
                            else:
                                context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                                # Associar ao LABEL correspondente na linha par anterior (mesma coluna)
                                label_row = cell.row - 1
                                label_cell = table.get_cell(label_row, cell.col)
                                if label_cell:
                                    context.value_to_label[cell.token_id] = label_cell.token_id
                                    context.label_to_value[label_cell.token_id] = cell.token_id
                        else:
                            # Colunas 2+ são VALUEs (associados aos labels das colunas 0 e 1)
                            context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                            # Associar ao LABEL correspondente na mesma linha (col 0 ou 1)
                            # Se col é par (2, 4, 6...), associar a col 0
                            # Se col é ímpar (3, 5, 7...), associar a col 1
                            label_col = 0 if cell.col % 2 == 0 else 1
                            # Encontrar o label correspondente na linha par mais próxima
                            label_row = cell.row if cell.row % 2 == 0 else cell.row - 1
                            label_cell = table.get_cell(label_row, label_col)
                            if label_cell:
                                context.value_to_label[cell.token_id] = label_cell.token_id
                                if label_cell.token_id not in context.label_to_value:
                                    context.label_to_value[label_cell.token_id] = []
                                if not isinstance(context.label_to_value[label_cell.token_id], list):
                                    context.label_to_value[label_cell.token_id] = [context.label_to_value[label_cell.token_id]]
                                if cell.token_id not in context.label_to_value[label_cell.token_id]:
                                    context.label_to_value[label_cell.token_id].append(cell.token_id)
                else:
                    # Padrão padrão: primeira coluna (col 0) = LABELs, segunda coluna (col 1) = VALUEs
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
                if has_double_label_pattern:
                    # Padrão detectado: linha 0 tem principalmente labels, linha 1 tem principalmente values
                    # Estrutura: Linha 0 = todos LABELs, Linha 1 = todos VALUEs
                    # (mesmo que alguns values estejam "apagados", a estrutura é essa)
                    max_row = max(cell.row for cell in table.cells)
                    max_col = max(cell.col for cell in table.cells)
                    
                    for cell in table.cells:
                        if cell.row == 0:
                            # Linha 0: todos LABELs
                            context.set_role(cell.token_id, "LABEL", source_rule="TableDetector")
                            if cell.token_id not in context.label_candidates:
                                context.label_candidates.append(cell.token_id)
                        elif cell.row == 1:
                            # Linha 1: todos VALUEs (associados aos labels da linha 0, mesma coluna)
                            context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                            label_cell = table.get_cell(0, cell.col)
                            if label_cell:
                                context.value_to_label[cell.token_id] = label_cell.token_id
                                context.label_to_value[label_cell.token_id] = cell.token_id
                        else:
                            # Linhas 2+: seguir padrão alternado (linhas pares = LABELs, ímpares = VALUEs)
                            if cell.row % 2 == 0:
                                context.set_role(cell.token_id, "LABEL", source_rule="TableDetector")
                                if cell.token_id not in context.label_candidates:
                                    context.label_candidates.append(cell.token_id)
                            else:
                                context.set_role(cell.token_id, "VALUE", source_rule="TableDetector")
                                # Associar ao LABEL da linha par anterior (mesma coluna)
                                label_row = cell.row - 1
                                label_cell = table.get_cell(label_row, cell.col)
                                if label_cell:
                                    context.value_to_label[cell.token_id] = label_cell.token_id
                                    context.label_to_value[label_cell.token_id] = cell.token_id
                else:
                    # Padrão padrão: primeira linha (row 0) = LABELs, segunda linha (row 1) = VALUEs
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

