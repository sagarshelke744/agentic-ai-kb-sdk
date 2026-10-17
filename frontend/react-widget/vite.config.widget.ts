import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

// Config for building standalone embeddable widget (bundles React inside)
export default defineConfig({
  plugins: [react()],
  define: {
    'process.env.NODE_ENV': JSON.stringify('production')
  },
  build: {
    outDir: 'dist',
    emptyOutDir: false,
    lib: {
      entry: resolve(__dirname, 'src/embed.ts'),
      name: 'AgenticKB',
      fileName: () => 'agentic-kb-widget.iife.js',
      formats: ['iife']
    },
    rollupOptions: {
      // In standalone widget mode, bundle everything so host page needs no extra scripts
      external: [],
      output: {
        exports: 'named'
      }
    }
  }
});
