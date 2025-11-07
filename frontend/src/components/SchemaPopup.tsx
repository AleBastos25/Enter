/** Popup para escrever schema JSON manualmente. */

"use client";

import { useState } from "react";

interface SchemaPopupProps {
  isOpen: boolean;
  onClose: () => void;
  onUse: (schema: Record<string, string>) => void;
}

export function SchemaPopup({ isOpen, onClose, onUse }: SchemaPopupProps) {
  const [jsonText, setJsonText] = useState("");
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleUse = () => {
    try {
      const parsed = JSON.parse(jsonText);
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Schema deve ser um objeto JSON");
      }
      // Validar que todos os valores são strings
      const schema: Record<string, string> = {};
      for (const [key, value] of Object.entries(parsed)) {
        if (typeof value !== "string") {
          throw new Error(`Valor de "${key}" deve ser uma string`);
        }
        schema[key] = value;
      }
      setError(null);
      onUse(schema);
      setJsonText("");
      onClose();
    } catch (err: any) {
      setError(err.message || "JSON inválido");
    }
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
      <div className="bg-[#171717] border border-[#404040] rounded-lg p-6 w-full max-w-2xl max-h-[80vh] flex flex-col">
        <h2 className="text-xl font-bold mb-4 text-white">Escrever Schema JSON</h2>
        <textarea
          value={jsonText}
          onChange={(e) => {
            setJsonText(e.target.value);
            setError(null);
          }}
          className="flex-1 w-full p-3 bg-[#000000] border border-[#404040] rounded-md font-mono text-sm resize-none text-[#e5e5e5] focus:outline-none focus:border-[#FF6B00]"
          placeholder='{"campo1": "Descrição do campo 1", "campo2": "Descrição do campo 2"}'
        />
        {error && (
          <p className="mt-2 text-sm text-[#ff4444]">{error}</p>
        )}
        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#404040] text-white rounded-lg transition-colors"
          >
            Cancelar
          </button>
          <button
            onClick={handleUse}
            className="px-4 py-2 bg-[#FF6B00] hover:bg-[#FF7A00] text-white rounded-lg transition-colors"
          >
            Usar
          </button>
        </div>
      </div>
    </div>
  );
}
