"""Teste do LLM para separação de tokens."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.client import create_client

logging.basicConfig(level=logging.DEBUG)

client = create_client('openai', 'gpt-5-mini', 0.0)

prompt = """Analise o seguinte texto extraído de um PDF e separe-o em tokens corretos baseado nos dois pontos.

Texto: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"

Regras:
1. Cada token deve terminar com ":" se for um label
2. Tokens que são valores (números, códigos, nomes) não devem terminar com ":"
3. Mantenha a ordem original do texto
4. Retorne APENAS uma lista JSON com os tokens separados, sem explicações

Exemplo:
Texto: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"
Resposta: ["Cidade:", "Mozarlândia", "U.F.:", "GO", "CEP:", "76709970"]

Texto: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"
Resposta:"""

print("Chamando LLM...")
response = client.generate(prompt, max_tokens=256, timeout=20.0)
print(f"\nResposta completa ({len(response)} caracteres):")
print(repr(response))
print(f"\nResposta formatada:")
print(response)

