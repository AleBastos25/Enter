/** Componente para mensagem do usuário. */

"use client";

import { useState } from "react";
import { MessageUser as MessageUserType } from "@/lib/types";

interface MessageUserProps {
  message: MessageUserType;
}

export function MessageUser({ message }: MessageUserProps) {
  const [copied, setCopied] = useState(false);
  
  // Se for apenas uma mensagem de schema (sem PDF)
  if (message.payload.isSchemaOnly && message.payload.schema) {
    const schemaText = typeof message.payload.schema === 'string' 
      ? message.payload.schema 
      : JSON.stringify(message.payload.schema, null, 2);
    
    const handleCopy = () => {
      navigator.clipboard.writeText(schemaText);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    };
    
    return (
      <div className="flex justify-end mb-4">
        <div className="bg-[#1a1a2a] border border-[#404040] rounded-lg p-4 max-w-2xl animate-fade-in">
          <div className="font-semibold mb-2 text-[#FF6B00]">📋 Schema JSON</div>
          <div className="relative">
            <pre className="bg-[#000000] border border-[#404040] p-3 rounded text-xs overflow-x-auto text-[#e5e5e5]">
              {schemaText}
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
  
  // Como é um PDF por vez, pegar o primeiro (e único) PDF
  const pdfFile = message.payload.pdfFiles[0];
  
  return (
    <div className="flex justify-end mb-4">
      <div className="bg-[#2a2a2a] border border-[#404040] rounded-lg p-4 max-w-2xl animate-fade-in">
        <div className="mb-2 text-sm">
          <span className="text-[#FF6B00] font-semibold">Label:</span>{" "}
          <span className="text-white">{message.payload.label}</span>
        </div>
        <div className="text-sm">
          <span className="text-[#FF6B00] font-semibold">PDF:</span>{" "}
          <span className="text-white">{pdfFile?.name || "N/A"}</span>
        </div>
      </div>
    </div>
  );
}
