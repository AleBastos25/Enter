/** Hook para gerenciar extração de PDFs. */

import { useState, useCallback } from "react";
import { apiClient } from "@/lib/api";
import { RunResult, ExtractionState, ExtractionStep } from "@/lib/types";

export function useExtraction() {
  const [state, setState] = useState<ExtractionState>("idle");
  const [currentStep, setCurrentStep] = useState<ExtractionStep | null>(null);
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [results, setResults] = useState<RunResult[]>([]);

  const extract = useCallback(
    async (
      label: string,
      schema: Record<string, string> | string,
      pdfFiles: File[],
      devMode: boolean = false,
      useLearning: boolean = true
    ): Promise<RunResult[]> => {
      setState("uploading");
      setError(null);
      setResults([]);
      setCurrentStep("received");

      try {
        console.log("[useExtraction] Iniciando extração...");
        console.log("[useExtraction] Label:", label);
        console.log("[useExtraction] PDFs:", pdfFiles.map(f => f.name));
        console.log("[useExtraction] Schema:", schema);
        console.log("[useExtraction] Dev mode:", devMode);
        
        // Simular progresso (backend não retorna streaming ainda)
        setState("processing");
        setProgress({ current: 0, total: pdfFiles.length });

        console.log("[useExtraction] Chamando apiClient.extractGraph...");
        // Chamar API
        const response = await apiClient.extractGraph(
          label,
          schema,
          pdfFiles,
          devMode,
          useLearning
        );
        console.log("[useExtraction] Resposta recebida:", response);

        setResults(response.runs);
        setState("done");
        setProgress(null);
        setCurrentStep("done");

        return response.runs;
      } catch (err: any) {
        console.error("[useExtraction] ERRO na extração:", err);
        console.error("[useExtraction] Tipo do erro:", err?.constructor?.name);
        console.error("[useExtraction] Mensagem:", err?.message);
        if (err?.response) {
          console.error("[useExtraction] Status:", err.response.status);
          console.error("[useExtraction] Data:", err.response.data);
        } else if (err?.request) {
          console.error("[useExtraction] Requisição enviada mas sem resposta");
        }
        const errorMessage = err.response?.data?.detail || err.message || "Erro desconhecido";
        setError(errorMessage);
        setState("error");
        setProgress(null);
        throw err;
      }
    },
    []
  );

  const reset = useCallback(() => {
    setState("idle");
    setCurrentStep(null);
    setProgress(null);
    setError(null);
    setResults([]);
  }, []);

  return {
    state,
    currentStep,
    progress,
    error,
    results,
    extract,
    reset,
  };
}

