import path from "node:path";
import { defineConfig, externalizeDepsPlugin } from "electron-vite";
import react from "@vitejs/plugin-react";

// Expose POS_* env vars (printer interface, DB path, FBR test mode, …) to
// import.meta.env in ALL processes — by default Vite only exposes VITE_*.
// The main process can't read process.env for these (electron-vite doesn't
// populate it), so they must come through import.meta.env at build time.
const ENV_PREFIX = ["VITE_", "POS_"];

export default defineConfig({
  main: {
    envPrefix: ENV_PREFIX,
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
    envPrefix: ENV_PREFIX,
    plugins: [externalizeDepsPlugin()],
    build: {
      rollupOptions: {
        input: { index: path.resolve(__dirname, "electron/preload.ts") },
        output: { format: "cjs", entryFileNames: "[name].cjs" },
      },
    },
  },
  renderer: {
    envPrefix: ENV_PREFIX,
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
