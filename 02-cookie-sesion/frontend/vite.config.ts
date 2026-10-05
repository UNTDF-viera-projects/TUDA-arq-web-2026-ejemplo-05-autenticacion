import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Sin proxy: el navegador consume directamente la API en otro origen.
export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5172, strictPort: true },
})
