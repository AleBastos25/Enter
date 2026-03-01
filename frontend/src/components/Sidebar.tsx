/** Sidebar com sessões, busca e labels. */

"use client";

import { useState, useMemo } from "react";
import { Page, Folder } from "@/lib/types";

interface SidebarProps {
  pages: Page[];
  folders: Record<string, Folder>;
  currentPageId?: string;
  onSelectPage: (pageId: string) => void;
  onDeletePage: (pageId: string) => void;
  onUpdatePageTitle: (pageId: string, title: string) => void;
  viewMode: "pages" | "folders";
  onViewModeChange: (mode: "pages" | "folders") => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
}

export function Sidebar({
  pages,
  folders,
  currentPageId,
  onSelectPage,
  onDeletePage,
  onUpdatePageTitle,
  viewMode,
  onViewModeChange,
  searchQuery,
  onSearchChange,
}: SidebarProps) {
  const [editingPageId, setEditingPageId] = useState<string | null>(null);
  const [editingTitle, setEditingTitle] = useState("");

  // Filtrar sessões baseado na busca
  const filteredPages = useMemo(() => {
    if (!searchQuery.trim()) return pages;
    const query = searchQuery.toLowerCase();
    return pages.filter((page) => {
      const titleMatch = page.title.toLowerCase().includes(query);
      const contentMatch = page.messages.some((msg) => {
        if (msg.role === "user") {
          return msg.payload.label.toLowerCase().includes(query);
        } else if (msg.role === "system" && msg.run.result) {
          return JSON.stringify(msg.run.result).toLowerCase().includes(query);
        }
        return false;
      });
      return titleMatch || contentMatch;
    });
  }, [pages, searchQuery]);

  const handleStartEdit = (page: Page) => {
    setEditingPageId(page.id);
    setEditingTitle(page.title);
  };

  const handleSaveEdit = (pageId: string) => {
    if (editingTitle.trim()) {
      onUpdatePageTitle(pageId, editingTitle.trim());
    }
    setEditingPageId(null);
    setEditingTitle("");
  };

  const handleCancelEdit = () => {
    setEditingPageId(null);
    setEditingTitle("");
  };

  // Agrupar sessões por label (uma sessão pode aparecer em múltiplas labels)
  const pagesByLabel = useMemo(() => {
    const grouped: Record<string, Page[]> = {};
    pages.forEach((page) => {
      // Pegar todas as labels únicas da sessão (de todas as mensagens de usuário)
      const labels = new Set<string>();
      page.messages.forEach((msg) => {
        if (msg.role === "user" && msg.payload.label && !msg.payload.isSchemaOnly) {
          labels.add(msg.payload.label);
        }
      });
      
      // Adicionar a sessão em cada label que ela contém
      labels.forEach((label) => {
        if (!grouped[label]) {
          grouped[label] = [];
        }
        // Evitar duplicatas (caso a mesma sessão tenha a mesma label múltiplas vezes)
        if (!grouped[label].find((p) => p.id === page.id)) {
          grouped[label].push(page);
        }
      });
    });
    
    // Ordenar labels alfabeticamente e sessões por data (mais recente primeiro)
    const sorted: Record<string, Page[]> = {};
    Object.keys(grouped)
      .sort()
      .forEach((label) => {
        sorted[label] = grouped[label].sort((a, b) => b.createdAt - a.createdAt);
      });
    
    return sorted;
  }, [pages]);

  return (
    <div className="w-64 bg-[#171717] border-r border-[#404040] flex flex-col h-full">
      {/* Header com logo ENTER */}
      <div className="px-3 py-3 border-b border-[#404040]">
        <div className="flex items-center gap-2 mb-4">
          <div className="text-white font-bold text-lg">ENTER</div>
          <div className="w-2 h-2 bg-white"></div>
        </div>
        
        {/* Botão Nova Sessão */}
        <button
          onClick={() => {
            // Criar nova sessão ao clicar
            const newPageId = `page_${Date.now()}`;
            onSelectPage(newPageId);
          }}
          className="w-full px-3 py-2 bg-[#FF6B00] hover:bg-[#FF7A00] text-white rounded-md text-sm font-medium flex items-center gap-2 mb-3 transition-colors"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Session
        </button>

        {/* Busca */}
        <div className="relative">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="Search sessions..."
            className="w-full px-3 py-2 bg-[#2a2a2a] border border-[#404040] rounded-md text-sm text-white placeholder-[#9ca3af] focus:outline-none focus:border-[#FF6B00]"
          />
          <svg className="w-4 h-4 absolute right-3 top-2.5 text-[#9ca3af]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </div>
      </div>

      {/* Lista */}
      <div className="flex-1 overflow-y-auto p-2">
        {/* Switch Sessões / Labels */}
        <div className="flex gap-1 mb-3 p-1 bg-[#1f1f1f] rounded-md">
          <button
            onClick={() => onViewModeChange("pages")}
            className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${
              viewMode === "pages"
                ? "bg-[#FF6B00] text-white"
                : "text-[#9ca3af] hover:text-white"
            }`}
          >
            Sessions
          </button>
          <button
            onClick={() => onViewModeChange("folders")}
            className={`flex-1 py-1.5 rounded text-xs font-medium transition-colors ${
              viewMode === "folders"
                ? "bg-[#FF6B00] text-white"
                : "text-[#9ca3af] hover:text-white"
            }`}
          >
            Labels
          </button>
        </div>

        {viewMode === "pages" ? (
          <div className="space-y-1">
            {filteredPages.length === 0 ? (
              <p className="text-xs text-[#9ca3af] p-2 text-center">No sessions found</p>
            ) : (
              filteredPages.map((page) => (
                <div
                  key={page.id}
                  className={`group px-2 py-2 rounded-md cursor-pointer transition-colors ${
                    currentPageId === page.id 
                      ? "bg-[#2a2a2a] border border-[#404040]" 
                      : "hover:bg-[#1f1f1f]"
                  }`}
                  onClick={() => onSelectPage(page.id)}
                >
                  {editingPageId === page.id ? (
                    <input
                      type="text"
                      value={editingTitle}
                      onChange={(e) => setEditingTitle(e.target.value)}
                      onBlur={() => handleSaveEdit(page.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          handleSaveEdit(page.id);
                        } else if (e.key === "Escape") {
                          handleCancelEdit();
                        }
                      }}
                      className="w-full text-sm bg-[#2a2a2a] border border-[#FF6B00] rounded px-2 py-1 text-white focus:outline-none"
                      autoFocus
                    />
                  ) : (
                    <div className="flex justify-between items-center">
                      <span
                        className="text-sm text-[#e5e5e5] truncate flex-1"
                        onDoubleClick={() => handleStartEdit(page)}
                        title={page.title}
                      >
                        {page.title}
                      </span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onDeletePage(page.id);
                        }}
                        className="opacity-0 group-hover:opacity-100 text-[#9ca3af] hover:text-white ml-2 text-xs transition-opacity"
                      >
                        ×
                      </button>
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {Object.keys(pagesByLabel).length === 0 ? (
              <p className="text-xs text-[#9ca3af] p-2 text-center">No labels found</p>
            ) : (
              Object.entries(pagesByLabel).map(([label, labelPages]) => (
                <div key={label}>
                  <div className="text-xs font-medium text-[#FF6B00] px-2 py-1.5 uppercase tracking-wide">
                    {label} <span className="text-[#9ca3af] font-normal">({labelPages.length})</span>
                  </div>
                  <div className="ml-2 space-y-1 mt-1">
                    {labelPages.map((page) => (
                      <div
                        key={page.id}
                        className={`px-2 py-1.5 rounded cursor-pointer text-sm transition-colors ${
                          currentPageId === page.id 
                            ? "bg-[#2a2a2a] text-white border-l-2 border-[#FF6B00]" 
                            : "text-[#9ca3af] hover:text-white hover:bg-[#1f1f1f]"
                        }`}
                        onClick={() => onSelectPage(page.id)}
                        title={page.title}
                      >
                        {page.title}
                      </div>
                    ))}
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
}
