import { readdir, readFile, writeFile } from 'node:fs/promises';
import { createHash } from 'node:crypto';
import { join } from 'node:path';
const root = new URL('../dist/', import.meta.url);
async function files(directory, prefix = '') {
  const entries = await readdir(directory, { withFileTypes: true });
  const nested = await Promise.all(
    entries.map((e) =>
      e.isDirectory()
        ? files(join(directory, e.name), `${prefix}${e.name}/`)
        : `${prefix}${e.name}`,
    ),
  );
  return nested.flat();
}
const assets = (await files(root.pathname))
  .filter((path) => path.startsWith('assets/'))
  .map((path) => `/${path}`);
const html = await readFile(new URL('ride/index.html', root), 'utf8');
const buildId = html.match(/manifest\.webmanifest\?v=([a-f0-9]+)/)?.[1];
if (!buildId) throw new Error('Versioned PWA manifest missing from ride entry.');
const manifestPath = new URL('ride/manifest.webmanifest', root);
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
manifest.icons = manifest.icons.map((icon) => ({ ...icon, src: `${icon.src}?v=${buildId}` }));
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
const versionedAssets = [
  'ride/manifest.webmanifest',
  'icon.svg',
  'icon-192.png',
  'icon-512.png',
].map((path) => `/${path}?v=${buildId}`);
const hash = createHash('sha256').update(html + assets.join('|'));
for (const file of ['ride/manifest.webmanifest', 'icon.svg', 'icon-192.png', 'icon-512.png']) {
  hash.update(await readFile(new URL(file, root)));
}
const version = hash.digest('hex').slice(0, 12);
const template = await readFile(new URL('../src/app/service-worker.js', import.meta.url), 'utf8');
const worker = template
  .replace('__CACHE_VERSION__', version)
  .replace(
    '__PRECACHE_ASSETS__',
    JSON.stringify(['/ride/', '/ride/index.html', ...versionedAssets, ...assets]),
  );
await writeFile(new URL('ride/sw.js', root), worker);
console.log(`Ride shell: ${assets.length} local assets, version ${version}`);
