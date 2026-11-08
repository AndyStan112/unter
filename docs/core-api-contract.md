# `core` API and events

`core` owns all ride data: riders, drivers (including their live position), trips, offers, prices, surge rules, incentives and proposals. Other services read it through this API or follow it through RabbitMQ events. Nobody else touches its database.

## Basics

- **Base URL:** `https://unter.windogs.win/api/<path>` from outside (mobile app, browser), with the admin Basic Auth. Inside the cluster it's `http://core:8080/<path>` with the service Basic Auth.
- **Mutations through the gateway** (POST/PATCH) need the header `X-Unter-Request: 1`.
- **Format:** JSON with `snake_case` keys, UUID ids, UTC ISO-8601 times (`2026-11-02T08:15:30Z`), coordinates as `{"lat": 45.7537, "lon": 21.2257}`, money in RON.
- **Errors:** `{"error": "<code>", "message": "<text>"}`.
    - `400`: invalid input (`invalid_request`, `unknown_zone`, `unknown_rider`).
    - `404`: unknown id (`not_found`).
    - `409`: the action doesn't fit the current state, or someone else got there first. A 409 is a normal outcome: show it and move on. Codes: `driver_busy`, `rider_has_open_trip`, `not_your_trip`, `not_your_offer`, `offer_expired`, `offer_not_pending`, `trip_not_cancellable`, `trip_not_assigned`, `trip_not_picked_up`, `proposal_not_pending`.
- **Errors from the gateway itself** (before the request reaches `core`) use `{"detail": "<text>"}` instead:
    - `401` wrong or missing login
    - `403` missing `X-Unter-Request`
    - `404` invalid path
    - `413` body over 16 KB
    - `503` `core` unreachable
- **No login:** the app creates its rider or driver once, keeps the returned `id`, and sends it in the request body where needed.
- **Mobile app:** a native app can call the API as is. A web app or PWA served from another address would be blocked by the browser: the gateway sends no CORS headers, so that would need a gateway change first.
- **Other services in the cluster:** only the gateway and the MCP server are allowed to call `core` directly (Kubernetes network policy). Anything else goes through the gateway, or asks Andy for a policy entry.
- **Full API docs (OpenAPI 3.1):** `https://unter.windogs.win/api/openapi`, as JSON behind the same login. Load it into any OpenAPI viewer to browse it. Its `servers` entry (`http://core:8080`) is the address inside the cluster: from outside, use the base URL above.

## How a ride works

1. The rider requests a trip. `core` looks for the **nearest AVAILABLE driver whose position was updated in the last 2 minutes** and offers them the trip.
2. The driver has **30 seconds** to accept. If they reject, don't answer, or go offline, the trip is offered to the next nearest driver. A driver is never offered the same trip twice.
3. If no driver takes the trip within **2 minutes**, it becomes `UNMATCHED`.
4. On accept, the price is fixed: **(5.00 RON + 2.50 RON per straight-line km) × the pickup zone's surge** (1.0 without surge).
5. The driver picks up, then completes the trip, and is `AVAILABLE` again.

A rider can have only one open trip at a time.

## Objects

```jsonc
// Zone: Centru, Iosefin, Fabric. A point belongs to the zone with the nearest center.
{"name": "Iosefin", "lat": 45.7480, "lon": 21.2080}

// Rider
{"id": "…", "name": "Ana", "created_at": "…"}

// Driver. status: OFFLINE | AVAILABLE | OFFERED | ON_TRIP. position and zone are null until the first location update.
{"id": "…", "name": "Mihai", "status": "AVAILABLE", "current_trip_id": null,
 "position": {"lat": 45.7502, "lon": 21.2101}, "position_updated_at": "…", "zone": "Iosefin"}

// Trip. status: REQUESTED → OFFERED → ASSIGNED → PICKED_UP → COMPLETED,
//       or CANCELLED / UNMATCHED. OFFERED can go back to REQUESTED when an offer ends.
{"id": "…", "rider_id": "…", "driver_id": null, "zone": "Iosefin",
 "pickup": {"lat": …, "lon": …}, "dropoff": {"lat": …, "lon": …},
 "status": "REQUESTED", "surge_multiplier": null, "price": null,
 "requested_at": "…", "assigned_at": null, "picked_up_at": null,
 "completed_at": null, "cancelled_at": null}

// Offer: a trip proposed to one driver. status: PENDING | ACCEPTED | REJECTED | EXPIRED
{"id": "…", "trip_id": "…", "driver_id": "…", "status": "PENDING",
 "created_at": "…", "expires_at": "…", "responded_at": null}

// Proposal. type: surge | incentive | null. status: pending | approved | rejected
{"id": "…", "zone": "Iosefin", "type": "surge",
 "params": {"multiplier": 1.5, "starts_at": "…", "ends_at": "…"},
 "reason": "…", "status": "pending", "created_at": "…", "decided_at": null}

// Surge rule / incentive: what an approved proposal creates.
{"id": "…", "zone": "Iosefin", "multiplier": 1.5, "starts_at": "…", "ends_at": "…", "proposal_id": "…"}
{"id": "…", "zone": "Fabric", "bonus_per_trip": 5.00, "starts_at": "…", "ends_at": "…", "proposal_id": "…"}
```

## Endpoints

**Driver app**

| Call | Body | Returns |
|---|---|---|
| `POST /drivers` | `{"name"}` | `201` the new Driver (`OFFLINE`) |
| `POST /drivers/{id}/online` | | Driver. Already online or busy: no change |
| `POST /drivers/{id}/offline` | | Driver. A pending offer is handed back. `409 driver_busy` during a trip |
| `POST /drivers/{id}/location` | `{"lat", "lon"}` | `204`. Send every 5–10 s while online: without it the driver gets no offers |
| `GET /drivers/{id}/offer` | | `{"offer", "trip", "estimated_price"}`, or `204` if none. Poll every 2–3 s |
| `POST /offers/{id}/accept` | `{"driver_id"}` | `{"offer", "trip"}` (trip `ASSIGNED`, price fixed) |
| `POST /offers/{id}/reject` | `{"driver_id"}` | Offer |
| `POST /trips/{id}/pickup` · `/complete` | `{"driver_id"}` | Trip |

**Rider app**

| Call | Body | Returns |
|---|---|---|
| `POST /riders` | `{"name"}` | `201` the new Rider |
| `POST /trips` | `{"rider_id", "pickup", "dropoff"}` | `201` Trip: already `OFFERED` if a driver was free, otherwise `REQUESTED` |
| `GET /trips/{id}` | | Trip. Poll every 2–3 s to follow progress |
| `GET /drivers/{id}` | | Driver, including position, to show the driver approaching |
| `POST /trips/{id}/cancel` | `{"rider_id"}` | Trip. Allowed until pickup |

**Dashboard, MCP, agent**

| Call | Body | Returns |
|---|---|---|
| `GET /zones` | | list of Zone |
| `GET /drivers?status=` | | list of Driver (`status` optional) |
| `GET /trips?status=&zone=&limit=` | | list of Trip, newest first (`limit` 1–200, default 50) |
| `GET /surge` · `GET /incentives` | | what applies right now: at most one per zone, the newest active one |
| `GET /proposals` | | the 50 newest Proposals |
| `POST /proposals` | `{"zone", "reason", "type", "params"}` | Proposal (`pending`) |
| `PATCH /proposals/{id}` | `{"status": "approved" \| "rejected"}` | Proposal. Approving a surge or incentive creates the rule straight away |
| `GET /observations` | | as today. **Deprecated**: kept until the stats worker replaces it |
| `GET /stats/zones?from=&to=&bucket=&zone=` | | Trip, wait and offer figures per zone and time bucket (below) |
| `GET /stats/flows?from=&to=` | | Trips per pickup zone → dropoff zone, all 9 pairs |
| `GET /stats/supply` | | Drivers per zone right now: `available`, `offered`, `on_trip`, `stale`, plus `waiting_trips` |

**Stats rules** (read-only, used by the MCP server and agent):
- `from`/`to`: ISO-8601 with an offset (`2026-11-03T08:00:00Z`; encode `+` as `%2B`). Default: the last 24 hours. `to` after now is cut at now. At most 7 days.
- `bucket`: `15m`, `1h` (default), `6h` or `1d`, aligned to UTC. Every zone × bucket is listed, with zeros if empty.
- A trip counts in the bucket of its `requested_at`, in its pickup zone. `arrivals` are completed trips whose **dropoff** is in the zone (nearest center, like pickup). Statuses are current, so a trip still underway counts in `open`.
- Rates (`unmatched_rate`, `cancel_rate`, `offer_reject_rate`, `offer_expiry_rate`) and `avg_wait_s`/`p90_wait_s` (`assigned_at − requested_at`) are `null` when there is nothing to divide by.
- `/stats/supply` is a snapshot: driver history isn't stored. `available` counts only AVAILABLE drivers with a position newer than `position_max_age_seconds` (the ones dispatch can use). `stale` counts AVAILABLE drivers without one.
- Errors: `400 invalid_request` (bad time, window, bucket), `400 unknown_zone`.

**Proposal rules:**
- `type` and `params` are optional. Without them, approving only records the decision.
- `surge`: `params` = `{"multiplier": 1.0–3.0, "starts_at", "ends_at"}`.
- `incentive`: `params` = `{"bonus_per_trip": 0–20, "starts_at", "ends_at"}`.
- Amounts have at most 2 decimals, and `ends_at` must be after `starts_at` and in the future.
- The incentive is a bonus for drivers: it doesn't change the rider's price.

## Events (RabbitMQ)

Exchange `unter.events` (topic). The routing key is the event `kind`. Each message:

```json
{"id": "<event id>", "kind": "trip.assigned", "data": { … }}
```

Events arrive in the order they happened, within a second or two. They can arrive **more than once**: skip ids you've already seen.

| `kind` | `data` |
|---|---|
| `trip.requested` · `trip.assigned` · `trip.picked_up` · `trip.completed` · `trip.cancelled` · `trip.unmatched` | `{"trip"}`, the full Trip after the change |
| `trip.offered` · `trip.offer_rejected` · `trip.offer_expired` | `{"trip", "offer"}`. `offer_rejected` also covers a driver going offline |
| `driver.created` · `driver.status_changed` | `{"driver", "previous_status"}` |
| `driver.zone_changed` | `{"driver", "previous_zone"}`. Sent only when a driver moves into another zone, not on every position update |
| `surge.changed` · `incentive.changed` | `{"surge_rule"}` / `{"incentive"}` |
| `proposal.created` | the Proposal itself |
| `report.ready` | Published by the **agent**, not core, from its own outbox (same envelope). The whole report plus `report_id`, `run_id`, `source` (`manual`/`schedule`) and `recipients`. See [surge-incentive-agent-plan.md](surge-incentive-agent-plan.md) |
| `proposal.decided` | `{"proposal"}` |

Every event carries everything needed to process it, so consumers never have to call `core` back. For example, wait time is `assigned_at − requested_at` on the trip, and driver supply per zone comes from `driver.*` events.

**Subscribing:**
- **Your own queue:** declare a durable queue for your service, bound to `unter.events` with the routing keys you need (e.g. `trip.*`, `driver.*`, or `#` for everything). Don't read from `unter.activity`: that's the worker's queue, and sharing it would take messages away from it.
- **No history:** RabbitMQ only delivers events published after your queue exists. While your service is down, a durable queue keeps them for you. For anything older, read the current state from the REST endpoints.
- **Access:** in the cluster only `core`, the worker, the agent (publishes `report.ready`) and the mailer (consumes it) may connect to RabbitMQ today. A new consumer needs a network-policy entry, a manifest and the RabbitMQ credentials (ask Andy). RabbitMQ isn't reachable from outside the cluster, so apps poll the REST endpoints instead.
