import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Default config for local dev server
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    host: true
  }
});
