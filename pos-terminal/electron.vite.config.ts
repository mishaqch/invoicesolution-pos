import path from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  main: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: {
          index: path.resolve(__dirname, "electron/main.ts"),
          // Bundled alongside main.cjs so the customer-display window
          // can reference it via `path.join(__dirname, "customer-display-preload.cjs")`.
          "customer-display-preload": path.resolve(
            __dirname, "electron/customer-display-preload.ts",
          ),
          // Sync worker runs as a utilityProcess.fork() — electron-vite
          // must produce its own .cjs bundle, otherwise main.ts's
          // `existsSync(workerPath)` returns false for every candidate
          // and the manager bails with "worker entry not found",
          // leaving the outbound queue forever pending. The candidates
          // in sync/manager.ts look for `sync/worker.cjs`, so we emit
          // exactly that path.
          "sync/worker": path.resolve(__dirname, "electron/sync/worker.ts"),
        },
        output: { format: "cjs", entryFileNames: "[name].cjs" },
      },
    },
  },
  preload: {
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: path.resolve(__dirname, "electron/preload.ts") },
        output: { format: "cjs", entryFileNames: "[name].cjs" },
      },
    },
  },
  renderer: {
    root: path.resolve(__dirname),
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
        "@pos/shared": path.resolve(__dirname, "../shared"),
      },
    },
    build: {
      rollupOptions: {
        input: { index: path.resolve(__dirname, "index.html") },
      },
    },
    server: {
      port: 5174,
    },
  },
});
