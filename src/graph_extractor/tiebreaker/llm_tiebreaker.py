"""Tiebreaker baseado em LLM (GPT)."""

import json
import os
import re
import time
from typing import List, Optional
from src.graph_builder.models import Graph, Token
from src.graph_extractor.models import MatchResult
from src.graph_extractor.tiebreaker.base import BaseTieBreaker

# Importar debug helper se disponível
try:
    import sys
    from pathlib import Path
    backend_src = Path(__file__).parent.parent.parent.parent / "backend" / "src"
    if str(backend_src) not in sys.path:
        sys.path.insert(0, str(backend_src))
    from utils.debug import debug_print, get_debug_mode
except ImportError:
    # Fallback se não conseguir importar
    def debug_print(*args, **kwargs):
        pass
    def get_debug_mode():
        return False


class LLMTieBreaker(BaseTieBreaker):
    """Tiebreaker que usa LLM (GPT) para desempatar entre candidatos.
    
    Usado quando as heurísticas não são suficientes para desempatar.
    O LLM recebe contexto claro sobre os candidatos e escolhe o melhor.
    """
    
    def __init__(
        self,
        model: str = "gpt-5-mini",
        api_key: Optional[str] = None,
        timeout: int = 8,
        max_retries: int = 2
    ):
        """Inicializa LLMTieBreaker.
        
        Args:
            model: Modelo GPT a usar (default: gpt-4o-mini)
            api_key: Chave da API OpenAI (opcional)
            timeout: Timeout em segundos
            max_retries: Número máximo de tentativas
        """
        super().__init__()
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.api_key = api_key or self._load_api_key()
        self.debug = False  # Pode ser habilitado externamente
        
        if not self.api_key:
            raise ValueError(
                "API key não encontrada. Configure OPENAI_API_KEY como variável de ambiente "
                "ou forneça via parâmetro api_key ou configure em configs/secrets.yaml"
            )
        
        from openai import OpenAI
        self.client = OpenAI(api_key=self.api_key)
    
    def _load_api_key(self) -> str:
        """Carrega API key do arquivo de secrets ou variável de ambiente."""
        try:
            secrets_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "configs",
                "secrets.yaml"
            )
            try:
                import yaml
            except ImportError:
                yaml = None
            
            if yaml:
                with open(secrets_path, "r", encoding="utf-8") as f:
                    secrets = yaml.safe_load(f)
                    return (
                        secrets.get("OPEN_API_KEY") or
                        secrets.get("OPENAI_API_KEY") or
                        os.getenv("OPENAI_API_KEY", "")
                    )
        except Exception:
            pass
        
        return os.getenv("OPENAI_API_KEY", "")
    
    def break_tie(
        self,
        candidates: List[MatchResult],
        graph: Graph,
        field_description: str
    ) -> MatchResult:
        """Desempata entre candidatos usando LLM.
        
        Args:
            candidates: Lista de MatchResult candidatos
            graph: Grafo completo (para contexto)
            field_description: Descrição do campo a ser extraído
            
        Returns:
            MatchResult escolhido pelo LLM
        """
        if not candidates:
            raise ValueError("Lista de candidatos vazia")
        
        if len(candidates) == 1:
            return candidates[0]
        
        # Construir prompt para desempate
        prompt = self._build_tiebreak_prompt(candidates, field_description, graph)
        
        # Chamar LLM
        selected_index = self._call_llm(prompt, len(candidates))
        
        # Validar índice retornado
        if selected_index is None or not (0 <= selected_index < len(candidates)):
            # Fallback: retornar primeiro candidato (maior score)
            return candidates[0]
        
        return candidates[selected_index]
    
    def _build_tiebreak_prompt(
        self,
        candidates: List[MatchResult],
        field_description: str,
        graph: Graph
    ) -> str:
        """Constrói prompt claro para desempate via LLM.
        
        Args:
            candidates: Lista de candidatos
            field_description: Descrição do campo
            graph: Grafo completo
            
        Returns:
            Prompt formatado
        """
        # Preparar informações de cada candidato
        candidates_info = []
        for i, candidate in enumerate(candidates):
            token = candidate.token
            label_info = ""
            if candidate.label_token:
                label_info = f" (LABEL associado: '{candidate.label_token.text}')"
            
            # Informações de posição
            position = f"Posição: Y={token.bbox.center_y():.3f}, X={token.bbox.center_x():.3f}"
            
            candidate_info = f"""
Candidato {i + 1}:
- Texto: "{token.text.strip()}"
- Tipo: {token.role}
- Score de similaridade: {candidate.score:.3f}
- {position}{label_info}
- Motivo do match: {candidate.reason}
"""
            candidates_info.append(candidate_info)
        
        candidates_text = "\n".join(candidates_info)
        
        prompt = f"""Você precisa escolher o melhor candidato para extrair o valor do campo descrito abaixo.

DESCRIÇÃO DO CAMPO:
{field_description}

CANDIDATOS (múltiplos nós do grafo que podem corresponder ao campo):
{candidates_text}

CONTEXTO:
- Todos os candidatos têm scores de similaridade muito próximos (empate técnico)
- Você precisa escolher o candidato que melhor corresponde à descrição do campo
- Considere:
  1. O texto do candidato corresponde melhor à descrição?
  2. O tipo (VALUE, HEADER, LABEL) é mais apropriado?
  3. Se há LABEL associado, ele faz sentido com o campo?
  4. A posição no documento é relevante?

INSTRUÇÕES:
1. Analise cada candidato cuidadosamente
2. Escolha o candidato que melhor corresponde à descrição do campo
3. Retorne APENAS um número (1, 2, 3, etc.) correspondente ao candidato escolhido
4. Não inclua texto adicional, apenas o número

RESPOSTA (número do candidato):"""
        
        return prompt
    
    def _call_llm(self, prompt: str, num_candidates: int) -> Optional[int]:
        """Chama o LLM para escolher candidato.
        
        Args:
            prompt: Prompt formatado
            num_candidates: Número de candidatos (para validação)
            
        Returns:
            Índice do candidato escolhido (0-based) ou None se falhar
        """
        for attempt in range(self.max_retries):
            try:
                # Preparar parâmetros da chamada
                create_params = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "Você é um assistente especializado em análise de documentos. Sua tarefa é escolher o melhor candidato entre opções fornecidas. Retorne APENAS um número (1, 2, 3, etc.) sem texto adicional."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "timeout": self.timeout
                }
                
                # Configurar parâmetros por modelo
                if "gpt-4o" in self.model or "gpt-3.5" in self.model:
                    create_params["max_tokens"] = 10  # Apenas precisa retornar um número
                    create_params["temperature"] = 0.1  # Baixa temperatura para consistência
                else:
                    create_params["max_completion_tokens"] = 10
                
                response = self.client.chat.completions.create(**create_params)
                
                # Extrair resposta
                content = response.choices[0].message.content.strip()
                
                # Extrair número da resposta (pode ter texto extra, procurar primeiro número)
                numbers = re.findall(r'\d+', content)
                if numbers:
                    candidate_num = int(numbers[0])
                    # Converter para índice 0-based
                    candidate_index = candidate_num - 1
                    # Validar índice
                    if 0 <= candidate_index < num_candidates:
                        return candidate_index
                
                # Se não encontrou número válido, tentar novamente
                if attempt < self.max_retries - 1:
                    continue
                
                return None
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(0.5)
                    continue
                print(f"Erro ao chamar LLM para desempate: {e}")
                return None
        
        return None
    
    def validate_type(self, text: str, expected_type: str) -> bool:
        """Valida se um texto é do tipo esperado usando LLM.
        
        Pergunta ao LLM: "Isso te parece um {expected_type}? {text}"
        
        Args:
            text: Texto a validar
            expected_type: Tipo esperado (ex: "endereço", "telefone")
        
        Returns:
            True se LLM confirma que é do tipo esperado, False caso contrário
        """
        if not text or not text.strip():
            return False
        
        # Construir pergunta específica
        question = f"Isso te parece um {expected_type}? {text}"
        
        # Construir prompt para validação
        prompt = f"""Você precisa validar se o texto fornecido é um {expected_type} válido.

TEXTO A VALIDAR:
"{text}"

PERGUNTA:
{question}

INSTRUÇÕES:
1. Analise o texto cuidadosamente
2. Determine se o texto corresponde a um {expected_type} válido
3. Retorne APENAS "SIM" ou "NÃO" (sem aspas, sem texto adicional)
4. Se o texto não é um {expected_type} válido, retorne "NÃO"
5. Se o texto é claramente um {expected_type} válido, retorne "SIM"

RESPOSTA (SIM ou NÃO):"""
        
        # Chamar LLM
        for attempt in range(self.max_retries):
            try:
                # Preparar parâmetros da chamada
                create_params = {
                    "model": self.model,
                    "messages": [
                        {
                            "role": "system",
                            "content": f"Você é um assistente especializado em validação de dados. Sua tarefa é validar se um texto é um {expected_type} válido. Retorne APENAS 'SIM' ou 'NÃO' sem texto adicional."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    "timeout": self.timeout
                }
                
                # Configurar parâmetros por modelo
                if "gpt-4o" in self.model or "gpt-3.5" in self.model:
                    create_params["max_tokens"] = 5  # Apenas precisa retornar SIM ou NÃO
                    create_params["temperature"] = 0.1  # Baixa temperatura para consistência
                else:
                    create_params["max_completion_tokens"] = 5
                
                response = self.client.chat.completions.create(**create_params)
                
                # Extrair resposta
                content = response.choices[0].message.content.strip().upper()
                
                # Verificar se resposta é SIM
                if "SIM" in content:
                    return True
                elif "NÃO" in content or "NAO" in content:
                    return False
                
                # Se não encontrou resposta clara, tentar novamente
                if attempt < self.max_retries - 1:
                    continue
                
                # Fallback: retornar False se não conseguiu determinar
                return False
                
            except Exception as e:
                if attempt < self.max_retries - 1:
                    time.sleep(0.5)
                    continue
                if self.debug:
                    print(f"Erro ao validar tipo com LLM: {e}")
                return False
        
        return False
    
    def identify_name(
        self,
        candidates: List[str]
    ) -> Optional[int]:
        """Identifica qual candidato é um nome de pessoa usando LLM.
        
        Método rápido e simples: envia lista de candidatos e recebe o índice
        do que é um nome de pessoa.
        
        Args:
            candidates: Lista de strings candidatas (ex: ["JOANA D'ARC", "PR", "AVENIDA PAULISTA"])
            
        Returns:
            Índice (0-based) do candidato que é um nome, ou None se nenhum for nome
        """
        if not candidates:
            return None
        
        # Construir prompt simples e direto
        candidates_list = "\n".join([f"{i+1}. {candidate}" for i, candidate in enumerate(candidates)])
        
        prompt = f"""Qual desses candidatos é um nome de pessoa?

{candidates_list}

Responda APENAS com o número (1, 2, 3, etc.) do candidato que é um nome de pessoa.
Se nenhum for um nome, responda "NENHUM".

Resposta:"""
        
        # Chamar LLM com configurações otimizadas para velocidade
        try:
            create_params = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Você é um assistente especializado em identificar nomes de pessoas. Retorne APENAS um número (1, 2, 3, etc.) ou 'NENHUM'."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "timeout": 5  # Timeout curto
            }
            
            # Configurar max_tokens e temperature por modelo
            if "gpt-4o" in self.model or "gpt-3.5" in self.model:
                create_params["max_tokens"] = 5  # Apenas precisa retornar um número
                create_params["temperature"] = 0.1  # Baixa temperatura para consistência
            else:
                # Para modelos mais novos (gpt-5-mini), usar temperatura padrão (1.0) ou não especificar
                # O modelo gpt-5-mini não suporta temperature=0.0
                create_params["max_completion_tokens"] = 5
                # Não definir temperature para modelos novos - usar padrão
            
            response = self.client.chat.completions.create(**create_params)
            
            # Verificar se há conteúdo na resposta
            if not response.choices or not response.choices[0].message.content:
                if self.debug or get_debug_mode():
                    debug_print(f"    [GPT Name] Resposta vazia do modelo")
                return None
            
            content = response.choices[0].message.content.strip().upper()
            
            if self.debug or get_debug_mode():
                debug_print(f"    [GPT Name] Resposta: '{content}'")
            
            # Se resposta está vazia após strip, retornar None
            if not content:
                if self.debug or get_debug_mode():
                    debug_print(f"    [GPT Name] Resposta vazia após strip")
                return None
            
            # Verificar se é "NENHUM"
            if "NENHUM" in content or "NONE" in content:
                return None
            
            # Extrair número da resposta
            numbers = re.findall(r'\d+', content)
            if numbers:
                candidate_num = int(numbers[0])
                candidate_index = candidate_num - 1
                if 0 <= candidate_index < len(candidates):
                    if self.debug or get_debug_mode():
                        debug_print(f"    [GPT Name] Escolheu candidato {candidate_index + 1}: '{candidates[candidate_index][:50]}'")
                    return candidate_index
            
            # Se não encontrou número, tentar fallback: verificar se há texto que indique um número
            # Ex: "1", "candidato 1", "primeiro", etc.
            if self.debug or get_debug_mode():
                debug_print(f"    [GPT Name] Não encontrou número válido na resposta: '{content}'")
            
            return None
            
        except Exception as e:
            if self.debug or get_debug_mode():
                debug_print(f"    [GPT Name] Erro: {e}")
            return None
    
    def _quick_name_check(self, text: str) -> bool:
        """Verificação rápida se um texto é um nome (sem chamar LLM para um único candidato).
        
        Args:
            text: Texto a verificar
            
        Returns:
            True se parece ser um nome, False caso contrário
        """
        if not text or not text.strip():
            return False
        
        # Verificações básicas rápidas
        text_clean = text.strip()
        
        # Não pode ter números
        if any(c.isdigit() for c in text_clean):
            return False
        
        # Não pode ter símbolos estranhos (exceto espaços, apóstrofes, hífens)
        if re.search(r'[^\w\s\'-]', text_clean):
            return False
        
        # Deve ter pelo menos 3 caracteres
        if len(text_clean) < 3:
            return False
        
        # Não pode ser sigla comum (2 letras)
        if len(text_clean.split()) == 1 and len(text_clean) <= 2:
            return False
        
        return True
