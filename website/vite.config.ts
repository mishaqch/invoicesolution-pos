import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Marketing site build. Static output served by nginx at the apex domain.
// During local dev, /api proxies to the Django backend so the contact form
// can post leads against a real endpoint.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 5174,
      proxy: {
        "/api": env.VITE_API_URL ?? "http://localhost:8000",
      },
    },
    build: {
      rollupOptions: {
        output: {
          // Split the heavy, rarely-changing vendor libs so app edits don't
          // bust their cache. framer-motion is the largest dep here.
          manualChunks(id) {
            if (!id.includes("node_modules")) return undefined;
            if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|react-router|scheduler)[\\/]/.test(id))
              return "react-vendor";
            if (/[\\/]node_modules[\\/]framer-motion[\\/]/.test(id)) return "motion-vendor";
            return undefined;
          },
        },
      },
      chunkSizeWarningLimit: 600,
    },
  };
});
