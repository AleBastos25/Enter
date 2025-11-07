/** Cliente HTTP para comunicação com a API. */

import axios, { AxiosInstance } from "axios";
import { RunResult } from "./types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiClient {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 600000, // 10 minutos para processamento de PDFs (aumentado)
    });
  }

  /**
   * Extrai dados de múltiplos PDFs.
   */
  async extractGraph(
    label: string,
    schema: Record<string, string> | string,
    pdfFiles: File[],
    devMode: boolean = false,
    useLearning: boolean = true
  ): Promise<{ runs: RunResult[] }> {
    const formData = new FormData();
    formData.append("label", label);
    formData.append("dev_mode", String(devMode));
    formData.append("use_learning", String(useLearning));

    // Schema pode ser string JSON ou arquivo
    console.log("[API] Tipo do schema:", typeof schema);
    console.log("[API] Schema value:", schema);
    console.log("[API] Schema é array?", Array.isArray(schema));
    
    if (typeof schema === "string") {
      console.log("[API] Schema é string, enviando diretamente");
      formData.append("schema", schema);
    } else {
      // FormData.append() não aceita terceiro parâmetro para strings
      // Apenas para Blob/File
      const schemaString = JSON.stringify(schema);
      console.log("[API] Schema é objeto, stringify:", schemaString.substring(0, 200));
      console.log("[API] Schema parseado de volta:", JSON.parse(schemaString));
      formData.append("schema", schemaString);
    }

    // Adicionar PDFs
    pdfFiles.forEach((file) => {
      formData.append("files", file);
    });

    console.log("=".repeat(80));
    console.log("ENVIANDO REQUISIÇÃO PARA BACKEND");
    console.log(`  URL: ${API_BASE_URL}/api/graph-extract`);
    console.log(`  Label: ${label}`);
    console.log(`  PDFs: ${pdfFiles.length} arquivo(s)`);
    pdfFiles.forEach((file, idx) => {
      console.log(`    PDF ${idx + 1}: ${file.name} (${file.size} bytes)`);
    });
    console.log(`  Schema: ${typeof schema === "string" ? "string" : "object"}`);
    if (typeof schema === "object") {
      console.log(`  Schema keys: ${Object.keys(schema).join(", ")}`);
    }
    console.log(`  Dev mode: ${devMode}`);
    console.log("=".repeat(80));
    
    // Testar conexão primeiro (com timeout curto)
    try {
      console.log("Testando conexão com backend...");
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000); // 5 segundos
      
      const testResponse = await fetch(`${API_BASE_URL}/test`, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      
      if (testResponse.ok) {
        const testData = await testResponse.json();
        console.log("Backend está respondendo:", testData);
      } else {
        console.warn("Backend retornou status:", testResponse.status);
      }
    } catch (testError: any) {
      if (testError.name === 'AbortError') {
        console.error("ERRO: Timeout ao conectar com backend!");
      } else {
        console.error("ERRO: Backend não está respondendo!", testError);
      }
      console.error(`  Verifique se o backend está rodando em ${API_BASE_URL}`);
      throw new Error(`Backend não está respondendo. Verifique se está rodando em ${API_BASE_URL}`);
    }
    
    try {
      console.log("Enviando requisição de extração...");
      console.log("FormData keys:", Array.from(formData.keys()));
      console.log("FormData entries:", Array.from(formData.entries()).map(([k, v]) => [k, v instanceof File ? v.name : typeof v]));
      
      // NÃO definir Content-Type manualmente - axios faz isso automaticamente com boundary
      const response = await this.client.post<{ runs: RunResult[] }>(
        "/api/graph-extract",
        formData,
        {
          // Removido headers - axios define automaticamente para FormData
          onUploadProgress: (progressEvent) => {
            if (progressEvent.total) {
              const percentCompleted = Math.round((progressEvent.loaded * 100) / progressEvent.total);
              console.log(`Upload: ${percentCompleted}%`);
            }
          },
        }
      );

      console.log("=".repeat(80));
      console.log("RESPOSTA RECEBIDA DO BACKEND");
      console.log("Resposta:", response.data);
      console.log("=".repeat(80));
      return response.data;
    } catch (error: any) {
      console.error("=".repeat(80));
      console.error("ERRO NA REQUISIÇÃO");
      console.error("Erro completo:", error);
      if (error.response) {
        console.error("  Status:", error.response.status);
        console.error("  Data:", error.response.data);
        console.error("  Headers:", error.response.headers);
      } else if (error.request) {
        console.error("  Requisição enviada mas SEM RESPOSTA do servidor");
        console.error(`  Verifique se o backend está rodando em ${API_BASE_URL}`);
        console.error("  Request:", error.request);
      } else {
        console.error("  Erro ao configurar requisição:", error.message);
      }
      console.error("=".repeat(80));
      throw error;
    }
  }

  /**
   * Obtém URL do HTML do grafo.
   */
  getGraphUrl(runId: string): string {
    return `${API_BASE_URL}/graph/${runId}.html`;
  }
}

export const apiClient = new ApiClient();

