// Vite settings. In development the interface runs on port 5173 and sends /api calls
// to the FastAPI server on port 8000. `npm run build` writes the finished site to
// frontend/dist, which FastAPI then serves itself (one address for everything).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://localhost:8000" },
  },
});
