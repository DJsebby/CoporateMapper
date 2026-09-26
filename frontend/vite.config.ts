import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
export default defineConfig({ plugins: [react(), tailwindcss()], build: { rollupOptions: { output: { manualChunks: (id) => id.includes('cytoscape') ? 'graph-engine' : undefined } } }, server: { proxy: { '/api': 'http://127.0.0.1:8000' } } })
