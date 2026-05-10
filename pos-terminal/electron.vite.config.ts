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
