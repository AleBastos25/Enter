"""Matcher baseado em embeddings semânticos (FastEmbed)."""

import numpy as np
from typing import List, Optional
from src.graph_builder.models import Token, Graph
from src.graph_extractor.models import MatchResult, MatchType
from src.graph_extractor.matchers.base import BaseMatcher


class EmbeddingMatcher(BaseMatcher):
    """Matcher que usa embeddings semânticos para encontrar correspondências.
    
    Usa FastEmbed para gerar embeddings e compara similaridade de cosseno
    entre a descrição do campo e os textos dos nós do grafo.
    """
    
    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5", min_similarity: float = 0.3):
        """Inicializa EmbeddingMatcher.
        
        Args:
            model_name: Nome do modelo FastEmbed a usar
            min_similarity: Similaridade mínima para considerar match (0.0 a 1.0)
        """
        super().__init__()
        self.model_name = model_name
        self.min_similarity = min_similarity
        self._embedding_model = None
        self._cache = {}  # Cache de embeddings para evitar recálculos
    
    def _get_embedding_model(self):
        """Carrega o modelo de embedding (lazy loading).
        
        Returns:
            Modelo de embedding FastEmbed
        """
        if self._embedding_model is None:
            try:
                from fastembed import TextEmbedding
                self._embedding_model = TextEmbedding(model_name=self.model_name)
            except ImportError:
                raise ImportError(
                    "FastEmbed não está instalado. Instale com: pip install fastembed"
                )
        return self._embedding_model
    
    def _extract_keywords_from_description(self, field_description: str) -> List[str]:
        """Extrai palavras-chave relevantes da descrição do campo.
        
        Args:
            field_description: Descrição do campo
            
        Returns:
            Lista de palavras-chave extraídas
        """
        import re
        
        # Remover stop words comuns
        stop_words = {
            'o', 'a', 'de', 'do', 'da', 'em', 'no', 'na', 'para', 'com', 'por', 'e', 'ou', 'um', 'uma',
            'do', 'da', 'dos', 'das', 'que', 'qual', 'quais', 'pode', 'ser', 'são', 'foi', 'está',
            'normalmente', 'geralmente', 'pode', 'ser', 'que', 'qual', 'faz', 'parte', 'selecionada',
            'selecionado', 'operacao', 'operação', 'sistema', 'detalhamento', 'saldos', 'parcelas'
        }
        
        # Extrair palavras
        words = re.findall(r'\b\w+\b', field_description.lower())
        
        # Filtrar: remover stop words e palavras muito curtas
        keywords = [w for w in words if len(w) > 2 and w not in stop_words]
        
        return keywords
    
    def _generate_synonyms_from_keywords(self, keywords: List[str]) -> List[str]:
        """Gera variações e sinônimos comuns a partir de palavras-chave (método geral).
        
        Args:
            keywords: Lista de palavras-chave
            
        Returns:
            Lista de sinônimos e variações
        """
        synonyms = []
        
        for keyword in keywords:
            # Adicionar a palavra original
            synonyms.append(keyword)
            
            # Remover acentos para variações
            import unicodedata
            keyword_no_accents = unicodedata.normalize('NFD', keyword).encode('ascii', 'ignore').decode('ascii')
            if keyword_no_accents != keyword:
                synonyms.append(keyword_no_accents)
            
            # Variações de sufixos comuns
            if keyword.endswith('ção') or keyword.endswith('cao') or keyword.endswith('mento'):
                # "vencimento" -> base "venc"
                if keyword.endswith('mento'):
                    base = keyword[:-6]  # Remove "mento"
                else:
                    base = keyword[:-3]  # Remove "ção" ou "cao"
                
                if base and len(base) >= 3:
                    synonyms.append(base)  # "venc"
                    # Abreviação: pegar consoantes principais de forma inteligente
                    consonants = ''.join([c for c in base if c not in 'aeiou'])
                    if len(consonants) >= 2:
                        # Para palavras como "vencimento" (base "venc" = v-n-c):
                        # Pegar primeira consoante + consoantes do meio (pulando a segunda se houver muitas)
                        if len(consonants) >= 3:
                            # Estratégia: primeira + uma do meio + última
                            # "venc" -> v-n-c -> v + c + o = "vco" (mas queremos "vcto")
                            # Melhor: primeira + segunda do meio + última
                            if len(consonants) == 3:
                                # 3 consoantes: pegar primeira, segunda, última
                                abbrev = consonants[0] + consonants[1] + consonants[2] + 'o'
                            else:
                                # Mais de 3: primeira + uma do meio + última
                                mid_idx = len(consonants) // 2
                                abbrev = consonants[0] + consonants[mid_idx] + consonants[-1] + 'o'
                            synonyms.append(abbrev)
                        elif len(consonants) == 2:
                            # Se só 2 consoantes, usar ambas + 'o'
                            abbrev = consonants[0] + consonants[1] + 'o'
                            synonyms.append(abbrev)
                    
                    # Caso especial: "vencimento" -> "vcto" (v-c-t-o)
                    # Se a palavra original contém "venc" e tem "t" depois, gerar "vcto"
                    if 'venc' in keyword.lower():
                        synonyms.append('vcto')
                    if 'refer' in keyword.lower():
                        synonyms.append('ref')
                    if 'telef' in keyword.lower():
                        synonyms.append('tel')
            
            # Abreviações gerais: pegar primeiras letras significativas
            if len(keyword) > 5:
                # Primeiras 3-4 letras
                synonyms.append(keyword[:3])
                synonyms.append(keyword[:4])
                
                # Abreviação por consoantes principais (primeira + consoantes)
                if len(keyword) > 6:
                    first_char = keyword[0]
                    consonants = ''.join([c for c in keyword[1:] if c not in 'aeiou'])
                    if consonants:
                        abbrev = first_char + consonants[:2] + 'o'
                        if len(abbrev) <= 5:  # Limitar tamanho
                            synonyms.append(abbrev)
            
            # Palavras compostas: "data_vencimento" -> extrair partes
            if '_' in keyword or ' ' in keyword:
                parts = keyword.replace('_', ' ').split()
                synonyms.extend([p for p in parts if len(p) > 2])
        
        # Remover duplicatas e palavras muito curtas
        unique_synonyms = []
        seen = set()
        for syn in synonyms:
            syn_lower = syn.lower()
            if len(syn) >= 2 and syn_lower not in seen:
                seen.add(syn_lower)
                unique_synonyms.append(syn)
        
        return unique_synonyms
    
    def _expand_query_with_synonyms(self, field_name: str, field_description: str) -> str:
        """Expande a query com sinônimos e palavras-chave relevantes (método geral).
        
        Dá mais peso aos sinônimos importantes repetindo-os e priorizando palavras-chave relevantes.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            
        Returns:
            Query expandida com sinônimos (palavras importantes repetidas para dar mais peso)
        """
        # Base query
        query_parts = [field_description]
        
        # Extrair palavras-chave da descrição
        keywords = self._extract_keywords_from_description(field_description)
        
        # Priorizar palavras-chave mais importantes (repetir 2-3 vezes)
        important_keywords = []
        for keyword in keywords:
            # Palavras relacionadas a datas, valores, etc. são mais importantes
            if any(term in keyword.lower() for term in ['venc', 'base', 'refer', 'data', 'valor', 'telef', 'endere']):
                important_keywords.append(keyword)
                important_keywords.append(keyword)  # Repetir para dar mais peso
            else:
                important_keywords.append(keyword)
        
        query_parts.extend(important_keywords)
        
        # Gerar sinônimos a partir das palavras-chave
        synonyms = self._generate_synonyms_from_keywords(keywords)
        
        # Priorizar sinônimos importantes (abreviações comuns como "vcto", "ref", "tel")
        important_synonyms = []
        other_synonyms = []
        for syn in synonyms:
            syn_lower = syn.lower()
            # Sinônimos muito relevantes (abreviações comuns)
            if syn_lower in ['vcto', 'ref', 'tel', 'end', 'venc', 'base', 'refer', 'telef', 'endere']:
                important_synonyms.append(syn)
                important_synonyms.append(syn)  # Repetir para dar mais peso
            else:
                other_synonyms.append(syn)
        
        # Adicionar sinônimos importantes primeiro (com repetição)
        query_parts.extend(important_synonyms)
        query_parts.extend(other_synonyms)
        
        # Adicionar palavras-chave do nome do campo (se tiver underscore)
        if '_' in field_name:
            field_keywords = field_name.split('_')
            # Adicionar palavras significativas do nome do campo (repetir se importante)
            for keyword in field_keywords:
                if len(keyword) > 3:
                    query_parts.append(keyword)
                    # Se for palavra importante, repetir
                    if any(term in keyword.lower() for term in ['venc', 'base', 'refer', 'data', 'valor']):
                        query_parts.append(keyword)
        
        # Combinar tudo (manter duplicatas de palavras importantes, remover outras)
        seen = set()
        unique_parts = []
        for part in query_parts:
            part_lower = part.lower()
            # Permitir duplicatas de palavras importantes
            if part_lower in ['vcto', 'ref', 'tel', 'vencimento', 'venc', 'base', 'referencia', 'refer']:
                unique_parts.append(part)
            elif part_lower not in seen:
                seen.add(part_lower)
                unique_parts.append(part)
        
        expanded_query = " ".join(unique_parts)
        return expanded_query
    
    def _calculate_keyword_boost(
        self, 
        field_name: str,
        field_description: str,
        label_text: Optional[str], 
        token_text: str
    ) -> float:
        """Calcula boost baseado em palavras-chave no label (método geral).
        
        Extrai palavras-chave da descrição e verifica se aparecem no label.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            label_text: Texto do label (se disponível)
            token_text: Texto do token
            
        Returns:
            Boost multiplicador (1.0 = sem boost, >1.0 = boost positivo)
        """
        if not label_text:
            return 1.0
        
        label_lower = label_text.lower()
        
        # Extrair palavras-chave da descrição
        keywords = self._extract_keywords_from_description(field_description)
        
        # Gerar sinônimos
        synonyms = self._generate_synonyms_from_keywords(keywords)
        all_keywords = keywords + synonyms
        
        # Verificar quantas palavras-chave aparecem no label
        matches = 0
        important_matches = 0  # Matches com sinônimos importantes (vcto, ref, tel, etc.)
        
        # Sinônimos muito importantes (abreviações comuns)
        important_synonyms = ['vcto', 'ref', 'tel', 'end', 'venc', 'base', 'refer', 'telef', 'endere']
        
        for keyword in all_keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in label_lower:
                matches += 1
                # Se for sinônimo importante, contar separadamente
                if keyword_lower in important_synonyms:
                    important_matches += 1
        
        # Boost proporcional ao número de matches
        if matches > 0:
            # Boost base: 5% por match normal
            boost = 1.0 + (min(matches, 3) * 0.05)
            
            # Boost extra para sinônimos importantes (abreviações como "vcto")
            # Cada sinônimo importante adiciona 10% extra
            if important_matches > 0:
                boost += (important_matches * 0.10)  # 10% extra por sinônimo importante
            
            return min(boost, 1.35)  # Limitar a 35% de boost total
        
        return 1.0
    
    def match(
        self,
        field_name: str,
        field_description: str,
        candidates: List[Token],
        graph: Optional[Graph] = None
    ) -> List[MatchResult]:
        """Encontra candidatos usando similaridade semântica.
        
        Args:
            field_name: Nome do campo
            field_description: Descrição do campo
            candidates: Lista de nós candidatos
            graph: Grafo completo (para encontrar VALUEs associados)
            
        Returns:
            Lista de MatchResult ordenada por score (similaridade)
        """
        if not candidates:
            return []
        
        # Expandir query com sinônimos
        expanded_query = self._expand_query_with_synonyms(field_name, field_description)
        
        # Gerar embedding da query expandida
        query_embedding = self._get_embedding(expanded_query)
        if query_embedding is None:
            return []
        
        matches = []
        
        # Para cada candidato, calcular similaridade
        for token in candidates:
            # Obter valor do token
            token_value = self.get_token_value(token, graph)
            
            # Tentar match com LABEL+VALUE se disponível
            if token.role == "VALUE" and graph:
                label_token = self.find_label_for_value(token, graph)
                if label_token:
                    combined_text = self.combine_label_value(label_token, token)
                    score = self._calculate_similarity(query_embedding, combined_text)
                    
                    # Aplicar boost se houver palavras-chave no label
                    boost = self._calculate_keyword_boost(field_name, field_description, label_token.text, token.text)
                    score = min(1.0, score * boost)  # Limitar a 1.0
                    
                    # Criar match result
                    match_result = self._create_match_result(
                        token, score, expanded_query, combined_text, label_token, graph
                    )
                    if match_result:
                        matches.append(match_result)
                        continue  # Se já fez match com LABEL+VALUE, não precisa verificar só VALUE
            
            # Match apenas com VALUE ou HEADER
            score = self._calculate_similarity(query_embedding, token_value)
            
            # Se há label associado, aplicar boost
            if graph:
                label_token = self.find_label_for_value(token, graph)
                if label_token:
                    boost = self._calculate_keyword_boost(field_name, field_description, label_token.text, token.text)
                    score = min(1.0, score * boost)
            
            match_result = self._create_match_result(
                token, score, expanded_query, token_value, None, graph
            )
            if match_result:
                matches.append(match_result)
        
        # Ordenar por score
        return self.sort_by_score(matches)
    
    def _get_embedding(self, text: str) -> Optional[np.ndarray]:
        """Obtém embedding de um texto (com cache).
        
        Args:
            text: Texto para gerar embedding
            
        Returns:
            Embedding como numpy array ou None se falhar
        """
        if not text or not text.strip():
            return None
        
        # Verificar cache
        text_key = text.strip().lower()
        if text_key in self._cache:
            return self._cache[text_key]
        
        try:
            model = self._get_embedding_model()
            # FastEmbed retorna um generator, precisa converter para lista
            embeddings = list(model.embed([text]))
            if embeddings:
                embedding = embeddings[0]
                # Normalizar embedding (unit vector)
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                
                # Armazenar no cache
                self._cache[text_key] = embedding
                return embedding
        except Exception as e:
            # Em caso de erro, retornar None
            print(f"Erro ao gerar embedding: {e}")
            return None
        
        return None
    
    def _calculate_similarity(self, query_embedding: np.ndarray, text: str) -> float:
        """Calcula similaridade de cosseno entre query e texto.
        
        Args:
            query_embedding: Embedding da query (já normalizado)
            text: Texto para comparar
            
        Returns:
            Similaridade de cosseno (0.0 a 1.0)
        """
        text_embedding = self._get_embedding(text)
        if text_embedding is None:
            return 0.0
        
        # Calcular cosseno (já estão normalizados, então é produto escalar)
        similarity = np.dot(query_embedding, text_embedding)
        
        # Garantir que está entre 0 e 1 (cosseno pode ser negativo)
        # Normalizar para [0, 1] usando (cos + 1) / 2
        similarity = (similarity + 1.0) / 2.0
        
        return float(similarity)
    
    def _create_match_result(
        self,
        token: Token,
        score: float,
        query_text: str,
        matched_text: str,
        label_token: Optional[Token],
        graph: Optional[Graph]
    ) -> Optional[MatchResult]:
        """Cria MatchResult se score for suficiente.
        
        Args:
            token: Token candidato
            score: Score de similaridade
            query_text: Texto da query (nome + descrição do campo)
            matched_text: Texto do token que fez match
            label_token: Token LABEL associado (se houver)
            graph: Grafo completo
            
        Returns:
            MatchResult se score >= min_similarity, None caso contrário
        """
        if score < self.min_similarity:
            return None
        
        # Se não encontrou label_token ainda, tentar encontrar
        if label_token is None and token.role == "VALUE" and graph:
            label_token = self.find_label_for_value(token, graph)
        
        # Determinar tipo de match baseado no score
        if score >= 0.8:
            match_type = MatchType.EMBEDDING  # Alta similaridade
        else:
            match_type = MatchType.PARTIAL  # Similaridade moderada
        
        reason = f"Semantic similarity: {score:.3f} (query: '{query_text[:50]}...', matched: '{matched_text[:50]}...')"
        if label_token:
            reason += f" (LABEL: '{label_token.text}')"
        
        return MatchResult(
            token=token,
            score=score,
            match_type=match_type,
            reason=reason,
            label_token=label_token,
            extracted_value=token.text.strip()
        )
    
    def clear_cache(self) -> None:
        """Limpa o cache de embeddings."""
        self._cache.clear()
    
    def batch_embed(self, texts: List[str]) -> List[Optional[np.ndarray]]:
        """Gera embeddings em batch (mais eficiente).
        
        Args:
            texts: Lista de textos para gerar embeddings
            
        Returns:
            Lista de embeddings (pode conter None se falhar)
        """
        if not texts:
            return []
        
        try:
            model = self._get_embedding_model()
            # Gerar embeddings em batch
            embeddings = list(model.embed(texts))
            
            results = []
            for i, embedding in enumerate(embeddings):
                # Normalizar
                norm = np.linalg.norm(embedding)
                if norm > 0:
                    embedding = embedding / norm
                
                # Armazenar no cache
                text_key = texts[i].strip().lower()
                self._cache[text_key] = embedding
                
                results.append(embedding)
            
            return results
        except Exception as e:
            print(f"Erro ao gerar embeddings em batch: {e}")
            return [None] * len(texts)
