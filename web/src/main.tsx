import React from 'react';
import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './styles.css';

const container = document.getElementById('root');
if (!container) throw new Error('找不到 #root 挂载点');

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

// PWA：只在安全上下文注册（局域网 http 访问时浏览器不允许，属预期行为）
const secure = location.protocol === 'https:' || ['localhost', '127.0.0.1'].includes(location.hostname);
if ('serviceWorker' in navigator && secure) {
  const hadController = Boolean(navigator.serviceWorker.controller);

  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/sw.js')
      .then((registration) => registration.update().catch(() => {}))
      .catch(() => {
        /* 离线缓存失败不影响使用 */
      });
  });

  // 新版本 Service Worker 接管后自动刷新一次；首次安装不刷新。
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) window.location.reload();
  });
}
