import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import svgr from 'vite-plugin-svgr';

export default defineConfig({
  plugins: [react(), svgr()],
  base: '/',  // Serve from root
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'https://mcp.mrrobot.dev',
        changeOrigin: true,
        secure: true,
      },
    },
  },
  build: {
    outDir: 'dist',
  },
});
