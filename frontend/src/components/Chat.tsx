/** Componente principal do chat. */

"use client";

import { useEffect, useRef } from "react";
import { Page, Message } from "@/lib/types";
import { MessageUser } from "./MessageUser";
import { MessageSystem } from "./MessageSystem";

interface ChatProps {
  page: Page | null;
  devMode: boolean;
  onRetry?: (messageId: string) => void;
}

export function Chat({ page, devMode, onRetry }: ChatProps) {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [page?.messages]);

  // Debug removido para melhor performance

  if (!page) {
    return (
      <div className="flex-1 flex items-center justify-center text-[#9ca3af] bg-[#000000]">
        <div className="text-center">
          <div className="text-2xl font-semibold mb-2 text-white">PDF Extractor</div>
          <div className="text-sm">Selecione uma sessão ou crie uma nova extração</div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-6 bg-[#000000]">
      <div className="max-w-4xl mx-auto space-y-6">
        {page.messages.length === 0 ? (
          <div className="text-center text-[#9ca3af] py-8">
            Nenhuma mensagem ainda. Envie um documento para começar.
          </div>
        ) : (
          page.messages.map((message) => {
            if (message.role === "user") {
              return <MessageUser key={message.id} message={message} />;
            } else {
              return (
                <MessageSystem
                  key={message.id}
                  message={message}
                  devMode={devMode}
                  onRetry={onRetry ? () => onRetry(message.id) : undefined}
                />
              );
            }
          })
        )}
        <div ref={messagesEndRef} />
      </div>
    </div>
  );
}
