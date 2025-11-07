/** Barra de entrada para label, schema e PDFs. */

"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { SchemaPopup } from "./SchemaPopup";

interface InputBarProps {
  onSend: (
    label: string,
    schema: Record<string, string>,
    pdfFiles: File[]
  ) => void;
  recentLabels: string[];
  disabled?: boolean;
  processingState?: string;
  currentStep?: string | null;
  progress?: { current: number; total: number } | null;
}

export function InputBar({ 
  onSend, 
  recentLabels, 
  disabled,
  processingState,
  currentStep,
  progress 
}: InputBarProps) {
  const [label, setLabel] = useState("");
  const [schema, setSchema] = useState<Record<string, string> | null>(null);
  const [schemaFile, setSchemaFile] = useState<File | null>(null);
  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [showSchemaPopup, setShowSchemaPopup] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [datasetItems, setDatasetItems] = useState<Array<{label: string, extraction_schema: Record<string, string>, pdf_path: string}> | null>(null);
  const [selectedDatasetIndex, setSelectedDatasetIndex] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const schemaInputRef = useRef<HTMLInputElement>(null);

  const handleSchemaFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSchemaFile(file);
      try {
        const text = await file.text();
        console.log("[InputBar] Arquivo de schema lido, tamanho:", text.length);
        const parsed = JSON.parse(text);
        console.log("[InputBar] Schema parseado, tipo:", typeof parsed, "é array?", Array.isArray(parsed));
        console.log("[InputBar] Schema parseado:", parsed);
        
        // CASO 1: É uma lista (dataset.json) - formato: [{label, extraction_schema, pdf_path}, ...]
        if (Array.isArray(parsed)) {
          console.log("[InputBar] Arquivo é uma lista (dataset.json)");
          
          // Validar estrutura da lista
          if (parsed.length === 0) {
            alert("Erro: A lista está vazia.");
            return;
          }
          
          // Validar que cada item tem a estrutura esperada
          const validItems = parsed.filter((item: any) => 
            item && 
            typeof item === "object" && 
            item.extraction_schema && 
            typeof item.extraction_schema === "object" &&
            item.label &&
            typeof item.label === "string"
          );
          
          if (validItems.length === 0) {
            alert("Erro: A lista não contém itens válidos. Cada item deve ter: label, extraction_schema, pdf_path");
            return;
          }
          
          console.log("[InputBar] Dataset válido com", validItems.length, "itens");
          setDatasetItems(validItems);
          setSelectedDatasetIndex(0); // Selecionar primeiro por padrão
          
          // Aplicar primeiro item automaticamente
          const firstItem = validItems[0];
          setLabel(firstItem.label);
          setSchema(firstItem.extraction_schema);
          
          return;
        }
        
        // CASO 2: É um objeto simples
        if (typeof parsed !== "object" || parsed === null) {
          alert("Erro: O schema deve ser um objeto JSON válido ou uma lista.");
          return;
        }
        
        // Se o arquivo tem estrutura {extraction_schema: {...}}, extrair apenas o extraction_schema
        if (parsed.extraction_schema && typeof parsed.extraction_schema === "object") {
          console.log("[InputBar] Arquivo tem extraction_schema, extraindo...");
          setSchema(parsed.extraction_schema);
          if (parsed.label && typeof parsed.label === "string") {
            setLabel(parsed.label);
          }
        } else {
          // Objeto simples com campos de schema
          setSchema(parsed);
        }
        
        // Limpar dataset se estava usando
        setDatasetItems(null);
        setSelectedDatasetIndex(null);
      } catch (err) {
        console.error("[InputBar] Erro ao processar schema:", err);
        alert("Erro ao ler arquivo de schema. Certifique-se de que é um JSON válido.");
      }
    }
  };

  const handleSchemaManual = (manualSchema: Record<string, string>) => {
    setSchema(manualSchema);
    setSchemaFile(null);
    // Limpar dataset quando usar schema manual
    setDatasetItems(null);
    setSelectedDatasetIndex(null);
  };

  const handlePdfFilesChange = (files: FileList | null) => {
    if (files) {
      const pdfs = Array.from(files).filter((f) => f.type === "application/pdf");
      if (pdfs.length !== files.length) {
        alert("Apenas arquivos PDF são permitidos.");
      }
      if (pdfs.length + pdfFiles.length > 10) {
        alert("Máximo de 10 PDFs permitidos.");
        return;
      }
      setPdfFiles((prev) => [...prev, ...pdfs]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handlePdfFilesChange(e.dataTransfer.files);
  };

  const removePdfFile = (index: number) => {
    setPdfFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleSend = async () => {
    console.log("[InputBar] handleSend chamado");
    console.log("[InputBar] Label:", label);
    console.log("[InputBar] Schema:", schema);
    console.log("[InputBar] PDFs:", pdfFiles.map(f => f.name));
    console.log("[InputBar] Dataset items:", datasetItems);
    
    if (pdfFiles.length === 0) {
      console.warn("[InputBar] Validação falhou - nenhum PDF");
      alert("Adicione pelo menos 1 PDF.");
      return;
    }
    
    // Se tem dataset, fazer match automático
    if (datasetItems && datasetItems.length > 0) {
      console.log("[InputBar] Dataset detectado, fazendo match automático...");
      
      const matchedPairs: Array<{pdf: File, label: string, schema: Record<string, string>, datasetItem: any}> = [];
      const unmatchedPdfs: File[] = [];
      
      // Para cada PDF, tentar encontrar match no dataset
      for (const pdf of pdfFiles) {
        const pdfName = pdf.name.toLowerCase();
        const matchedItem = datasetItems.find(item => {
          const itemPdfPath = item.pdf_path.toLowerCase();
          // Match exato ou match sem extensão
          return pdfName === itemPdfPath || 
                 pdfName === itemPdfPath.replace('.pdf', '') ||
                 pdfName.replace('.pdf', '') === itemPdfPath.replace('.pdf', '');
        });
        
        if (matchedItem) {
          matchedPairs.push({
            pdf,
            label: matchedItem.label,
            schema: matchedItem.extraction_schema,
            datasetItem: matchedItem
          });
          console.log(`[InputBar] Match encontrado: ${pdf.name} -> ${matchedItem.label} (${matchedItem.pdf_path})`);
        } else {
          unmatchedPdfs.push(pdf);
          console.warn(`[InputBar] Nenhum match encontrado para: ${pdf.name}`);
        }
      }
      
      // Verificar se há PDFs sem match
      if (unmatchedPdfs.length > 0) {
        const unmatchedNames = unmatchedPdfs.map(f => f.name).join(', ');
        const availablePaths = datasetItems.map(item => item.pdf_path).join(', ');
        const shouldContinue = confirm(
          `Os seguintes PDFs não têm correspondência no dataset:\n${unmatchedNames}\n\n` +
          `PDFs disponíveis no dataset:\n${availablePaths}\n\n` +
          `Deseja continuar apenas com os PDFs que têm match?`
        );
        
        if (!shouldContinue) {
          return;
        }
      }
      
      if (matchedPairs.length === 0) {
        alert("Nenhum PDF correspondeu a nenhum item do dataset. Verifique os nomes dos arquivos.");
        return;
      }
      
      console.log(`[InputBar] ${matchedPairs.length} PDF(s) com match encontrado(s)`);
      
      // Limpar campos
      setLabel("");
      setSchema(null);
      setPdfFiles([]);
      // Não limpar datasetItems - permite reutilizar o mesmo dataset
      
      // Enviar cada PDF individualmente com seu próprio label e schema
      try {
        for (const pair of matchedPairs) {
          console.log(`[InputBar] Enviando PDF: ${pair.pdf.name} com label: ${pair.label}`);
          console.log(`[InputBar]   Schema keys: ${Object.keys(pair.schema).join(', ')}`);
          // Enviar cada PDF individualmente com seu schema correspondente
          await onSend(pair.label, pair.schema, [pair.pdf]);
        }
        console.log("[InputBar] Todos os PDFs enviados com sucesso");
      } catch (err) {
        console.error("[InputBar] Erro ao enviar PDFs:", err);
        throw err;
      }
      
      return;
    }
    
    // Caso normal: schema único para todos os PDFs
    if (!label.trim() || !schema) {
      console.warn("[InputBar] Validação falhou - label ou schema vazio");
      alert("Preencha label e schema, ou carregue um dataset.json.");
      return;
    }
    
    console.log("[InputBar] Validação passou, preparando para enviar...");
    
    try {
      // Limpar após enviar (mas não aguardar)
      const currentLabel = label;
      const currentSchema = schema;
      const currentPdfFiles = [...pdfFiles];
      
      console.log("[InputBar] Chamando onSend...");
      console.log("[InputBar]   - Label:", currentLabel);
      console.log("[InputBar]   - Schema keys:", typeof currentSchema === "object" ? Object.keys(currentSchema) : "string");
      console.log("[InputBar]   - PDFs:", currentPdfFiles.map(f => `${f.name} (${f.size} bytes)`));
      
      setLabel("");
      setSchema(null);
      setSchemaFile(null);
      setPdfFiles([]);
      // Não limpar datasetItems - permite reutilizar o mesmo dataset
      
      // Chamar onSend
      console.log("[InputBar] Aguardando onSend...");
      await onSend(currentLabel, currentSchema, currentPdfFiles);
      console.log("[InputBar] onSend concluído");
    } catch (err) {
      console.error("[InputBar] Erro ao enviar:", err);
      console.error("[InputBar] Tipo do erro:", err?.constructor?.name);
      console.error("[InputBar] Mensagem:", err?.message);
      if (err?.stack) {
        console.error("[InputBar] Stack:", err.stack);
      }
    }
  };

  // Pode enviar se:
  // 1. Tem PDFs E (tem label+schema OU tem dataset)
  // 2. Não está desabilitado
  const canSend = pdfFiles.length > 0 && 
                  ((label.trim() && schema) || (datasetItems && datasetItems.length > 0)) && 
                  !disabled;
  
  // Log de debug para verificar estado do botão (apenas quando muda)
  useEffect(() => {
    const state = {
      canSend,
      hasLabel: !!label.trim(),
      labelLength: label.trim().length,
      hasSchema: !!schema,
      schemaType: schema ? (typeof schema === "object" ? (Array.isArray(schema) ? "array" : "object") : typeof schema) : "null",
      schemaKeys: schema && typeof schema === "object" && !Array.isArray(schema) ? Object.keys(schema) : null,
      hasPdfs: pdfFiles.length > 0,
      pdfCount: pdfFiles.length,
      disabled,
      labelValue: label,
    };
    
    console.log("[InputBar] Estado atualizado:", state);
    
      // Mostrar alerta se não pode enviar e tem campos preenchidos
      if (!canSend && (label.trim() || schema || pdfFiles.length > 0 || datasetItems)) {
        const reasons = [];
        if (pdfFiles.length === 0) reasons.push("Nenhum PDF adicionado");
        if (!datasetItems && (!label.trim() || !schema)) {
          if (!label.trim()) reasons.push("Label vazio");
          if (!schema) reasons.push("Schema não definido");
        }
        if (disabled) reasons.push("Processando (desabilitado)");
        
        console.warn("[InputBar] NÃO PODE ENVIAR. Razões:", reasons);
      }
  }, [canSend, label, schema, pdfFiles.length, disabled, datasetItems]);

  // Filtrar labels recentes que começam com o texto digitado
  const filteredLabels = recentLabels.filter((l) =>
    l.toLowerCase().startsWith(label.toLowerCase())
  );

  return (
    <div className="border-t border-[#404040] p-4 bg-[#171717]">
      <div className="max-w-3xl mx-auto space-y-3">
        {/* Label com autocomplete */}
        <div className="relative">
          <input
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label do documento"
            className="w-full p-2.5 bg-[#2a2a2a] border border-[#404040] rounded-lg text-white placeholder-[#9ca3af] focus:outline-none focus:border-[#FF6B00]"
            list="label-suggestions"
          />
          {filteredLabels.length > 0 && label && (
            <datalist id="label-suggestions">
              {filteredLabels.map((l, idx) => (
                <option key={idx} value={l} />
              ))}
            </datalist>
          )}
        </div>

        {/* Schema */}
        <div className="flex gap-2 items-center">
          <input
            ref={schemaInputRef}
            type="file"
            accept=".json"
            onChange={handleSchemaFileChange}
            className="hidden"
          />
          <button
            onClick={() => schemaInputRef.current?.click()}
            className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#404040] border border-[#404040] text-white rounded-lg text-sm transition-colors"
          >
            Upload schema.json
          </button>
          <button
            onClick={() => setShowSchemaPopup(true)}
            className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#404040] border border-[#404040] text-white rounded-lg text-sm transition-colors"
          >
            Escrever à mão
          </button>
          {schemaFile && !datasetItems && (
            <span className="text-sm text-[#9ca3af]">{schemaFile.name}</span>
          )}
          {schema && !schemaFile && !datasetItems && (
            <span className="text-sm text-[#9ca3af]">Schema manual</span>
          )}
          {datasetItems && (
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm text-[#9ca3af]">Dataset ({datasetItems.length} itens)</span>
              <select
                value={selectedDatasetIndex ?? 0}
                onChange={(e) => {
                  const idx = parseInt(e.target.value);
                  setSelectedDatasetIndex(idx);
                  const item = datasetItems[idx];
                  setLabel(item.label);
                  setSchema(item.extraction_schema);
                }}
                className="bg-[#2a2a2a] border border-[#404040] text-white rounded px-2 py-1 text-sm focus:outline-none focus:border-[#FF6B00]"
              >
                {datasetItems.map((item, idx) => (
                  <option key={idx} value={idx}>
                    {item.label} - {item.pdf_path}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>

        {/* PDFs - Drag & Drop */}
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          className={`border-2 border-dashed rounded-lg p-4 transition-colors ${
            isDragging 
              ? "border-[#FF6B00] bg-[#2a1f1f]" 
              : "border-[#404040] bg-[#1f1f1f]"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf"
            multiple
            onChange={(e) => handlePdfFilesChange(e.target.files)}
            className="hidden"
          />
          <div className="text-center">
            <p className="text-[#e5e5e5] mb-2 text-sm">
              Arraste PDFs aqui ou{" "}
              <button
                onClick={() => fileInputRef.current?.click()}
                className="text-[#FF6B00] hover:text-[#FF7A00] underline"
              >
                clique para selecionar
              </button>
            </p>
            <p className="text-xs text-[#9ca3af]">Máximo 10 PDFs</p>
          </div>
          {pdfFiles.length > 0 && (
            <div className="mt-4 space-y-2">
              {pdfFiles.map((file, idx) => (
                <div
                  key={idx}
                  className="flex justify-between items-center bg-[#2a2a2a] p-2 rounded border border-[#404040]"
                >
                  <span className="text-sm text-[#e5e5e5]">{file.name}</span>
                  <button
                    onClick={() => removePdfFile(idx)}
                    className="text-[#ff4444] hover:text-[#ff6666] text-lg"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Botão Enviar */}
        <button
          onClick={(e) => {
            // FORÇAR LOG IMEDIATO - ANTES DE QUALQUER COISA
            console.log("=".repeat(80));
            console.log("[InputBar] ===== BOTÃO CLICADO =====");
            console.log("[InputBar] Timestamp:", new Date().toISOString());
            console.log("[InputBar] canSend:", canSend);
            console.log("[InputBar] disabled:", disabled);
            console.log("[InputBar] label:", label, "(trim:", label.trim(), ")");
            console.log("[InputBar] schema:", schema, "(tipo:", typeof schema, ", é array:", Array.isArray(schema), ")");
            console.log("[InputBar] pdfFiles:", pdfFiles.map(f => f.name));
            console.log("=".repeat(80));
            
            // Verificar se pode enviar
            if (!canSend) {
              const reasons = [];
              if (!label.trim()) reasons.push("Label vazio");
              if (!schema) reasons.push("Schema não definido");
              if (pdfFiles.length === 0) reasons.push("Nenhum PDF adicionado");
              if (disabled) reasons.push("Processando (desabilitado)");
              
              console.warn("[InputBar] CANNOT SEND - canSend é false");
              alert(`Não é possível enviar:\n${reasons.join("\n")}`);
              return;
            }
            
            if (disabled) {
              console.warn("[InputBar] CANNOT SEND - botão está desabilitado");
              return;
            }
            
            console.log("[InputBar] TUDO OK - Chamando handleSend...");
            try {
              handleSend();
            } catch (error) {
              console.error("[InputBar] ERRO ao chamar handleSend:", error);
              throw error;
            }
          }}
          disabled={!canSend}
          className={`w-full py-3 rounded-lg font-medium transition-colors ${
            canSend
              ? "bg-[#FF6B00] hover:bg-[#FF7A00] text-white cursor-pointer"
              : "bg-[#2a2a2a] text-[#9ca3af] cursor-not-allowed"
          }`}
          title={!canSend ? `Não é possível enviar. ${!label.trim() ? "Label vazio. " : ""}${!schema ? "Schema não definido. " : ""}${pdfFiles.length === 0 ? "Nenhum PDF adicionado. " : ""}${disabled ? "Processando..." : ""}` : "Enviar para processar"}
        >
          {disabled ? "Processando..." : "Enviar"}
        </button>
        
        {/* Debug info - mostrar por que não pode enviar */}
        {!canSend && (label.trim() || schema || pdfFiles.length > 0 || datasetItems) && (
          <div className="text-xs text-[#ff6b6b] mt-2">
            {pdfFiles.length === 0 && "• Nenhum PDF adicionado"}
            {!datasetItems && !label.trim() && " • Label vazio"}
            {!datasetItems && !schema && " • Schema não definido"}
            {disabled && " • Processando..."}
          </div>
        )}
      </div>

      <SchemaPopup
        isOpen={showSchemaPopup}
        onClose={() => setShowSchemaPopup(false)}
        onUse={handleSchemaManual}
      />
    </div>
  );
}
