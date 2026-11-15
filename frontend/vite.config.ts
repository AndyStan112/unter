import { createHash } from 'node:crypto';
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Stable across local/Docker builds. Public PWA URLs must change even when a CDN
// overrides origin cache headers for unversioned .js, manifests or icons.
const hash = createHash('sha256');
function include(directory: string) {
  for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) =>
    a.name.localeCompare(b.name, 'en'),
  )) {
    const file = join(directory, entry.name);
    if (entry.isDirectory()) include(file);
    else hash.update(file).update(readFileSync(file));
  }
}
for (const directory of ['src', 'public', 'scripts']) include(directory);
for (const file of ['index.html', 'ride/index.html', 'package-lock.json', 'vite.config.ts'])
  hash.update(readFileSync(file));
hash.update(process.env.VITE_MAP_TILE_URL || '');
const buildId = hash.digest('hex').slice(0, 16);

export default defineConfig({
  define: { 'import.meta.env.VITE_BUILD_ID': JSON.stringify(buildId) },
  plugins: [
    react(),
    {
      name: 'version-public-pwa-assets',
      transformIndexHtml: (html) =>
        html.replace(
          /(\/icon(?:-\d+\.png|\.svg)|\/ride\/manifest\.webmanifest)(?=["'])/g,
          `$1?v=${buildId}`,
        ),
    },
  ],
  server: { proxy: { '/api': 'http://localhost:5180', '/healthz': 'http://localhost:5180' } },
  build: { rollupOptions: { input: { dashboard: 'index.html', ride: 'ride/index.html' } } },
  test: { environment: 'jsdom', restoreMocks: true },
});
