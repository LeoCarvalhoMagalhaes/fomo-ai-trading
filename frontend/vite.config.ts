import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // No GitHub Pages o site fica em /fomo-ai-trading/
  base: process.env.VITE_BASE_PATH ?? "/",
  server: {
    port: 5320,
    proxy: {
      "/api": "http://127.0.0.1:8765",
      "/ws": { target: "ws://127.0.0.1:8765", ws: true },
    },
  },
});
