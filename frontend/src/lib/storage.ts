/** Persistência em sessionStorage. */

import { Page, Folder } from "./types";

const STORAGE_KEYS = {
  PAGES: "graph_extractor_pages",
  FOLDERS: "graph_extractor_folders",
  DEV_MODE: "graph_extractor_dev_mode",
} as const;

export const storage = {
  /**
   * Salva páginas no sessionStorage.
   */
  savePages(pages: Page[]): void {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem(STORAGE_KEYS.PAGES, JSON.stringify(pages));
    } catch (error) {
      console.error("Erro ao salvar páginas:", error);
    }
  },

  /**
   * Carrega páginas do sessionStorage.
   */
  loadPages(): Page[] {
    if (typeof window === "undefined") return [];
    try {
      const data = sessionStorage.getItem(STORAGE_KEYS.PAGES);
      return data ? JSON.parse(data) : [];
    } catch (error) {
      console.error("Erro ao carregar páginas:", error);
      return [];
    }
  },

  /**
   * Salva pastas no sessionStorage.
   */
  saveFolders(folders: Record<string, Folder>): void {
    if (typeof window === "undefined") return;
    try {
      sessionStorage.setItem(STORAGE_KEYS.FOLDERS, JSON.stringify(folders));
    } catch (error) {
      console.error("Erro ao salvar pastas:", error);
    }
  },

  /**
   * Carrega pastas do sessionStorage.
   */
  loadFolders(): Record<string, Folder> {
    if (typeof window === "undefined") return {};
    try {
      const data = sessionStorage.getItem(STORAGE_KEYS.FOLDERS);
      return data ? JSON.parse(data) : {};
    } catch (error) {
      console.error("Erro ao carregar pastas:", error);
      return {};
    }
  },

  /**
   * Salva estado do dev mode no localStorage (persiste entre sessões).
   */
  saveDevMode(enabled: boolean): void {
    if (typeof window === "undefined") return;
    try {
      localStorage.setItem(STORAGE_KEYS.DEV_MODE, String(enabled));
    } catch (error) {
      console.error("Erro ao salvar dev mode:", error);
    }
  },

  /**
   * Carrega estado do dev mode do localStorage.
   */
  loadDevMode(): boolean {
    if (typeof window === "undefined") return false;
    try {
      const data = localStorage.getItem(STORAGE_KEYS.DEV_MODE);
      return data === "true";
    } catch (error) {
      console.error("Erro ao carregar dev mode:", error);
      return false;
    }
  },
};

/**
 * Exporta dados como ZIP (inputs/ e outputs/).
 */
export async function exportToZip(
  pages: Page[]
): Promise<Blob> {
  const JSZip = (await import("jszip")).default;
  const zip = new JSZip();

  const inputsFolder = zip.folder("inputs");
  const outputsFolder = zip.folder("outputs");

  pages.forEach((page) => {
    page.messages.forEach((message) => {
      if (message.role === "user") {
        // Salvar inputs
        const inputData = {
          label: message.payload.label,
          schema: message.payload.schemaName,
          pdfFiles: message.payload.pdfFiles,
        };
        inputsFolder?.file(
          `page_${page.id}_input.json`,
          JSON.stringify(inputData, null, 2)
        );
      } else if (message.role === "system" && message.run.result) {
        // Salvar outputs
        outputsFolder?.file(
          `${message.run.run_id}_output.json`,
          JSON.stringify(message.run.result, null, 2)
        );
      }
    });
  });

  return zip.generateAsync({ type: "blob" });
}

