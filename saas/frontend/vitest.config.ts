import { configDefaults, defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    environmentOptions: { jsdom: { url: "http://localhost/" } },
    exclude: [...configDefaults.exclude, "e2e/**"],
    setupFiles: "./src/test-setup.ts",
  },
});
