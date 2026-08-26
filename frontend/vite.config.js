import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

function validateProductionApiBase(command, mode) {
  if (command !== "build") return;

  const value = loadEnv(mode, process.cwd(), "VITE_API_BASE_URL").VITE_API_BASE_URL;
  if (!value) {
    throw new Error(
      "VITE_API_BASE_URL is required for production builds. " +
        "Example: VITE_API_BASE_URL=https://shop.exonplus.ir npm run build",
    );
  }

  const url = new URL(value);
  if (url.protocol !== "https:" || url.pathname !== "/") {
    throw new Error("VITE_API_BASE_URL must be an HTTPS origin without a path.");
  }
}

export default defineConfig(({ command, mode }) => {
  validateProductionApiBase(command, mode);

  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/api": "http://localhost:8000",
        "/media": "http://localhost:8000",
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test/setup.js",
      css: true,
    },
  };
});
