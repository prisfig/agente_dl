import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// La interfaz no contiene secretos: la clave del backend se escribe al abrirla y vive solo en la sesión del navegador.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
});
