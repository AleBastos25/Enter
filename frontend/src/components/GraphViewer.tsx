/** Componente para exibir HTML do grafo em um modal. */

"use client";

import { useEffect } from "react";

interface GraphViewerProps {
  isOpen: boolean;
  onClose: () => void;
  graphUrl: string;
}

export function GraphViewer({ isOpen, onClose, graphUrl }: GraphViewerProps) {
  useEffect(() => {
    // Prevenir scroll do body quando modal está aberto
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  if (!isOpen) return null;

  // Garantir que a URL seja absoluta
  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const absoluteUrl = graphUrl.startsWith("http") 
    ? graphUrl 
    : graphUrl.startsWith("/")
    ? `${API_BASE_URL}${graphUrl}`
    : `${API_BASE_URL}/graph/${graphUrl}`;

  console.log("[GraphViewer] URL do grafo:", absoluteUrl);
  console.log("[GraphViewer] URL original:", graphUrl);

  return (
    <div
      className="fixed inset-0 bg-black bg-opacity-80 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-[#000000] border border-[#404040] rounded-lg w-[95vw] h-[95vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-[#404040]">
          <h2 className="text-lg font-semibold text-white">Visualização do Grafo</h2>
          <button
            onClick={onClose}
            className="text-[#9ca3af] hover:text-white transition-colors"
            title="Fechar"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Iframe com o HTML do grafo - simples e direto */}
        <div className="flex-1 overflow-hidden">
          <iframe
            src={absoluteUrl}
            className="w-full h-full border-0"
            title="Visualização do Grafo"
            style={{ width: "100%", height: "100%" }}
          />
        </div>
      </div>
    </div>
  );
}

