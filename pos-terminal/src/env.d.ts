/// <reference types="vite/client" />

import type { PosApi } from "../electron/preload";

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_BRANCH_NAME?: string;
  readonly VITE_TERMINAL_NAME?: string;
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
