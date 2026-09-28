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
      // 5174 — admin-web owns 5173, so the two dev servers coexist.
      port: 5174,
      proxy: {
        "/api": env.VITE_API_URL ?? "http://localhost:8000",
      },
    },
    build: {
      // Split the heavy, rarely-changing vendor libs into their own cacheable
      // chunks so app-code edits don't bust them (mirrors admin-web).
      rollupOptions: {
        output: {
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|react-router|scheduler)[\\/]/.test(id))
              return "react-vendor";
            if (/[\\/]node_modules[\\/]@tanstack[\\/]/.test(id)) return "query-vendor";
            return undefined;
          },
        },
      },
      chunkSizeWarningLimit: 600,
    },
  };
});
