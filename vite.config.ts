import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  base: "/static/dist/",
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2020",
    rollupOptions: {
      input: {
        app: resolve(__dirname, "frontend/src/entries/app.ts"),
        login: resolve(__dirname, "frontend/src/entries/login.ts"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
});
