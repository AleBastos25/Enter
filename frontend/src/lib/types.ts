/** Tipos TypeScript para a aplicação. */

export type RunResult = {
  run_id: string;
  filename: string;
  status: "ok" | "error" | "processing";
  result?: Record<string, any>;
  error_message?: string;
  dev?: {
    elapsed_ms?: number;
    rules_used?: string[];
    graph_url?: string;
  };
};

export type MessageUser = {
  id: string;
  role: "user";
  createdAt: number;
  payload: {
    label: string;
    schemaName: string; // "Manual" ou nome do arquivo
    pdfFiles: { name: string; size: number }[];
  };
};

export type MessageSystem = {
  id: string;
  role: "system";
  createdAt: number;
  run: RunResult;
};

export type Message = MessageUser | MessageSystem;

export type Page = {
  id: string;
  title: string; // editável
  createdAt: number;
  messages: Message[];
  labelFolderId?: string;
};

export type Folder = {
  id: string;
  label: string;
  pageIds: string[];
  createdAt: number;
};

export type ExtractionStep =
  | "received"
  | "building_graph"
  | "regex_matching"
  | "embedding_matching"
  | "tiebreaking"
  | "post_processing"
  | "done";

export type ExtractionState =
  | "idle"
  | "uploading"
  | "processing"
  | "done"
  | "error";

