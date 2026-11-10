import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

// Vitest 没开启 globals，Testing Library 不会自动清理；这里显式注册。
afterEach(cleanup);

// jsdom 没有实现 scrollIntoView，聊天视图会用到。
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
