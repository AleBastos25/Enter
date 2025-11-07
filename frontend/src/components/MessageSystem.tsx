/** Componente para mensagem do sistema (resultado da extração). */

"use client";

import { useState } from "react";
import { MessageSystem as MessageSystemType, ExtractionStep } from "@/lib/types";
import { apiClient } from "@/lib/api";

interface MessageSystemProps {
  message: MessageSystemType;
  devMode: boolean;
  onRetry?: () => void;
}

const stepLabels: Record<ExtractionStep, string> = {
  received: "Recebido",
  building_graph: "Construindo grafo",
  regex_matching: "Regras & Regex",
  embedding_matching: "Embeddings & ranking",
  tiebreaking: "Desempate/Arbitragem",
  post_processing: "Pós-processamento",
  done: "JSON gerado",
};

export function MessageSystem({ message, devMode, onRetry }: MessageSystemProps) {
  const [copied, setCopied] = useState(false);
  const run = message.run;

  const handleCopy = () => {
    if (run.result) {
      navigator.clipboard.writeText(JSON.stringify(run.result, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleDownload = () => {
    if (run.result) {
      const blob = new Blob([JSON.stringify(run.result, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${run.run_id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  };

  if (run.status === "processing") {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-[#171717] border border-[#404040] rounded-lg p-4 max-w-2xl animate-fade-in">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-5 w-5 border-2 border-[#FF6B00] border-t-transparent"></div>
            <div className="text-[#e5e5e5]">{run.filename}</div>
          </div>
        </div>
      </div>
    );
  }

  if (run.status === "error") {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-[#2a1f1f] border border-[#ff4444] rounded-lg p-4 max-w-2xl animate-fade-in">
          <div className="font-semibold mb-2 text-white">Erro ao processar {run.filename}</div>
          <div className="mb-2 text-[#ff8888]">{run.error_message}</div>
          {devMode && run.dev && (
            <div className="mt-2 text-sm text-[#9ca3af]">
              <div>Tempo: {run.dev.elapsed_ms} ms</div>
              {run.dev.rules_used && run.dev.rules_used.length > 0 && (
                <div>Regras: {run.dev.rules_used.join(", ")}</div>
              )}
            </div>
          )}
          {onRetry && (
            <button
              onClick={onRetry}
              className="mt-2 px-3 py-1 bg-[#ff4444] hover:bg-[#ff6666] text-white rounded text-sm transition-colors"
            >
              Tentar Novamente
            </button>
          )}
        </div>
      </div>
    );
  }

  // Se for mensagem de schema, mostrar de forma especial
  if (run.filename === "Schema JSON" && run.result) {
    return (
      <div className="flex justify-start mb-4">
        <div className="bg-[#1a1a2a] border border-[#404040] rounded-lg p-4 max-w-2xl w-full animate-fade-in">
          <div className="font-semibold mb-2 text-[#FF6B00]">📋 Schema JSON</div>
          <div className="relative">
            <pre className="bg-[#000000] border border-[#404040] p-3 rounded text-xs overflow-x-auto text-[#e5e5e5]">
              {JSON.stringify(run.result, null, 2)}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-2 right-2 px-2 py-1 bg-[#2a2a2a] hover:bg-[#404040] text-white rounded text-xs transition-colors"
            >
              {copied ? "Copiado!" : "Copiar"}
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-4">
      <div className="bg-[#171717] border border-[#404040] rounded-lg p-4 max-w-2xl w-full animate-fade-in">
        <div className="font-semibold mb-2 text-white">{run.filename}</div>

        {devMode && run.dev && (
          <div className="mb-3 text-sm text-[#9ca3af] space-y-1">
            <div>Tempo: <span className="text-[#FF6B00]">{run.dev.elapsed_ms} ms</span></div>
            {run.dev.rules_used && run.dev.rules_used.length > 0 && (
              <div>Regras: <span className="text-[#e5e5e5]">{run.dev.rules_used.join(", ")}</span></div>
            )}
            {run.dev.graph_url && (
              <div>
                <a
                  href={apiClient.getGraphUrl(run.run_id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#FF6B00] hover:text-[#FF7A00] underline"
                >
                  Abrir Grafo →
                </a>
              </div>
            )}
          </div>
        )}

        {run.result && (
          <>
            <div className="relative">
              <pre className="bg-[#000000] border border-[#404040] p-3 rounded text-xs mb-3 overflow-x-auto text-[#e5e5e5]">
                {JSON.stringify(run.result, null, 2)}
              </pre>
              <button
                onClick={handleCopy}
                className="absolute top-2 right-2 px-2 py-1 bg-[#2a2a2a] hover:bg-[#404040] text-white rounded text-xs transition-colors"
              >
                {copied ? "Copiado!" : "Copiar"}
              </button>
            </div>
            <div className="flex gap-2">
              <button
                onClick={handleCopy}
                className="px-3 py-1.5 bg-[#2a2a2a] hover:bg-[#404040] text-white rounded text-sm transition-colors"
              >
                {copied ? "✓ Copiado" : "Copiar"}
              </button>
              <button
                onClick={handleDownload}
                className="px-3 py-1.5 bg-[#FF6B00] hover:bg-[#FF7A00] text-white rounded text-sm transition-colors"
              >
                Baixar JSON
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
