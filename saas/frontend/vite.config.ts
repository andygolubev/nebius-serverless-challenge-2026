import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build emits to backend/static so the single app image serves API + UI.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../backend/static",
    emptyOutDir: true,
  },
  server: {
    // Local dev proxies API calls to the FastAPI backend.
    proxy: {
      "/jobs": "http://127.0.0.1:8000",
      "/health": "http://127.0.0.1:8000",
      "/training-options": "http://127.0.0.1:8000",
      "/robots": "http://127.0.0.1:8000",
      "/robot-samples": "http://127.0.0.1:8000",
      "/robot-setups": "http://127.0.0.1:8000",
      "/environment-catalog": "http://127.0.0.1:8000",
      "/auth": "http://127.0.0.1:8000",
      "/me": "http://127.0.0.1:8000",
    },
  },
});
