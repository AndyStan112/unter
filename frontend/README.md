# Unter frontend

React + TypeScript + Material UI + React Router. Node 22.12 or newer is required.

```sh
npm ci
npm run dev
npm test
npm run build
```

Vite serves the app on port 5173 and proxies `/api` to the gateway on 5180.
Production is generated in `dist/` and copied into the Python image by its
multi-stage Dockerfile. For live editing use the Vite development server.

- `src/theme/theme.ts`: palette, typography, spacing defaults, shape and shared MUI overrides.
- `src/app/router.tsx`: dashboard routes and `/ride/passenger`, `/ride/driver`.
- `src/pages/`: one page per file, grouped by dashboard/passenger/driver.
- `src/layouts/`: navigation and responsive application layouts.
- `src/components/`: reusable UI and the Leaflet map.
- `src/hooks/`: API polling, serialized mutations, installation and connectivity.
- `src/services/`: API client, session persistence and display helpers.
- `src/types/`: API data contracts.
- `public/`: PWA manifest and icons. Put future imported imagery under `src/assets/`.

Only the ride app is installable. The build creates a versioned worker and precaches
its local shell and lazy-loaded bundles so passenger/driver routes reload offline.
API data, dashboard HTML, and map tiles are never service-worker cached.

The map uses Leaflet and standard OpenStreetMap tiles with visible attribution.
Set `VITE_MAP_TILE_URL` at build time to use another compatible OSM-attributed tile
server. Production deployments with higher traffic should configure a suitable
provider. Markers can be selected by tapping the map or by using accessible zone
fields or explicit address searches. OSRM road routes include distance, ETA and directions; dashed
lines indicate an unavailable routing provider. Drivers can open live navigation.
Live driver GPS is only sent while this app is open and the driver is online.

The existing shared development Basic Auth and browser-local profiles remain in
use. No credentials belong in Vite environment variables or browser assets.

PWA URLs include a deterministic build version so a CDN retaining old `.js`,
manifest or icon responses cannot pin the app to an earlier shell. The generated
worker caches only those explicit public URLs and hashed bundles; arbitrary query
strings and API requests still bypass it.

The driver screen displays mock earnings from core's transactional settlement ledger. Passenger and
driver trip history are fetched by profile ID. Push preferences select one receiving profile per
browser subscription; notification payloads contain only status text and an app route. The service
worker never reads Basic Auth credentials or caches private API responses.

The ride experience uses a full-viewport map with floating controls and a draggable action sheet.
`RideChrome` shares the sheet height with the map so route framing leaves space for the controls.
`RideSheet` owns expansion, `LocationPicker` handles explicit address search and map pin selection,
and `RouteFields` displays the selected stops. History, earnings and notification settings live in
secondary drawers. The page itself does not scroll; longer sheets and secondary panels scroll
internally, with safe-area padding for installed phone apps.
