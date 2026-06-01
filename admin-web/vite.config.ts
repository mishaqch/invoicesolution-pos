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
          // Function form (required by Rolldown / Vite 8; also valid on
          // Rollup). Splits the heavy, rarely-changing vendor libs into
          // their own cacheable chunks so app-code edits don't bust them.
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|react-router|scheduler)[\\/]/.test(id))
              return "react-vendor";
            if (/[\\/]node_modules[\\/]@tanstack[\\/]/.test(id)) return "query-vendor";
            if (/[\\/]node_modules[\\/](react-hook-form|@hookform|zod)[\\/]/.test(id))
              return "form-vendor";
            return undefined;
          },
        },
      },
      chunkSizeWarningLimit: 600,
    },
  };
});
