import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const workspace = fileURLToPath(new URL('..', import.meta.url));
const outDir = fileURLToPath(new URL('../dist/web', import.meta.url));

export default defineConfig({
  root,
  plugins: [react()],
  server: {
    // host: true 是为了手机能通过局域网 IP 访问开发服务器
    host: true,
    port: 5173,
    fs: { allow: [workspace] },
    proxy: {
      '/api': { target: 'http://127.0.0.1:8787', changeOrigin: true },
    },
  },
  build: {
    outDir,
    emptyOutDir: true,
  },
});
