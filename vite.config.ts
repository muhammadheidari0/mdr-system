import { defineConfig } from "vite";
import { resolve } from "node:path";

export default defineConfig({
  base: "/static/dist/",
  build: {
    outDir: "static/dist",
    emptyOutDir: true,
    sourcemap: true,
    rollupOptions: {
      input: {
        app: resolve(__dirname, "frontend/src/entries/app.ts")
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "chunks/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]"
      }
    }
  }
});
