"""Gerenciador de sessão em memória."""

from typing import Dict, Any, List, Optional
import uuid


class SessionManager:
    """Gerencia sessões em memória (perde dados ao reiniciar servidor)."""
    
    def __init__(self):
        """Inicializa o gerenciador de sessões."""
        self._sessions: Dict[str, Dict[str, Any]] = {}
    
    def get_or_create_session(self, session_id: Optional[str] = None) -> str:
        """Obtém ou cria uma sessão.
        
        Args:
            session_id: ID da sessão (opcional, gera novo se None)
            
        Returns:
            ID da sessão
        """
        if session_id is None or session_id not in self._sessions:
            session_id = str(uuid.uuid4())
            self._sessions[session_id] = {
                "pages": [],
                "folders": {}
            }
        return session_id
    
    def get_session(self, session_id: str) -> Dict[str, Any]:
        """Obtém dados da sessão.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Dicionário com dados da sessão
        """
        return self._sessions.get(session_id, {"pages": [], "folders": {}})
    
    def save_session(self, session_id: str, data: Dict[str, Any]) -> None:
        """Salva dados da sessão.
        
        Args:
            session_id: ID da sessão
            data: Dados para salvar
        """
        self._sessions[session_id] = data
    
    def add_page(self, session_id: str, page: Dict[str, Any]) -> None:
        """Adiciona uma página à sessão.
        
        Args:
            session_id: ID da sessão
            page: Dados da página
        """
        session = self.get_session(session_id)
        session["pages"].append(page)
        self.save_session(session_id, session)
    
    def get_pages(self, session_id: str) -> List[Dict[str, Any]]:
        """Obtém todas as páginas da sessão.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Lista de páginas
        """
        session = self.get_session(session_id)
        return session.get("pages", [])
    
    def get_folders(self, session_id: str) -> Dict[str, List[str]]:
        """Obtém pastas organizadas por label.
        
        Args:
            session_id: ID da sessão
            
        Returns:
            Dicionário {label: [page_ids]}
        """
        session = self.get_session(session_id)
        return session.get("folders", {})


# Instância singleton
session_manager = SessionManager()

