export interface DictionaryFetchResult {
  ok: boolean;
  status: number;
  body: unknown;
}

export interface AppDataXlsxDeps {
  isScriptLoaded: (absoluteSrc: string) => boolean;
  markScriptLoaded: (absoluteSrc: string) => void;
  getGlobalXlsx: () => unknown;
}

export interface AppDataDictionaryDeps {
  apiBase: string;
  fetchDictionary: (url: string) => Promise<DictionaryFetchResult>;
  setCache: (cache: Record<string, unknown>) => void;
}

export interface EnsureXlsxResult {
  handled: boolean;
  xlsx: unknown;
}

export interface AppDataBridge {
  ensureXlsxLoaded(deps: AppDataXlsxDeps): Promise<EnsureXlsxResult>;
  loadDictionary(deps: AppDataDictionaryDeps): Promise<boolean>;
}

const XLSX_SRC = "https://cdn.jsdelivr.net/npm/xlsx@0.19.3/dist/xlsx.full.min.js";

function asRecord(input: unknown): Record<string, unknown> | null {
  if (!input || typeof input !== "object") return null;
  return input as Record<string, unknown>;
}

async function ensureXlsxLoaded(deps: AppDataXlsxDeps): Promise<EnsureXlsxResult> {
  const existing = deps.getGlobalXlsx();
  if (existing) {
    return { handled: true, xlsx: existing };
  }

  const absoluteSrc = new URL(XLSX_SRC, window.location.origin).href;
  if (deps.isScriptLoaded(absoluteSrc)) {
    return { handled: true, xlsx: deps.getGlobalXlsx() };
  }

  await new Promise<void>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = XLSX_SRC;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load XLSX library."));
    document.head.appendChild(script);
  });

  deps.markScriptLoaded(absoluteSrc);
  return { handled: true, xlsx: deps.getGlobalXlsx() };
}

async function loadDictionary(deps: AppDataDictionaryDeps): Promise<boolean> {
  const apiBase = String(deps.apiBase || "").trim();
  if (!apiBase) return false;

  try {
    const url = `${apiBase}/lookup/dictionary`;
    const result = await deps.fetchDictionary(url);
    if (!result.ok) {
      throw new Error(`Dictionary request failed: ${result.status}`);
    }

    const body = asRecord(result.body);
    if (body?.ok) {
      const cache = asRecord(body.data) || {};
      deps.setCache(cache);
      console.log("Dictionary loaded:", Object.keys(cache));
    }
    return true;
  } catch (error) {
    console.error("Failed to load dictionary:", error);
    return true;
  }
}

export function createAppDataBridge(): AppDataBridge {
  return {
    ensureXlsxLoaded,
    loadDictionary,
  };
}

