import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "src"),
        "@pos/shared": path.resolve(__dirname, "../shared"),
      },
    },
    server: {
      port: 5173,
      proxy: {
        "/api": env.VITE_API_URL ?? "http://localhost:8000",
      },
    },
    build: {
      // Phase 8 — keep first paint <1s on 3G. Vendor split lets the
      // browser cache react/router/query independently from app code,
      // which dominates the bundle once the report viewer + wizard ship.
      rollupOptions: {
        output: {
          manualChunks: {
            "react-vendor": ["react", "react-dom", "react-router-dom"],
            "query-vendor": ["@tanstack/react-query"],
            "form-vendor": ["react-hook-form", "@hookform/resolvers", "zod"],
          },
        },
      },
      chunkSizeWarningLimit: 600,
    },
  };
});
