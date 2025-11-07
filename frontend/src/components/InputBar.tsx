/** Barra de entrada para label, schema e PDFs. */

"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";
import { SchemaPopup } from "./SchemaPopup";

interface InputBarProps {
  onSend: (
    label: string,
    schema: Record<string, string>,
    pdfFiles: File[],
    schemaJsonString?: string // Texto JSON original do schema
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
  const [labelFile, setLabelFile] = useState<File | null>(null);
  const [schema, setSchema] = useState<Record<string, string> | null>(null);
  const [schemaFile, setSchemaFile] = useState<File | null>(null);
  const [schemaJsonString, setSchemaJsonString] = useState<string | null>(null); // Texto JSON original
  const [pdfFiles, setPdfFiles] = useState<File[]>([]);
  const [showSchemaPopup, setShowSchemaPopup] = useState(false);
  const [showSchemaEditor, setShowSchemaEditor] = useState(false);
  const [schemaEditorText, setSchemaEditorText] = useState("");
  const [isDraggingLabel, setIsDraggingLabel] = useState(false);
  const [isDraggingPdf, setIsDraggingPdf] = useState(false);
  const [isDraggingSchema, setIsDraggingSchema] = useState(false);
  const [datasetItems, setDatasetItems] = useState<Array<{label: string, extraction_schema: Record<string, string>, pdf_path: string}> | null>(null);
  const [selectedDatasetIndex, setSelectedDatasetIndex] = useState<number | null>(null);
  const [mode, setMode] = useState<"multi" | "single">("multi"); // multi = padrão
  
  const fileInputRef = useRef<HTMLInputElement>(null);
  const schemaInputRef = useRef<HTMLInputElement>(null);
  const labelInputRef = useRef<HTMLInputElement>(null);

  // Detectar modo automaticamente
  useEffect(() => {
    // Modo single se: 1 PDF E (1 schema file que é objeto, não lista) OU apenas 1 PDF sem dataset
    const isSingleMode = (pdfFiles.length === 1 && schemaFile && schema && !Array.isArray(schema) && !datasetItems) ||
                        (pdfFiles.length === 1 && !datasetItems && !schemaFile);
    setMode(isSingleMode ? "single" : "multi");
  }, [pdfFiles.length, schemaFile, schema, datasetItems]);

  // Handler para arquivo de label (drag & drop ou seleção)
  const handleLabelFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setLabelFile(file);
      try {
        const text = await file.text();
        const parsed = JSON.parse(text);
        // Se for objeto com label, usar
        if (typeof parsed === "object" && !Array.isArray(parsed) && parsed.label) {
          setLabel(parsed.label);
        } else if (typeof parsed === "string") {
          setLabel(parsed);
        }
      } catch (err) {
        console.error("[InputBar] Erro ao ler arquivo de label:", err);
      }
    }
  };

  const handleSchemaFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSchemaFile(file);
      try {
        const text = await file.text();
        console.log("[InputBar] Arquivo de schema lido, tamanho:", text.length);
        // Salvar texto JSON original
        setSchemaJsonString(text);
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
          // Para dataset, salvar o texto JSON original da lista completa
          setSchemaJsonString(text);
          
          return;
        }
        
        // CASO 2: É um objeto simples (modo single)
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
          // Salvar o texto JSON original do objeto completo
          setSchemaJsonString(text);
        } else {
          // Objeto simples com campos de schema
          setSchema(parsed);
          // Salvar o texto JSON original
          setSchemaJsonString(text);
        }
        
        // Limpar dataset se estava usando
        setDatasetItems(null);
        setSelectedDatasetIndex(null);
        
        // Atualizar texto do editor
        setSchemaEditorText(JSON.stringify(parsed, null, 2));
      } catch (err) {
        console.error("[InputBar] Erro ao processar schema:", err);
        alert("Erro ao ler arquivo de schema. Certifique-se de que é um JSON válido.");
      }
    }
  };

  const handleSchemaManual = (manualSchema: Record<string, string>) => {
    setSchema(manualSchema);
    setSchemaFile(null);
    // Salvar texto JSON original do schema manual
    setSchemaJsonString(JSON.stringify(manualSchema, null, 2));
    // Limpar dataset quando usar schema manual
    setDatasetItems(null);
    setSelectedDatasetIndex(null);
    setSchemaEditorText(JSON.stringify(manualSchema, null, 2));
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

  // Drag & Drop handlers para Label
  const handleLabelDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingLabel(true);
  };

  const handleLabelDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingLabel(false);
  };

  const handleLabelDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingLabel(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleLabelFileChange({ target: { files } } as any);
    }
  };

  // Drag & Drop handlers para PDF
  const handlePdfDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingPdf(true);
  };

  const handlePdfDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingPdf(false);
  };

  const handlePdfDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingPdf(false);
    handlePdfFilesChange(e.dataTransfer.files);
  };

  // Drag & Drop handlers para Schema
  const handleSchemaDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingSchema(true);
  };

  const handleSchemaDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingSchema(false);
  };

  const handleSchemaDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDraggingSchema(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleSchemaFileChange({ target: { files } } as any);
    }
  };

  const removePdfFile = (index: number) => {
    setPdfFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleEditSchema = () => {
    if (schema) {
      setSchemaEditorText(JSON.stringify(schema, null, 2));
      setShowSchemaEditor(true);
    }
  };

  const handleSaveSchemaEdit = () => {
    try {
      const parsed = JSON.parse(schemaEditorText);
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        alert("Schema deve ser um objeto JSON, não uma lista.");
        return;
      }
      setSchema(parsed);
      // Salvar texto JSON original editado
      setSchemaJsonString(schemaEditorText);
      setShowSchemaEditor(false);
    } catch (err) {
      alert("JSON inválido. Verifique a sintaxe.");
    }
  };

  const handleSend = async () => {
    console.log("[InputBar] handleSend chamado");
    console.log("[InputBar] Label:", label);
    console.log("[InputBar] Schema:", schema);
    console.log("[InputBar] PDFs:", pdfFiles.map(f => f.name));
    console.log("[InputBar] Dataset items:", datasetItems);
    console.log("[InputBar] Mode:", mode);
    
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
      
      // Limpar campos apenas após todos os envios
      // Não limpar datasetItems - permite reutilizar o mesmo dataset
      
      // Enviar cada PDF individualmente com seu próprio label e schema
      // Aguardar resposta aparecer na tela antes de enviar o próximo
      // Todos na mesma sessão (chat scrollável)
      try {
        for (let i = 0; i < matchedPairs.length; i++) {
          const pair = matchedPairs[i];
          console.log(`[InputBar] Enviando PDF ${i + 1}/${matchedPairs.length}: ${pair.pdf.name} com label: ${pair.label}`);
          console.log(`[InputBar]   Schema keys: ${Object.keys(pair.schema).join(', ')}`);
          
          // Enviar este PDF e aguardar resposta completa
          // Passar um flag para não criar nova sessão se já houver uma
          // Para dataset, passar o texto JSON original da lista completa
          const pairSchemaJson = schemaJsonString || JSON.stringify(pair.schema, null, 2);
          await onSend(pair.label, pair.schema, [pair.pdf], pairSchemaJson);
          
          // Aguardar um pouco para garantir que a resposta apareceu na tela
          // e que o estado foi atualizado antes de enviar o próximo
          // IMPORTANTE: Aguardar mais tempo para garantir que a sessão foi criada/atualizada
          if (i < matchedPairs.length - 1) {
            console.log(`[InputBar] Aguardando resposta aparecer na tela antes de enviar próximo PDF...`);
            // Aguardar mais tempo para garantir que:
            // 1. A resposta foi renderizada
            // 2. O estado da sessão foi atualizado
            // 3. A próxima chamada vai reutilizar a mesma sessão
            await new Promise(resolve => setTimeout(resolve, 1500));
          }
        }
        console.log("[InputBar] Todos os PDFs enviados com sucesso");
        
        // Limpar apenas PDFs e label após todos os envios serem concluídos
        // Manter schema visível para que possa ser atualizado/acumulado
        setLabel("");
        setPdfFiles([]);
        // Não limpar schema, schemaFile, schemaJsonString - permite reutilizar e atualizar
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
      // Salvar valores antes de enviar (não limpar ainda)
      const currentLabel = label;
      const currentSchema = schema;
      const currentPdfFiles = [...pdfFiles];
      
      console.log("[InputBar] Chamando onSend...");
      console.log("[InputBar]   - Label:", currentLabel);
      console.log("[InputBar]   - Schema keys:", typeof currentSchema === "object" ? Object.keys(currentSchema) : "string");
      console.log("[InputBar]   - PDFs:", currentPdfFiles.map(f => `${f.name} (${f.size} bytes)`));
      
      // Chamar onSend e aguardar conclusão antes de limpar
      console.log("[InputBar] Aguardando onSend...");
      // Passar texto JSON original do schema (ou converter se não tiver)
      const currentSchemaJson = schemaJsonString || JSON.stringify(currentSchema, null, 2);
      await onSend(currentLabel, currentSchema, currentPdfFiles, currentSchemaJson);
      console.log("[InputBar] onSend concluído");
      
      // Limpar apenas PDFs e label após sucesso
      // Manter schema visível para que possa ser atualizado/acumulado
      setLabel("");
      setPdfFiles([]);
      // Não limpar schema, schemaFile, schemaJsonString - permite reutilizar e atualizar
      // Não limpar datasetItems - permite reutilizar o mesmo dataset
    } catch (err: any) {
      console.error("[InputBar] Erro ao enviar:", err);
      console.error("[InputBar] Tipo do erro:", err?.constructor?.name);
      console.error("[InputBar] Mensagem:", err?.message);
      if (err?.stack) {
        console.error("[InputBar] Stack:", err.stack);
      }
      // Não limpar campos em caso de erro - permite tentar novamente
    }
  };

  // Pode enviar se:
  // 1. Tem PDFs E (tem label+schema OU tem dataset)
  // 2. Não está desabilitado
  const canSend = pdfFiles.length > 0 && 
                  ((label.trim() && schema) || (datasetItems && datasetItems.length > 0)) && 
                  !disabled;

  // Filtrar labels recentes que começam com o texto digitado
  const filteredLabels = recentLabels.filter((l) =>
    l.toLowerCase().startsWith(label.toLowerCase())
  );

  // Função para obter label de cada PDF no modo multi
  const getPdfLabels = () => {
    if (!datasetItems || pdfFiles.length === 0) return [];
    
    return pdfFiles.map((pdf) => {
      const pdfName = pdf.name.toLowerCase();
      const matchedItem = datasetItems.find(item => {
        const itemPdfPath = item.pdf_path.toLowerCase();
        return pdfName === itemPdfPath || 
               pdfName === itemPdfPath.replace('.pdf', '') ||
               pdfName.replace('.pdf', '') === itemPdfPath.replace('.pdf', '');
      });
      return {
        pdf,
        label: matchedItem?.label || "Sem label",
        matched: !!matchedItem
      };
    });
  };

  const pdfLabels = mode === "multi" && datasetItems ? getPdfLabels() : [];

  return (
    <div className="border-t border-[#404040] p-4 bg-[#171717]">
      <div className="max-w-6xl mx-auto">
        {/* Layout em linha: JSON (esquerda), PDF (meio), Label (direita) + Botão circular */}
        <div className="flex gap-4 items-center">
          {/* JSON - Esquerda */}
          <div className="flex flex-col flex-1">
            <label className="text-xs text-[#9ca3af] mb-2">Schema JSON</label>
            <div
              onDragOver={handleSchemaDragOver}
              onDragLeave={handleSchemaDragLeave}
              onDrop={handleSchemaDrop}
              onClick={() => schemaInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-4 transition-colors min-h-[120px] flex flex-col cursor-pointer ${
                isDraggingSchema
                  ? "border-[#FF6B00] bg-[#2a1f1f]"
                  : "border-[#404040] bg-[#1f1f1f] hover:border-[#505050]"
              }`}
            >
              <input
                ref={schemaInputRef}
                type="file"
                accept=".json"
                onChange={handleSchemaFileChange}
                className="hidden"
              />
              {schema ? (
                <div className="flex-1 flex flex-col">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs text-[#e5e5e5] truncate">
                      {schemaFile ? schemaFile.name : "Schema manual"}
                    </span>
                    <div className="flex gap-1">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleEditSchema();
                        }}
                        className="text-[#FF6B00] hover:text-[#FF7A00] p-1"
                        title="Editar JSON"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSchema(null);
                          setSchemaFile(null);
                          setDatasetItems(null);
                        }}
                        className="text-[#ff4444] hover:text-[#ff6666] p-1"
                        title="Remover"
                      >
                        ×
                      </button>
                    </div>
                  </div>
                  {datasetItems ? (
                    <select
                      value={selectedDatasetIndex ?? 0}
                      onChange={(e) => {
                        const idx = parseInt(e.target.value);
                        setSelectedDatasetIndex(idx);
                        const item = datasetItems[idx];
                        setLabel(item.label);
                        setSchema(item.extraction_schema);
                      }}
                      onClick={(e) => e.stopPropagation()}
                      className="bg-[#2a2a2a] border border-[#404040] text-white rounded px-2 py-1 text-xs focus:outline-none focus:border-[#FF6B00]"
                    >
                      {datasetItems.map((item, idx) => (
                        <option key={idx} value={idx}>
                          {item.label} - {item.pdf_path}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <div className="text-xs text-[#9ca3af] mt-2">
                      {Object.keys(schema).length} campo(s)
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-center flex-1 flex flex-col items-center justify-center">
                  <svg className="w-8 h-8 text-[#9ca3af] mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <p className="text-xs text-[#9ca3af] mb-2">
                    Arraste ou clique para selecionar
                  </p>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowSchemaPopup(true);
                    }}
                    className="text-xs text-[#FF6B00] hover:text-[#FF7A00] underline"
                  >
                    Escrever manualmente
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* PDF - Meio */}
          <div className="flex flex-col flex-1">
            <label className="text-xs text-[#9ca3af] mb-2">PDF</label>
            <div
              onDragOver={handlePdfDragOver}
              onDragLeave={handlePdfDragLeave}
              onDrop={handlePdfDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-2 transition-colors h-[120px] flex flex-col cursor-pointer ${
                isDraggingPdf
                  ? "border-[#FF6B00] bg-[#2a1f1f]"
                  : "border-[#404040] bg-[#1f1f1f] hover:border-[#505050]"
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                multiple={mode === "multi"}
                onChange={(e) => handlePdfFilesChange(e.target.files)}
                className="hidden"
              />
              {pdfFiles.length === 0 ? (
                <div className="text-center flex-1 flex flex-col items-center justify-center">
                  <svg className="w-8 h-8 text-[#9ca3af] mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                  </svg>
                  <p className="text-xs text-[#9ca3af] mb-2">
                    Arraste ou clique para selecionar
                  </p>
                  {mode === "multi" && (
                    <p className="text-xs text-[#9ca3af]">Máximo 10 PDFs</p>
                  )}
                </div>
              ) : (
                <div className="grid grid-cols-5 gap-1.5 h-full overflow-y-auto">
                  {pdfFiles.map((file, idx) => (
                    <div
                      key={idx}
                      className="bg-[#2a2a2a] border border-[#404040] rounded p-1.5 flex flex-col items-center justify-center relative group"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <svg className="w-4 h-4 text-[#9ca3af] mb-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
                      </svg>
                      <span className="text-[10px] text-[#e5e5e5] truncate w-full text-center leading-tight" title={file.name}>{file.name}</span>
                      <button
                        onClick={() => removePdfFile(idx)}
                        className="absolute top-0 right-0 w-4 h-4 bg-[#ff4444] text-white rounded-full flex items-center justify-center text-[10px] opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Remover"
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* LABEL - Direita */}
          <div className="flex flex-col flex-1">
            <label className="text-xs text-[#9ca3af] mb-2">Label</label>
            {mode === "single" ? (
              // Modo single: caixa de texto
              <div className="w-full h-[36px] bg-[#2a2a2a] border border-[#404040] rounded-lg flex items-center">
                <input
                  type="text"
                  value={label}
                  onChange={(e) => setLabel(e.target.value)}
                  placeholder="Digite uma label"
                  className="w-full px-2.5 py-1.5 bg-transparent text-white placeholder-[#9ca3af] focus:outline-none border-none"
                  list="label-suggestions"
                />
              </div>
            ) : (
              // Modo multi: caixa mostrando labels de cada PDF do dataset
              <div className="w-full p-2 bg-[#2a2a2a] border border-[#404040] rounded-lg h-[120px] flex flex-col">
                {pdfLabels.length > 0 ? (
                  <div className="grid grid-cols-5 gap-1.5 h-full overflow-y-auto">
                    {pdfLabels.map((item, idx) => (
                      <div
                        key={idx}
                        className={`p-1.5 rounded border flex flex-col items-center justify-center relative group ${
                          item.matched
                            ? "bg-[#1f1f1f] border-[#404040]"
                            : "bg-[#2a1f1f] border-[#ff4444]"
                        }`}
                        title={`${item.pdf.name}\nLabel: ${item.label}`}
                      >
                        <svg className="w-4 h-4 mb-1 text-[#9ca3af]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                        <span className={`text-[10px] truncate w-full text-center leading-tight ${
                          item.matched ? "text-[#e5e5e5]" : "text-[#ff6666]"
                        }`} title={item.pdf.name}>
                          {item.pdf.name}
                        </span>
                        <span 
                          className={`text-[9px] truncate w-full text-center leading-tight ${
                            item.matched ? "text-[#9ca3af]" : "text-[#ff8888]"
                          }`} 
                          title={item.label}
                          style={{ cursor: 'help' }}
                        >
                          {item.label}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="flex items-center justify-center text-center h-full">
                    <p className="text-xs text-[#9ca3af]">
                      {datasetItems 
                        ? "Adicione PDFs para ver suas labels"
                        : "Carregue um dataset.json para ver labels"}
                    </p>
                  </div>
                )}
              </div>
            )}
            {filteredLabels.length > 0 && label && mode === "single" && (
              <datalist id="label-suggestions">
                {filteredLabels.map((l, idx) => (
                  <option key={idx} value={l} />
                ))}
              </datalist>
            )}
          </div>

          {/* Botão Enviar Circular - Direita */}
          <div className="flex items-center" style={{ minHeight: '120px' }}>
            <button
              onClick={(e) => {
                console.log("[InputBar] ===== BOTÃO CLICADO =====");
                console.log("[InputBar] Mode:", mode);
                console.log("[InputBar] canSend:", canSend);
                console.log("[InputBar] disabled:", disabled);
                
                if (!canSend) {
                  const reasons = [];
                  if (pdfFiles.length === 0) reasons.push("Nenhum PDF adicionado");
                  if (!datasetItems && (!label.trim() || !schema)) {
                    if (!label.trim()) reasons.push("Label vazio");
                    if (!schema) reasons.push("Schema não definido");
                  }
                  if (disabled) reasons.push("Processando (desabilitado)");
                  
                  alert(`Não é possível enviar:\n${reasons.join("\n")}`);
                  return;
                }
                
                if (disabled) {
                  return;
                }
                
                try {
                  handleSend();
                } catch (error) {
                  console.error("[InputBar] ERRO ao chamar handleSend:", error);
                  throw error;
                }
              }}
              disabled={!canSend}
              className={`w-14 h-14 rounded-full flex items-center justify-center transition-all ${
                canSend
                  ? "bg-[#FF6B00] hover:bg-[#FF7A00] text-white cursor-pointer hover:scale-110"
                  : "bg-[#FF6B00] text-white cursor-not-allowed opacity-50"
              }`}
              title={disabled ? "Processando..." : "Enviar"}
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 10l7-7m0 0l7 7m-7-7v18" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Popup de edição de schema */}
      {showSchemaEditor && (
        <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-50">
          <div className="bg-[#171717] border border-[#404040] rounded-lg p-6 w-[90vw] max-w-5xl h-[85vh] flex flex-col">
            <h2 className="text-xl font-bold mb-4 text-white">Editar Schema JSON</h2>
            <textarea
              value={schemaEditorText}
              onChange={(e) => setSchemaEditorText(e.target.value)}
              className="flex-1 bg-[#2a2a2a] border border-[#404040] rounded p-3 text-white font-mono text-sm focus:outline-none focus:border-[#FF6B00] resize-none"
              placeholder='{"campo": "descrição"}'
            />
            <div className="flex gap-2 mt-4">
              <button
                onClick={handleSaveSchemaEdit}
                className="px-4 py-2 bg-[#FF6B00] hover:bg-[#FF7A00] text-white rounded-lg"
              >
                Salvar
              </button>
              <button
                onClick={() => setShowSchemaEditor(false)}
                className="px-4 py-2 bg-[#2a2a2a] hover:bg-[#404040] text-white rounded-lg"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      <SchemaPopup
        isOpen={showSchemaPopup}
        onClose={() => setShowSchemaPopup(false)}
        onUse={handleSchemaManual}
      />
    </div>
  );
}
