import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
// Marketing site build. Static output served by nginx at the apex domain.
// During local dev, /api proxies to the Django backend so the contact form
// can post leads against a real endpoint.
export default defineConfig(function (_a) {
    var _b;
    var mode = _a.mode;
    var env = loadEnv(mode, process.cwd(), "");
    return {
        plugins: [react()],
        resolve: {
            alias: { "@": path.resolve(__dirname, "src") },
        },
        server: {
            port: 5174,
            proxy: {
                "/api": (_b = env.VITE_API_URL) !== null && _b !== void 0 ? _b : "http://localhost:8000",
            },
        },
        build: {
            rollupOptions: {
                output: {
                    // Split the heavy, rarely-changing vendor libs so app edits don't
                    // bust their cache. framer-motion is the largest dep here.
                    manualChunks: function (id) {
                        if (!id.includes("node_modules"))
                            return undefined;
                        if (/[\\/]node_modules[\\/](react|react-dom|react-router-dom|react-router|scheduler)[\\/]/.test(id))
                            return "react-vendor";
                        if (/[\\/]node_modules[\\/]framer-motion[\\/]/.test(id))
                            return "motion-vendor";
                        return undefined;
                    },
                },
            },
            chunkSizeWarningLimit: 600,
        },
    };
});
