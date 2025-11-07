"""Utilitário para prints condicionais baseados em modo debug."""

import sys
from typing import Optional

# Variável global para controlar modo debug
_debug_mode: Optional[bool] = None


def set_debug_mode(enabled: bool) -> None:
    """Define o modo debug global.
    
    Args:
        enabled: Se True, ativa prints de debug
    """
    global _debug_mode
    _debug_mode = enabled


def get_debug_mode() -> bool:
    """Obtém o modo debug atual.
    
    Returns:
        True se debug está ativado, False caso contrário
    """
    global _debug_mode
    if _debug_mode is None:
        return False
    return _debug_mode


def debug_print(*args, **kwargs) -> None:
    """Print condicional baseado em modo debug.
    
    Args:
        *args: Argumentos para print
        **kwargs: Keyword arguments para print (flush será sempre True)
    """
    if get_debug_mode():
        # Sempre usar flush=True para prints de debug
        kwargs['flush'] = True
        print(*args, **kwargs)
        sys.stdout.flush()


def error_print(*args, **kwargs) -> None:
    """Print de erro (sempre executado, independente de debug).
    
    Args:
        *args: Argumentos para print
        **kwargs: Keyword arguments para print
    """
    kwargs.setdefault('file', sys.stderr)
    print(*args, **kwargs)
    sys.stderr.flush()

