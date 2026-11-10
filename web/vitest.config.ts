import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { fileURLToPath } from 'node:url';

// 测试配置独立于 web/vite.config.ts（后者只负责构建和开发服务器）。
// root 固定为仓库根，这样 include 与 setupFiles 都使用 web/src/... 路径。
const root = fileURLToPath(new URL('..', import.meta.url));

export default defineConfig({
  root,
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./web/src/test-setup.ts'],
    include: ['web/src/**/*.test.ts', 'web/src/**/*.test.tsx'],
  },
});
