"""Utilitários para manipulação de arquivos."""

import tempfile
import shutil
from pathlib import Path
from typing import List, Tuple
from fastapi import UploadFile


async def save_uploaded_files(
    files: List[UploadFile],
    max_files: int = 10
) -> Tuple[List[Tuple[Path, str]], str]:
    """Salva arquivos enviados em diretório temporário.
    
    Args:
        files: Lista de arquivos enviados
        max_files: Número máximo de arquivos permitidos
        
    Returns:
        Tupla (lista de (caminho, filename), diretório temporário)
        
    Raises:
        ValueError: Se exceder max_files
    """
    if len(files) > max_files:
        raise ValueError(f"Máximo de {max_files} arquivos permitidos")
    
    # Criar diretório temporário
    temp_dir = Path(tempfile.mkdtemp(prefix="graph_extractor_"))
    
    saved_files = []
    for file in files:
        if file.filename:
            file_path = temp_dir / file.filename
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)
            saved_files.append((file_path, file.filename))
    
    return saved_files, str(temp_dir)


def cleanup_temp_dir(temp_dir: str) -> None:
    """Remove diretório temporário.
    
    Args:
        temp_dir: Caminho do diretório temporário
    """
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"Erro ao remover diretório temporário {temp_dir}: {e}")

