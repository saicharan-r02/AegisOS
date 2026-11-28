import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// `npm run build` writes straight into the folder FastAPI serves (aegis_os/static),
// so a local build, the Docker image and CI all use the same path.
// `npm run dev` proxies API calls to a locally running `aegis server`.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../aegis_os/static',
    emptyOutDir: true,
    // three.js is a lazy-loaded chunk (see OrbitScene), so its size does not block first paint.
    chunkSizeWarningLimit: 600,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
