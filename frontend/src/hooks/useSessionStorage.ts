/** Hook para gerenciar sessionStorage. */

import { useState, useEffect, useCallback } from "react";
import { Page, Folder } from "@/lib/types";
import { storage } from "@/lib/storage";

export function useSessionStorage() {
  const [pages, setPages] = useState<Page[]>([]);
  const [folders, setFolders] = useState<Record<string, Folder>>({});
  const [isLoaded, setIsLoaded] = useState(false);

  // Função auxiliar para remover duplicatas de páginas
  const removeDuplicatePages = useCallback((pages: Page[]): Page[] => {
    const seen = new Set<string>();
    const unique: Page[] = [];
    
    for (const page of pages) {
      if (!seen.has(page.id)) {
        seen.add(page.id);
        unique.push(page);
      }
    }
    
    return unique;
  }, []);

  // Carregar dados ao montar
  useEffect(() => {
    const loadedPages = storage.loadPages();
    const loadedFolders = storage.loadFolders();
    // Remover duplicatas ao carregar
    const uniquePages = removeDuplicatePages(loadedPages);
    if (uniquePages.length !== loadedPages.length) {
      console.warn(`[useSessionStorage] Removidas ${loadedPages.length - uniquePages.length} páginas duplicadas ao carregar`);
      // Salvar versão sem duplicatas
      storage.savePages(uniquePages);
    }
    setPages(uniquePages);
    setFolders(loadedFolders);
    setIsLoaded(true);
  }, [removeDuplicatePages]);

  // Nota: Não precisamos de um useEffect separado para remover duplicatas do estado
  // porque:
  // 1. addPage já verifica duplicatas antes de adicionar
  // 2. O carregamento inicial remove duplicatas
  // 3. O salvamento sempre salva versão sem duplicatas

  // Salvar páginas quando mudarem
  useEffect(() => {
    if (isLoaded) {
      // Sempre salvar a versão sem duplicatas
      const uniquePages = removeDuplicatePages(pages);
      storage.savePages(uniquePages);
    }
  }, [pages, isLoaded, removeDuplicatePages]);

  // Salvar pastas quando mudarem
  useEffect(() => {
    if (isLoaded) {
      storage.saveFolders(folders);
    }
  }, [folders, isLoaded]);

  const addPage = useCallback((page: Page) => {
    setPages((prev) => {
      // Verificar se a página já existe (evitar duplicatas)
      const existingPage = prev.find((p) => p.id === page.id);
      if (existingPage) {
        console.warn(`[useSessionStorage] Página ${page.id} já existe, ignorando adição duplicada`);
        return prev;
      }
      
      const updated = [...prev, page];
      // Salvar imediatamente no storage
      if (typeof window !== "undefined") {
        storage.savePages(updated);
      }
      return updated;
    });
  }, []);

  const updatePage = useCallback((pageId: string, updates: Partial<Page>) => {
    setPages((prev) => {
      // Buscar página atual
      const currentPage = prev.find((p) => p.id === pageId);
      if (!currentPage) {
        // Se não encontrou, tentar buscar do storage e adicionar
        if (typeof window !== "undefined") {
          const storagePages = storage.loadPages();
          const storagePage = storagePages.find((p) => p.id === pageId);
          if (storagePage) {
            const updatedPage = { ...storagePage, ...updates };
            const updated = [...prev, updatedPage];
            storage.savePages(updated);
            return updated;
          }
        }
        console.warn(`Página ${pageId} não encontrada para atualização`);
        return prev;
      }
      
      // Atualizar página
      const updated = prev.map((page) => 
        page.id === pageId 
          ? { ...page, ...updates }
          : page
      );
      
      // Salvar imediatamente no storage
      if (typeof window !== "undefined") {
        storage.savePages(updated);
      }
      return updated;
    });
  }, []);

  const deletePage = useCallback((pageId: string) => {
    setPages((prev) => prev.filter((page) => page.id !== pageId));
  }, []);

  const addFolder = useCallback((folder: Folder) => {
    setFolders((prev) => ({ ...prev, [folder.id]: folder }));
  }, []);

  const addPageToFolder = useCallback((folderId: string, pageId: string) => {
    setFolders((prev) => {
      const folder = prev[folderId];
      if (!folder) return prev;
      return {
        ...prev,
        [folderId]: {
          ...folder,
          pageIds: [...folder.pageIds, pageId],
        },
      };
    });
  }, []);

  return {
    pages,
    folders,
    isLoaded,
    addPage,
    updatePage,
    deletePage,
    addFolder,
    addPageToFolder,
  };
}

