import { useEffect, useState } from 'react';
import { buildAsset } from '../services/buildAsset';
interface InstallPrompt extends Event {
  prompt: () => Promise<void>;
}
export function useInstall() {
  const [prompt, setPrompt] = useState<InstallPrompt | null>(null);
  useEffect(() => {
    const ready = (event: Event) => {
      event.preventDefault();
      setPrompt(event as InstallPrompt);
    };
    const installed = () => setPrompt(null);
    window.addEventListener('beforeinstallprompt', ready);
    window.addEventListener('appinstalled', installed);
    if ('serviceWorker' in navigator && import.meta.env.PROD)
      navigator.serviceWorker
        .register(buildAsset('/ride/sw.js'), { scope: '/ride/', updateViaCache: 'none' })
        .catch(() => {});
    return () => {
      window.removeEventListener('beforeinstallprompt', ready);
      window.removeEventListener('appinstalled', installed);
    };
  }, []);
  return {
    available: !!prompt,
    install: async () => {
      const event = prompt;
      setPrompt(null);
      await event?.prompt();
    },
  };
}
