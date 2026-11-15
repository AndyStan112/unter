import { useEffect } from 'react';
import { useLocation } from 'react-router';
import theme from '../theme/theme';
import { buildAsset } from '../services/buildAsset';

export function usePageMetadata() {
  const { pathname } = useLocation();
  useEffect(() => {
    const ride = pathname === '/ride' || pathname.startsWith('/ride/');
    document.title = ride ? 'Unter · Ride & drive' : 'Unter · Control room';
    const color = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
    if (color) color.content = ride ? theme.palette.primary.main : theme.palette.secondary.main;
    let manifest = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
    if (ride && !manifest) {
      manifest = document.createElement('link');
      manifest.rel = 'manifest';
      manifest.href = buildAsset('/ride/manifest.webmanifest');
      document.head.append(manifest);
    } else if (!ride) manifest?.remove();
  }, [pathname]);
}
