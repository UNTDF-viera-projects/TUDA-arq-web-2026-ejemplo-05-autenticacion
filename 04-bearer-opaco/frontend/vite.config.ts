import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Sin proxy: el navegador debe llamar a la API en otro origen para estudiar CORS.
export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5174, strictPort: true },
})
