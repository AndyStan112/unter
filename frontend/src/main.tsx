import { createRoot } from 'react-dom/client';
import '@fontsource/roboto/latin-400.css';
import '@fontsource/roboto/latin-ext-400.css';
import '@fontsource/roboto/latin-500.css';
import '@fontsource/roboto/latin-ext-500.css';
import '@fontsource/roboto/latin-700.css';
import '@fontsource/roboto/latin-ext-700.css';
import '@fontsource/roboto/latin-900.css';
import '@fontsource/roboto/latin-ext-900.css';
import App from './app/App';

// Only update the former root worker. The ride worker is managed by RideLayout.
if ('serviceWorker' in navigator)
  navigator.serviceWorker
    .getRegistrations()
    .then((registrations) =>
      Promise.all(
        registrations.filter((r) => r.scope === `${location.origin}/`).map((r) => r.update()),
      ),
    )
    .catch(() => {});
createRoot(document.getElementById('root')!).render(<App />);
