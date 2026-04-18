// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, cloudflare (build-only),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... } }) if needed.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import { damaCorpusFsPlugin } from "./vite-plugin-dama-corpus-fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
/** AN corpus (`an1`…`an11` + optional `aud/`) lives in this repo by default. Override with `VITE_DAMA5_ROOT`. */
const corpusRoot = process.env.VITE_DAMA5_ROOT
  ? path.resolve(process.env.VITE_DAMA5_ROOT)
  : path.resolve(__dirname);
const damaFs =
  fs.existsSync(corpusRoot) && fs.statSync(corpusRoot).isDirectory()
    ? damaCorpusFsPlugin(corpusRoot)
    : null;

// Proxy /api to a local FastAPI backend (optional). Start it on port 8000 when using chat/reflect.
const damaProxy = {
  "/api": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
  },
  // Corpus MP3s (`<corpusRoot>/aud`) without clashing with `public/aud/*` used for bundled demos.
  "/dama-aud": {
    target: "http://127.0.0.1:8000",
    changeOrigin: true,
    rewrite: (path: string) => path.replace(/^\/dama-aud/, "/aud"),
  },
} as const;

export default defineConfig({
  vite: {
    plugins: damaFs ? [damaFs] : [],
    server: {
      fs: {
        // App source + corpus root (same folder by default).
        allow: [path.resolve(__dirname), corpusRoot],
      },
      proxy: { ...damaProxy },
    },
    // Same as dev: LAN `vite preview --host` must proxy /api or corpus calls 404 / hang.
    preview: {
      fs: {
        allow: [path.resolve(__dirname), corpusRoot],
      },
      proxy: { ...damaProxy },
    },
  },
});
