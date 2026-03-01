"""Modelos Pydantic para a API."""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


class RunResult(BaseModel):
    """Resultado de uma execução de extração."""
    run_id: str
    filename: str
    status: str  # "ok" | "error" | "processing"
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    dev: Optional[Dict[str, Any]] = None
    
    class Config:
        """Configuração do modelo."""
        # Permitir tipos complexos (já que result pode ter qualquer estrutura)
        json_encoders = {
            # Não há necessidade de encoders especiais - Pydantic cuida disso
        }


class ExtractionRequest(BaseModel):
    """Request de extração (para validação)."""
    label: str
    schema_data: Dict[str, str] = Field(..., alias="schema")
    dev_mode: bool = False
    
    class Config:
        """Configuração do modelo."""
        populate_by_name = True  # Permite usar tanto 'schema' quanto 'schema_data'


class ExtractionResponse(BaseModel):
    """Resposta de extração."""
    runs: List[RunResult]

