import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// El navegador contacta directamente otro puerto: no se oculta CORS con un proxy.
export default defineConfig({
  plugins: [react()],
  server: { host: '0.0.0.0', port: 5175, strictPort: true },
})
