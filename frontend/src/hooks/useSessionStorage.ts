/** Hook para gerenciar sessionStorage. */

import { useState, useEffect, useCallback } from "react";
import { Page, Folder } from "@/lib/types";
import { storage } from "@/lib/storage";

export function useSessionStorage() {
  const [pages, setPages] = useState<Page[]>([]);
  const [folders, setFolders] = useState<Record<string, Folder>>({});
  const [isLoaded, setIsLoaded] = useState(false);

  // Carregar dados ao montar
  useEffect(() => {
    const loadedPages = storage.loadPages();
    const loadedFolders = storage.loadFolders();
    setPages(loadedPages);
    setFolders(loadedFolders);
    setIsLoaded(true);
  }, []);

  // Salvar páginas quando mudarem
  useEffect(() => {
    if (isLoaded) {
      storage.savePages(pages);
    }
  }, [pages, isLoaded]);

  // Salvar pastas quando mudarem
  useEffect(() => {
    if (isLoaded) {
      storage.saveFolders(folders);
    }
  }, [folders, isLoaded]);

  const addPage = useCallback((page: Page) => {
    setPages((prev) => {
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

