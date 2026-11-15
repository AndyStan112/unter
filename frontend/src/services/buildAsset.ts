/** Cache-busting for public files whose stable paths may be retained by the CDN. */
export const buildAsset = (path: string) => `${path}?v=${import.meta.env.VITE_BUILD_ID}`;
