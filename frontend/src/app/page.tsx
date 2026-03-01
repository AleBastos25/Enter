/** Sessão principal da aplicação. */

"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { Chat } from "@/components/Chat";
import { InputBar } from "@/components/InputBar";
import { Sidebar } from "@/components/Sidebar";
import { DevModeToggle } from "@/components/DevModeToggle";
import { LearningToggle } from "@/components/LearningToggle";
import { useExtraction } from "@/hooks/useExtraction";
import { useSessionStorage } from "@/hooks/useSessionStorage";
import { Page, MessageUser, MessageSystem, RunResult } from "@/lib/types";
import { storage } from "@/lib/storage";

export default function Home() {
  const [currentPageId, setCurrentPageId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"pages" | "folders">("pages");
  const [searchQuery, setSearchQuery] = useState("");
  const [devMode, setDevMode] = useState(false);
  const [useLearning, setUseLearning] = useState(true);
  const [updateTrigger, setUpdateTrigger] = useState(0);
  const [lastSchema, setLastSchema] = useState<Record<string, string> | null>(null);
  const [isProcessing, setIsProcessing] = useState(false); // Trava para evitar múltiplas chamadas simultâneas

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

  // Carregar dev mode e use learning do localStorage
  useEffect(() => {
    if (typeof window !== "undefined") {
      setDevMode(storage.loadDevMode());
      const savedUseLearning = storage.loadUseLearning();
      if (savedUseLearning !== null) {
        setUseLearning(savedUseLearning);
      }
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
      pdfFiles: File[],
      schemaJsonString?: string // Texto JSON original do schema
    ) => {
      // Trava: evitar múltiplas chamadas simultâneas
      if (isProcessing) {
        console.warn("[Page] handleSend já está processando, ignorando chamada duplicada");
        return;
      }
      
      setIsProcessing(true);
      
      // IMPORTANTE: Declarar finalPageId no escopo externo para ser acessível no catch
      let finalPageId: string | null = null;
      
      try {
        console.log("[Page] handleSend chamado");
        console.log("[Page] Label:", label);
        console.log("[Page] Schema:", schema);
        console.log("[Page] PDFs:", pdfFiles.map(f => f.name));
        console.log("[Page] lastSchema atual:", lastSchema);
        
        // IMPORTANTE: Capturar currentPageId UMA VEZ no início e não mudar
        // Se não há sessão, criar uma nova e usar para TODOS os PDFs
        // SEMPRE verificar o storage primeiro para pegar a sessão mais recente
        const storagePages = storage.loadPages();
        const now = Date.now();
        
        // Prioridade 1: Usar currentPageId se existir e a página ainda existir
        let pageId: string | null = currentPageId;
        if (pageId) {
          const pageExists = storagePages.find(p => p.id === pageId);
          if (!pageExists) {
            // Página foi deletada, resetar
            const deletedPageId = pageId;
            pageId = null;
            console.log(`[Page] Sessão ${deletedPageId} não existe mais, criando nova`);
          } else {
            console.log(`[Page] Usando sessão existente: ${pageId}`);
          }
        }
        
        // Prioridade 2: Se não há sessão atual, verificar se uma foi criada recentemente
        // (evita criar múltiplas sessões quando múltiplos PDFs são enviados simultaneamente)
        if (!pageId) {
          // Verificar se outra chamada já criou uma página enquanto esperávamos
          // Usar uma janela de tempo maior (10 segundos) para capturar sessões criadas em sequência
          const recentPages = storagePages
            .filter(p => p.createdAt > now - 10000) // Últimos 10 segundos
            .sort((a, b) => b.createdAt - a.createdAt); // Mais recente primeiro
          
          if (recentPages.length > 0) {
            // Usar página mais recente ao invés de criar nova
            pageId = recentPages[0].id;
            setCurrentPageId(pageId);
            console.log(`[Page] Reutilizando sessão recente: ${pageId} (criada há ${Math.round((now - recentPages[0].createdAt) / 1000)}s)`);
          } else {
            // Criar nova página com timestamp único para evitar colisões
            const timestamp = Date.now();
            const newPage: Page = {
              id: `page_${timestamp}`,
              title: `New Session ${new Date().toLocaleString("en-US", { 
                day: "2-digit", 
                month: "2-digit", 
                hour: "2-digit", 
                minute: "2-digit" 
              })}`,
              createdAt: timestamp,
              messages: [],
            };
            // Verificar novamente se não foi criada entre a verificação e agora
            // (double-check para evitar race conditions)
            const pagesAfterCheck = storage.loadPages();
            const veryRecentPages = pagesAfterCheck
              .filter(p => p.createdAt > now - 2000) // Últimos 2 segundos
              .sort((a, b) => b.createdAt - a.createdAt);
            
            if (veryRecentPages.length > 0) {
              // Alguém criou uma sessão enquanto verificávamos, usar ela
              pageId = veryRecentPages[0].id;
              setCurrentPageId(pageId);
              console.log(`[Page] Reutilizando sessão criada durante verificação: ${pageId}`);
            } else {
              // Criar nova página
              addPage(newPage);
              pageId = newPage.id;
              setCurrentPageId(pageId);
              setLastSchema(null);
              console.log(`[Page] Nova sessão criada: ${pageId}`);
            }
          }
        }
        
        // Garantir que pageId não seja null daqui em diante
        if (!pageId) {
          console.error("[Page] ERRO: pageId é null após tentar criar/obter sessão");
          setIsProcessing(false);
          return;
        }
        
        // IMPORTANTE: Usar uma constante finalPageId que NÃO muda durante todo o processamento
        // Isso garante que todos os PDFs vão para a mesma sessão
        finalPageId = pageId;
        
        // Buscar página existente (primeiro do estado, depois do storage)
        let page: Page | undefined = pages.find((p) => p.id === finalPageId);
        if (!page && typeof window !== "undefined") {
          const storagePages = storage.loadPages();
          page = storagePages.find((p) => p.id === finalPageId);
        }
        
        // Se a página não foi encontrada, criar uma nova com o mesmo ID
        // IMPORTANTE: Verificar novamente antes de criar para evitar duplicatas
        if (!page) {
          // Verificar uma última vez se a página não foi criada entre a verificação anterior e agora
          const finalCheckPages = storage.loadPages();
          const finalCheckPage = finalCheckPages.find((p) => p.id === finalPageId);
          
          if (finalCheckPage) {
            // Página foi criada entre as verificações, usar ela
            page = finalCheckPage;
            console.log(`[Page] Página ${finalPageId} encontrada na verificação final`);
          } else {
            console.warn(`[Page] Página ${finalPageId} não encontrada, criando nova com mesmo ID...`);
            const newPage: Page = {
              id: finalPageId,
              title: `New Session ${new Date().toLocaleString("en-US", { 
                day: "2-digit", 
                month: "2-digit", 
                hour: "2-digit", 
                minute: "2-digit" 
              })}`,
              createdAt: Date.now(),
              messages: [],
            };
            // addPage já verifica duplicatas, então é seguro chamar
            addPage(newPage);
            page = newPage;
          }
        }
        
        // Garantir que a página está selecionada
        if (currentPageId !== finalPageId) {
          setCurrentPageId(finalPageId);
        }

        // Verificar se o schema mudou comparando com o último schema enviado no chat
        // SEMPRE verificar nas mensagens do chat (fonte de verdade) para evitar duplicações
        const currentPagesForSchema = storage.loadPages();
        const currentPageForSchema = currentPagesForSchema.find((p) => p.id === finalPageId) || page;
        const schemaMessages = currentPageForSchema.messages
          .filter((msg): msg is MessageUser => msg.role === "user" && msg.payload.isSchemaOnly === true)
          .sort((a, b) => b.createdAt - a.createdAt); // Ordenar do mais recente para o mais antigo
        
        const lastSchemaMessage = schemaMessages[0]; // Pegar o mais recente
        
        // Comparar com o último schema enviado no chat
        // Esta variável será usada para decidir se mostra mensagem de schema no chat
        let schemaChanged = false;
        
        // Verificar se há uma mensagem de schema muito recente (últimos 2 segundos) - pode ser duplicação
        // Usar a variável 'now' já declarada anteriormente
        const veryRecentSchemaMessage = schemaMessages.find(msg => (now - msg.createdAt) < 2000);
        if (veryRecentSchemaMessage) {
          console.log("[Page] Mensagem de schema muito recente encontrada (possível duplicação), ignorando verificação");
          // Não adicionar schema se já foi adicionado muito recentemente
          schemaChanged = false;
        }
        
        // Normalizar JSON para comparação (remove diferenças de formatação)
        const normalizeJson = (json: string) => {
          try {
            const parsed = JSON.parse(json);
            return JSON.stringify(parsed, Object.keys(parsed).sort()); // Ordenar chaves para comparação consistente
          } catch {
            return json.trim();
          }
        };
        
        const newSchemaText = schemaJsonString || JSON.stringify(schema, null, 2);
        const normalizedNewSchema = normalizeJson(newSchemaText);
        
        // Se não há mensagem muito recente, fazer a comparação normal
        if (!veryRecentSchemaMessage) {
          if (!lastSchemaMessage || !lastSchemaMessage.payload.schema) {
            // Se não há schema anterior no chat, considerar como mudança
            schemaChanged = true;
            console.log("[Page] Nenhum schema anterior encontrado no chat, considerando como mudança");
          } else {
            // Comparar com o schema das mensagens (fonte de verdade)
            const lastSchemaText = typeof lastSchemaMessage.payload.schema === 'string'
              ? lastSchemaMessage.payload.schema
              : JSON.stringify(lastSchemaMessage.payload.schema, null, 2);
            const normalizedLastSchema = normalizeJson(lastSchemaText);
            schemaChanged = normalizedLastSchema !== normalizedNewSchema;
            
            console.log("[Page] Comparando schemas:");
            console.log("[Page]   Último schema (normalizado):", normalizedLastSchema.substring(0, 100) + "...");
            console.log("[Page]   Novo schema (normalizado):", normalizedNewSchema.substring(0, 100) + "...");
            console.log("[Page]   Schemas são diferentes?", schemaChanged);
          }
        }
        
        // Só adicionar mensagem de schema UMA VEZ se houver mudança (antes de processar todos os PDFs)
        if (schemaChanged) {
          console.log("[Page] Schema mudou, adicionando mensagem de schema UMA VEZ antes de processar", pdfFiles.length, "PDF(s)");
          
          // Adicionar mensagem de usuário mostrando o schema (à direita)
          // Usar o texto JSON original se fornecido, senão converter o schema
          const schemaText = schemaJsonString || JSON.stringify(schema, null, 2);
          const schemaMessage: MessageUser = {
            id: `msg_schema_${Date.now()}`,
            role: "user",
            createdAt: Date.now(),
            payload: {
              label: "",
              schemaName: "Schema JSON",
              pdfFiles: [],
              schema: schemaText, // Salvar como string JSON original
              isSchemaOnly: true,
            },
          };
          
          // Buscar página atualizada antes de adicionar mensagem
          const updatedPagesForSchema = storage.loadPages();
          const updatedPageForSchema = updatedPagesForSchema.find((p) => p.id === finalPageId) || currentPageForSchema;
          
          updatePage(finalPageId, {
            messages: [...updatedPageForSchema.messages, schemaMessage],
          });
          setUpdateTrigger((prev) => prev + 1);
          
          // Atualizar último schema no estado (para referência futura)
          setLastSchema(schema);
          
          // Aguardar um pouco para a mensagem aparecer antes de processar os PDFs
          await new Promise(resolve => setTimeout(resolve, 200));
        } else {
          console.log("[Page] Schema não mudou, não adicionando mensagem de schema");
        }

        // Processar PDFs sequencialmente (ping-pong: um PDF → resposta → próximo PDF → resposta)
        // Manter no mesmo chat (mesmo pageId) e processar um por vez
        for (let i = 0; i < pdfFiles.length; i++) {
          const pdfFile = pdfFiles[i];
          const isLast = i === pdfFiles.length - 1;
          
          // Criar mensagem do usuário para este PDF específico
          const userMessage: MessageUser = {
            id: `msg_user_${Date.now()}_${i}`,
            role: "user",
            createdAt: Date.now(),
            payload: {
              label,
              schemaName: "Manual", // TODO: passar nome do arquivo
              pdfFiles: [{ name: pdfFile.name, size: pdfFile.size }],
            },
          };

          // Mensagem de processamento temporária
          const processingMessageId = `msg_processing_${Date.now()}_${i}`;
          const processingMessage: MessageSystem = {
            id: processingMessageId,
            role: "system",
            createdAt: Date.now(),
            run: {
              run_id: `processing_${Date.now()}_${i}`,
              filename: `Processing ${pdfFile.name}...`,
              status: "processing",
              result: undefined,
              error_message: undefined,
              dev: undefined,
            },
          };

          // Buscar página atualizada antes de adicionar mensagens
          // SEMPRE usar finalPageId (constante) para garantir que todos os PDFs vão para a mesma sessão
          const currentPages = storage.loadPages();
          let currentPage = currentPages.find((p) => p.id === finalPageId);
          
          // Se não encontrou a página, usar a página inicial
          if (!currentPage) {
            console.warn(`[Page] Página ${finalPageId} não encontrada no storage, usando página inicial`);
            currentPage = page;
          }
          
          // Garantir que estamos usando a mesma sessão (não permitir mudança)
          if (currentPage && currentPage.id !== finalPageId) {
            console.error(`[Page] ERRO: Sessão mudou durante processamento. Esperado: ${finalPageId}, encontrado: ${currentPage.id}`);
            // Forçar uso do finalPageId correto
            currentPage = { ...currentPage, id: finalPageId };
          }
          
          // Garantir que a página está selecionada
          if (currentPageId !== finalPageId) {
            setCurrentPageId(finalPageId);
          }
          
          // Adicionar mensagem do usuário e mensagem de processamento
          const updatedMessages = [...currentPage.messages, userMessage, processingMessage];
          
          console.log(`[Page] Adicionando mensagens para PDF ${i + 1}/${pdfFiles.length}:`, {
            finalPageId,
            pdfName: pdfFile.name,
            userMessage,
            processingMessage,
            totalMessages: updatedMessages.length
          });
          
          updatePage(finalPageId, {
            messages: updatedMessages,
          });
          
          // Garantir que a página está selecionada
          setCurrentPageId(finalPageId);
          
          // Forçar atualização imediata
          setUpdateTrigger((prev) => prev + 1);

          // Executar extração para este PDF específico
          // Nota: O schema sempre é enviado na API (necessário para processar),
          // mas a mensagem de schema no chat só aparece quando mudou (otimização de UI)
          console.log(`[Page] Processando PDF ${i + 1}/${pdfFiles.length}: ${pdfFile.name}`);
          console.log("[Page]   - label:", label);
          console.log("[Page]   - schema:", schema);
          console.log("[Page]   - devMode:", devMode);
          console.log("[Page]   - schemaChanged:", schemaChanged);
          
          let runs: RunResult[] = [];
          try {
            console.log(`[Page] Chamando extract() para ${pdfFile.name}...`);
            // Processar este PDF (ping-pong: um PDF → resposta → próximo PDF)
            runs = await extract(label, schema, [pdfFile], devMode, useLearning);
            console.log(`[Page] extract() retornou para ${pdfFile.name}:`, runs);
          } catch (extractError) {
            console.error(`[Page] ERRO em extract() para ${pdfFile.name}:`, extractError);
            throw extractError;
          }

          // Buscar página atualizada do estado
          const updatedPages = storage.loadPages();
          const finalPage = updatedPages.find((p) => p.id === finalPageId);
          
          if (!finalPage) {
            console.error(`[Page] Sessão ${finalPageId} não encontrada após extração`);
            continue; // Continuar para próximo PDF ao invés de retornar
          }

          // Remover mensagem de processamento e adicionar resultados
          const messagesWithoutProcessing = finalPage.messages.filter(
            (msg) => msg.id !== processingMessageId
          );

          // Criar mensagens do sistema para cada run
          const systemMessages: MessageSystem[] = runs.map((run) => {
            // Log para debug do dev mode
            if (devMode) {
              console.log(`[Page] Run ${run.run_id} - dev data:`, run.dev);
              console.log(`[Page] Run ${run.run_id} - dev.elapsed_ms:`, run.dev?.elapsed_ms);
              console.log(`[Page] Run ${run.run_id} - dev.graph_url:`, run.dev?.graph_url);
            }
            return {
              id: `msg_system_${run.run_id}`,
              role: "system",
              createdAt: Date.now(),
              run,
            };
          });

          // Atualizar página com mensagens do sistema (sem a de processamento)
          updatePage(finalPageId, {
            messages: [...messagesWithoutProcessing, ...systemMessages],
          });
          
          // Forçar atualização
          setUpdateTrigger((prev) => prev + 1);
          
          // Aguardar que a resposta apareça na tela antes de processar o próximo PDF
          // Verificar se a mensagem de processamento foi substituída por uma mensagem de resultado
          if (!isLast) {
            console.log(`[Page] Aguardando resposta aparecer na tela antes de processar próximo PDF...`);
            // Aguardar um pouco mais para garantir que o React renderizou a atualização
            await new Promise(resolve => setTimeout(resolve, 300));
            
            // Verificar se a mensagem de processamento foi removida
            let attempts = 0;
            const maxAttempts = 20; // 2 segundos máximo
            while (attempts < maxAttempts) {
              const checkPages = storage.loadPages();
              const checkPage = checkPages.find((p) => p.id === finalPageId);
              if (checkPage) {
                const hasProcessingMessage = checkPage.messages.some(
                  (msg) => msg.id === processingMessageId
                );
                const hasResultMessage = checkPage.messages.some(
                  (msg) => msg.role === "system" && 
                           msg.run && 
                           msg.run.status !== "processing" &&
                           (msg.run.status === "ok" || msg.run.status === "error")
                );
                
                // Se não tem mais mensagem de processamento E tem mensagem de resultado, pode continuar
                if (!hasProcessingMessage && hasResultMessage) {
                  console.log(`[Page] Resposta apareceu na tela, continuando para próximo PDF`);
                  break;
                }
              }
              await new Promise(resolve => setTimeout(resolve, 100));
              attempts++;
            }
          }
        }
      } catch (err: any) {
        console.error("Erro ao extrair:", err);
        
        // Adicionar mensagem de erro (usar finalPageId se disponível, senão currentPageId)
        const errorPageId = finalPageId || currentPageId;
        if (!errorPageId) {
          console.error("[Page] Não é possível adicionar erro: nenhum pageId disponível");
          setIsProcessing(false);
          return;
        }
        
        const errorPages = storage.loadPages();
        const errorPage = errorPages.find((p) => p.id === errorPageId);
        
        if (errorPage) {
          // Remover mensagens de processamento
          const messagesWithoutProcessing = errorPage.messages.filter(
            (msg) => !msg.id?.startsWith("msg_processing_")
          );
          
          const errorMessage: MessageSystem = {
            id: `msg_error_${Date.now()}`,
            role: "system",
            createdAt: Date.now(),
            run: {
              run_id: `error_${Date.now()}`,
              filename: "Error",
              status: "error",
              result: undefined,
              error_message: err.response?.data?.detail || err.message || "Unknown error",
              dev: undefined,
            },
          };
          
          updatePage(errorPageId, {
            messages: [...messagesWithoutProcessing, errorMessage],
          });
          // Forçar atualização
          setUpdateTrigger((prev) => prev + 1);
        } else {
          // Se não encontrou página, mostrar erro genérico
          alert(`Error: ${err.response?.data?.detail || err.message || "Unknown error"}`);
        }
      } finally {
        // Sempre liberar a trava no final
        setIsProcessing(false);
      }
    },
    [currentPageId, pages, addPage, updatePage, extract, devMode, useLearning, isProcessing]
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
              title: `New Extraction ${new Date().toLocaleString("en-US", { 
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
        <div className="text-lg">Loading...</div>
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
              <span className="text-sm text-[#e5e5e5]">PDF Extractor</span>
            </div>
            <div className="flex items-center gap-4">
              <LearningToggle value={useLearning} onChange={setUseLearning} />
              <DevModeToggle value={devMode} onChange={setDevMode} />
            </div>
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
