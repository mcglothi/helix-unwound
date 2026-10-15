import { defineConfig } from 'vite'
import { svelte } from '@sveltejs/vite-plugin-svelte'

// Built assets are served by the Python engine (helixtune serve); dev server proxies the API.
export default defineConfig({
  plugins: [svelte()],
  base: '/',
  build: { outDir: '../src/helixtune/web/dist', emptyOutDir: true },
  server: { proxy: { '/api': 'http://127.0.0.1:8765' } },
})
