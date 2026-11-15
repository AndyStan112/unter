import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: { proxy: { '/api': 'http://localhost:5180', '/healthz': 'http://localhost:5180' } },
  build: { rollupOptions: { input: { dashboard: 'index.html', ride: 'ride/index.html' } } },
  test: { environment: 'jsdom', restoreMocks: true },
});
