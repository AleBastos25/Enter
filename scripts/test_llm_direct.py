"""Teste direto do LLM durante extração."""

import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm.client import create_client

logging.basicConfig(level=logging.DEBUG)

# Criar cliente da mesma forma que durante a extração
from pathlib import Path
import yaml
llm_config_path = Path("configs/llm.yaml")
if llm_config_path.exists():
    with open(llm_config_path, "r", encoding="utf-8") as f:
        llm_config = yaml.safe_load(f) or {}
else:
    llm_config = {
        "enabled": True,
        "provider": "openai",
        "model": "gpt-5-mini",
        "temperature": 0.0
   }

provider = llm_config.get("provider", "none")
model = llm_config.get("model", "gpt-5-mini")
temperature = llm_config.get("temperature", 0.0)

client = create_client(provider, model, temperature)
print(f"Cliente criado: {type(client).__name__}")

prompt = """Separe este texto em tokens individuais onde cada ":" marca o fim de um label.

Texto: "Cidade: Mozarlândia U.F.: GO CEP: 76709970"

Exemplo:
"Cidade: Mozarlândia U.F.: GO CEP: 76709970" → ["Cidade:", "Mozarlândia", "U.F.:", "GO", "CEP:", "76709970"]

Resposta (apenas JSON, sem explicações):"""

print("\nChamando LLM diretamente...")
from openai import OpenAI
from src.llm.client import _load_api_key

api_key = _load_api_key()
openai_client = OpenAI(api_key=api_key)

create_params = {
    "model": "gpt-5-mini",
    "messages": [{"role": "user", "content": prompt}],
    "timeout": 20.0,
    "max_completion_tokens": 256,
}

response_obj = openai_client.chat.completions.create(**create_params)
print(f"\nResposta objeto: {type(response_obj)}")
print(f"Choices: {len(response_obj.choices) if response_obj.choices else 0}")
print(f"Response object dict keys: {list(response_obj.model_dump().keys()) if hasattr(response_obj, 'model_dump') else 'N/A'}")
if response_obj.choices:
    choice = response_obj.choices[0]
    print(f"Choice type: {type(choice)}")
    print(f"Choice finish_reason: {choice.finish_reason}")
    print(f"Message type: {type(choice.message)}")
    print(f"Message content: {repr(choice.message.content)}")
    print(f"Message content type: {type(choice.message.content)}")
    print(f"Message role: {choice.message.role}")
    if hasattr(choice.message, 'model_dump'):
        msg_dict = choice.message.model_dump()
        print(f"Message dict keys: {list(msg_dict.keys())}")
        print(f"Message dict: {msg_dict}")

print("\n\nUsando wrapper:")
response = client.generate(prompt, max_tokens=256, timeout=20.0)
print(f"\nResposta wrapper: {repr(response)}")
print(f"Tamanho: {len(response) if response else 0}")

