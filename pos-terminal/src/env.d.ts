/// <reference types="vite/client" />

import type { PosApi } from "../electron/preload";

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare global {
  interface Window {
    api: PosApi;
  }
}

export {};
