/** Página principal da aplicação. */

"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Chat } from "@/components/Chat";
import { InputBar } from "@/components/InputBar";
import { Sidebar } from "@/components/Sidebar";
import { DevModeToggle } from "@/components/DevModeToggle";
import { useExtraction } from "@/hooks/useExtraction";
import { useSessionStorage } from "@/hooks/useSessionStorage";
import { Page, MessageUser, MessageSystem, RunResult } from "@/lib/types";
import { storage } from "@/lib/storage";

export default function Home() {
  const [currentPageId, setCurrentPageId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"pages" | "folders">("pages");
  const [searchQuery, setSearchQuery] = useState("");
  const [devMode, setDevMode] = useState(false);
  const [updateTrigger, setUpdateTrigger] = useState(0);

  const { pages, folders, addPage, updatePage, deletePage, isLoaded } =
    useSessionStorage();
  const { state, extract, error: extractionError, currentStep, progress } = useExtraction();
  
  // Forçar atualização de páginas quando houver mudanças no storage
  useEffect(() => {
    if (isLoaded && typeof window !== "undefined") {
      const storagePages = storage.loadPages();
      // Sincronizar se houver diferença
      if (storagePages.length !== pages.length) {
        // Atualizar do storage se necessário
        const currentPages = storage.loadPages();
        if (currentPages.length > 0 && currentPageId) {
          const currentPageFromStorage = currentPages.find((p) => p.id === currentPageId);
          if (currentPageFromStorage) {
            // Forçar re-render se a página atual foi atualizada
            setCurrentPageId((prev) => prev);
          }
        }
      }
    }
  }, [pages.length, currentPageId, isLoaded]);

  // Carregar dev mode do localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      setDevMode(storage.loadDevMode());
    }
  }, []);

  // Buscar página atual (com fallback para storage se não estiver no estado)
  const currentPage = useMemo(() => {
    if (!currentPageId) return null;
    const page = pages.find((p) => p.id === currentPageId);
    if (page) return page;
    // Fallback: buscar do storage
    if (typeof window !== "undefined") {
      const storagePages = storage.loadPages();
      return storagePages.find((p) => p.id === currentPageId) || null;
    }
    return null;
  }, [pages, currentPageId]);

  // Labels recentes para autocomplete
  const recentLabels = useMemo(() => {
    const labels = new Set<string>();
    pages.forEach((page) => {
      page.messages.forEach((msg) => {
        if (msg.role === "user") {
          labels.add(msg.payload.label);
        }
      });
    });
    return Array.from(labels);
  }, [pages]);

  const handleSend = useCallback(
    async (
      label: string,
      schema: Record<string, string>,
      pdfFiles: File[]
    ) => {
      console.log("[Page] handleSend chamado");
      console.log("[Page] Label:", label);
      console.log("[Page] Schema:", schema);
      console.log("[Page] PDFs:", pdfFiles.map(f => f.name));
      
      // Declarar pageId e processingMessageId fora do try para usar no catch
      let pageId: string | null = currentPageId;
      let processingMessageId: string | undefined;
      
      try {
        // Criar nova página se não houver uma selecionada
        let page: Page | undefined;
        
        if (!pageId) {
          const newPage: Page = {
            id: `page_${Date.now()}`,
            title: `Nova Extração ${new Date().toLocaleString("pt-BR", { 
              day: "2-digit", 
              month: "2-digit", 
              hour: "2-digit", 
              minute: "2-digit" 
            })}`,
            createdAt: Date.now(),
            messages: [],
          };
          // Adicionar página e selecionar
          addPage(newPage);
          pageId = newPage.id;
          page = newPage;
          setCurrentPageId(pageId);
        } else {
          // Buscar página existente (primeiro do estado, depois do storage)
          page = pages.find((p) => p.id === pageId);
          if (!page && typeof window !== "undefined") {
            const storagePages = storage.loadPages();
            page = storagePages.find((p) => p.id === pageId);
          }
        }
        
        if (!page) {
          console.error("Página não encontrada");
          alert("Erro: página não encontrada. Tente novamente.");
          return;
        }
        
        // Garantir que a página está selecionada
        if (currentPageId !== pageId) {
          setCurrentPageId(pageId);
        }

        // Criar mensagem do usuário
        const userMessage: MessageUser = {
          id: `msg_user_${Date.now()}`,
          role: "user",
          createdAt: Date.now(),
          payload: {
            label,
            schemaName: "Manual", // TODO: passar nome do arquivo
            pdfFiles: pdfFiles.map((f) => ({ name: f.name, size: f.size })),
          },
        };

        // Mensagem de processamento temporária
        processingMessageId = `msg_processing_${Date.now()}`;
        const processingMessage: MessageSystem = {
          id: processingMessageId,
          role: "system",
          createdAt: Date.now(),
          run: {
            run_id: `processing_${Date.now()}`,
            filename: `Processando ${pdfFiles.length} PDF(s)...`,
            status: "processing",
            result: undefined,
            error_message: undefined,
            dev: undefined,
          },
        };

        // Adicionar mensagem do usuário e mensagem de processamento IMEDIATAMENTE
        // Usar função que garante atualização síncrona
        const updatedMessages = [...page.messages, userMessage, processingMessage];
        
        console.log("Adicionando mensagens:", {
          pageId,
          userMessage,
          processingMessage,
          totalMessages: updatedMessages.length
        });
        
        updatePage(pageId, {
          messages: updatedMessages,
        });
        
        // Garantir que a página está selecionada
        setCurrentPageId(pageId);
        
        // Forçar atualização imediata (sem delay)
        setUpdateTrigger((prev) => prev + 1);

        // Executar extração
        console.log("[Page] ANTES de chamar extract()");
        console.log("[Page]   - label:", label);
        console.log("[Page]   - schema:", schema);
        console.log("[Page]   - pdfFiles:", pdfFiles.map(f => f.name));
        console.log("[Page]   - devMode:", devMode);
        
        let runs: RunResult[] = [];
        try {
          console.log("[Page] Chamando extract() agora...");
          runs = await extract(label, schema, pdfFiles, devMode);
          console.log("[Page] extract() retornou:", runs);
        } catch (extractError) {
          console.error("[Page] ERRO em extract():", extractError);
          throw extractError;
        }

        // Buscar página atualizada do estado (não do storage, que pode estar desatualizado)
        const updatedPages = storage.loadPages();
        const finalPage = updatedPages.find((p) => p.id === pageId);
        
        if (!finalPage) {
          console.error("Página não encontrada após extração");
          return;
        }

        // Remover mensagem de processamento e adicionar resultados
        const messagesWithoutProcessing = finalPage.messages.filter(
          (msg) => msg.id !== processingMessageId && !msg.id?.startsWith("msg_processing_")
        );

        // Criar mensagens do sistema para cada run
        const systemMessages: MessageSystem[] = runs.map((run) => ({
          id: `msg_system_${run.run_id}`,
          role: "system",
          createdAt: Date.now(),
          run,
        }));

        // Atualizar página com mensagens do sistema (sem a de processamento)
        updatePage(pageId, {
          messages: [...messagesWithoutProcessing, ...systemMessages],
        });
        
        // Forçar atualização
        setUpdateTrigger((prev) => prev + 1);
      } catch (err: any) {
        console.error("Erro ao extrair:", err);
        
        // Adicionar mensagem de erro
        // Usar pageId do escopo externo (definido no início do try)
        const errorPages = storage.loadPages();
        const errorPage = errorPages.find((p) => p.id === pageId);
        
        if (errorPage) {
          // Remover mensagem de processamento
          const messagesWithoutProcessing = errorPage.messages.filter(
            (msg) => msg.id !== processingMessageId && !msg.id?.startsWith("msg_processing_")
          );
          
          const errorMessage: MessageSystem = {
            id: `msg_error_${Date.now()}`,
            role: "system",
            createdAt: Date.now(),
            run: {
              run_id: `error_${Date.now()}`,
              filename: "Erro",
              status: "error",
              result: undefined,
              error_message: err.response?.data?.detail || err.message || "Erro desconhecido",
              dev: undefined,
            },
          };
          
          updatePage(pageId, {
            messages: [...messagesWithoutProcessing, errorMessage],
          });
          
          // Forçar atualização
          setUpdateTrigger((prev) => prev + 1);
        } else {
          // Se não encontrou página, mostrar erro genérico
          alert(`Erro: ${err.response?.data?.detail || err.message || "Erro desconhecido"}`);
        }
      }
    },
    [currentPageId, pages, addPage, updatePage, extract, devMode]
  );

  const handleSelectPage = useCallback((pageId: string) => {
    if (!pageId || pageId === "") {
      setCurrentPageId(null);
      return;
    }
    
    // Verificar se a página existe, se não, criar
    const existingPage = pages.find((p) => p.id === pageId);
    if (!existingPage && typeof window !== "undefined") {
      const storagePages = storage.loadPages();
      const storagePage = storagePages.find((p) => p.id === pageId);
      if (!storagePage) {
        // Criar nova página
        const newPage: Page = {
          id: pageId,
          title: `Nova Extração ${new Date().toLocaleString("pt-BR", { 
            day: "2-digit", 
            month: "2-digit", 
            hour: "2-digit", 
            minute: "2-digit" 
          })}`,
          createdAt: Date.now(),
          messages: [],
        };
        addPage(newPage);
      }
    }
    
    setCurrentPageId(pageId);
  }, [pages, addPage]);

  const handleDeletePage = useCallback(
    (pageId: string) => {
      deletePage(pageId);
      if (currentPageId === pageId) {
        setCurrentPageId(null);
      }
    },
    [currentPageId, deletePage]
  );

  const handleUpdatePageTitle = useCallback(
    (pageId: string, title: string) => {
      updatePage(pageId, { title });
    },
    [updatePage]
  );

  if (!isLoaded) {
    return (
      <div className="h-screen flex items-center justify-center bg-[#000000] text-white">
        <div className="text-lg">Carregando...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex bg-[#000000] text-white overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        pages={pages}
        folders={folders}
        currentPageId={currentPageId || undefined}
        onSelectPage={handleSelectPage}
        onDeletePage={handleDeletePage}
        onUpdatePageTitle={handleUpdatePageTitle}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col bg-[#000000]">
        {/* Top Bar (simples, minimalista) */}
        {currentPage && (
          <div className="border-b border-[#404040] px-4 py-2 flex items-center justify-between bg-[#000000]">
            <div className="flex items-center gap-2">
              <span className="text-sm text-[#e5e5e5]">Graph Extractor</span>
            </div>
            <DevModeToggle value={devMode} onChange={setDevMode} />
          </div>
        )}

        {/* Chat Area */}
        <div className="flex-1 overflow-hidden">
          <Chat
            page={currentPage}
            devMode={devMode}
            onRetry={(messageId) => {
              // TODO: implementar retry
              console.log("Retry message:", messageId);
            }}
          />
        </div>

        {/* Input Bar */}
        <InputBar
          onSend={handleSend}
          recentLabels={recentLabels}
          disabled={state === "processing" || state === "uploading"}
          processingState={state}
          currentStep={currentStep}
          progress={progress}
        />
      </div>
    </div>
  );
}
