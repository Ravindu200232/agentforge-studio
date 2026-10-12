import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// One self-contained HTML file: the script, the styles and every small image are inlined, so the preview is a single page.
export default defineConfig({
  plugins: [react(), viteSingleFile()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  logLevel: "warn",
  build: {
    outDir: "dist",
    emptyOutDir: true,
    assetsInlineLimit: 100_000_000,
    chunkSizeWarningLimit: 100_000,
    reportCompressedSize: false,
  },
});
