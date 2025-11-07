/** Componente para mensagem do usuário. */

"use client";

import { MessageUser as MessageUserType } from "@/lib/types";

interface MessageUserProps {
  message: MessageUserType;
}

export function MessageUser({ message }: MessageUserProps) {
  return (
    <div className="flex justify-end mb-4">
      <div className="bg-[#2a2a2a] border border-[#404040] rounded-lg p-4 max-w-2xl animate-fade-in">
        <div className="mb-2 text-sm">
          <span className="text-[#FF6B00] font-semibold">Label:</span>{" "}
          <span className="text-white">{message.payload.label}</span>
        </div>
        <div className="mb-2 text-sm">
          <span className="text-[#FF6B00] font-semibold">Schema:</span>{" "}
          <span className="text-white">{message.payload.schemaName}</span>
        </div>
        <div className="text-sm">
          <span className="text-[#FF6B00] font-semibold">PDFs:</span>
          <ul className="list-disc list-inside mt-1 text-white space-y-1">
            {message.payload.pdfFiles.map((file, idx) => (
              <li key={idx} className="text-[#e5e5e5]">
                {file.name} <span className="text-[#9ca3af]">({(file.size / 1024).toFixed(2)} KB)</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
