# RailPulse

Real-time 3D tracking for Mumbai's suburban local trains. MVP scope: the
Central Line's Thane&harr;Dadar corridor, with simulated (not live) train
telemetry running through the same pipeline a real feed would use.

The 3D view isn't decoration — it's how you tell where your train is, how
far it is from a station, and whether it's on time. Camera, track
geometry, and train positions all come from the same rail-relative
coordinate system end to end (backend chainage &rarr; WebSocket &rarr;
client scene), so nothing is faked for visual effect except the physical
size of the train model (see `frontend/components/three/TrainMesh.tsx`).

## Architecture

```
Telemetry source (simulator today, authorized railway API later)
        |  raw, noisy GPS fixes
        v
Position processor  --  snaps each fix onto the track (GPS-to-track
        |                matching), derives speed/direction from
        |                consecutive chainage deltas, enriches with
        |                schedule (current/next station, ETA, delay)
        v
Live train cache  --  last-known position per train; marks a train
        |              "stale" instead of inventing a new position
        |              when its telemetry goes quiet
        v
WebSocket hub  --  one broadcast reaches every connected client
        v
Next.js client  --  interpolates motion between snapshots, converts
                     lat/lon to scene coordinates, renders the 3D map
```

PostGIS holds the *static* network topology (stations, tracks, segments,
schedules) — not live positions. Live positions stay in memory and go out
over the WebSocket; writing every tick of every train to Postgres would
be the "excessive load" the product spec explicitly says to avoid. See
`backend/app/models/train.py:TrainPosition` for where periodic history
*would* be persisted for analytics/replay.

### Backend (`backend/`)

- **`app/services/geometry.py`** — WGS84 &harr; local planar metres
  (equirectangular approximation around a fixed origin). Mirrored exactly
  in `frontend/lib/geo.ts` so a position computed server-side lands in the
  same spot in the 3D scene.
- **`app/services/track_matching.py`** — builds the route as a Shapely
  `LineString` in local metres; `RailwayRoute.match()` projects a raw
  GPS fix onto it and returns chainage (distance along the route),
  snapped lat/lon, and how far off the rail the raw fix was.
- **`app/services/simulator/`** — `SimulatedTelemetrySource` runs a
  trapezoidal accel/cruise/brake physics model per train and emits
  *noisy* GPS fixes (positional jitter + occasional dropped fixes) — it
  does not hand the processor a clean answer. `schedule.py` builds a
  timetable per train type/direction that the processor compares actual
  progress against, which is how delay is computed (not a random number).
- **`app/services/position_processor.py`** — the pipeline's middle:
  match &rarr; reject implausible fixes &rarr; derive speed/direction
  from chainage deltas &rarr; enrich with schedule &rarr;
  `TrainPositionUpdate`.
- **`app/services/telemetry.py`** — the `TelemetrySource` /
  `ScheduleProvider` protocols. A future `LiveRailwayApiSource` implements
  the same two protocols; nothing downstream changes.
- **`app/api/ws.py`** — `/ws/live`, one broadcast per tick to every
  connected client.
- **`app/models/`** — the full PostGIS-backed schema (stations,
  railway_lines, railway_tracks, track_segments, stations_on_routes,
  trains, train_runs, train_positions, schedules), with a hand-written
  Alembic migration (`alembic/versions/0001_initial_schema.py`) and a seed
  script (`scripts/seed_db.py`) that loads the same Central Line data the
  simulator uses.

### Frontend (`frontend/`)

- **`lib/geo.ts`** — geographic &rarr; Three.js scene coordinates.
- **`lib/interpolate.ts`** — client-side motion smoothing between the
  last two WebSocket snapshots (the server ticks once a second; without
  this a train would visibly jump instead of glide).
- **`lib/store.ts`** — Zustand store: route geometry, per-train
  from/to snapshot pairs, selection, view mode, connection status.
- **`lib/useLiveTrains.ts`** — owns the WebSocket connection, with
  backoff reconnect. Never clears known trains on disconnect — see
  `components/ui/ConnectionBadge.tsx` / `TrainInfoPanel.tsx`'s "stale"
  state instead.
- **`components/three/`** — `RailwayTrack` (the actual route polyline as
  a tube), `StationMarkers`, `TrainMesh` (procedural EMU model + a
  distance-scaled "beacon" so a train stays legible zoomed out to the
  whole network, not just up close), `CameraRig` (orbit controls +
  auto-framing + follow-selected-train chase cam).

## Known limitations (MVP scope, by design)

- **One route.** Only Central Line Thane&harr;Dadar. `app/data/mumbai_network.py`
  is structured so Western/Harbour/Trans-Harbour lines are additional
  `LineSeed` entries — no other code changes needed to add one, only
  sourcing its station geometry.
- **Approximate track geometry.** Station coordinates are from general
  public geographic knowledge, not a surveyed feed, and the track
  polyline is straight segments between stations, not the true curved
  centerline. Documented in `app/data/mumbai_network.py`; replace with an
  official GTFS feed or OSM `railway=rail` ways before this touches real
  commuters.
- **No live data provider.** There is no public, freely-licensed
  real-time GPS feed for Mumbai suburban trains. `TelemetrySource` /
  `ScheduleProvider` are the seam for plugging one in once you have an
  authorized data partnership (IRCTC/CRIS or a licensed vendor) — nothing
  else in the pipeline needs to change.
- **PostGIS schema exists but isn't wired to the live path.** Migration
  and seed script are written and lint/type-check clean, but weren't run
  against a live Postgres in this environment (no Docker available in
  this session). `docker compose up -d postgres && cd backend && uv run
  alembic upgrade head && uv run python scripts/seed_db.py` should do it
  on a machine with Docker.
- **Dark-first UI only.** No light theme yet; tokens are already CSS
  variables in `app/globals.css` for when that's added.
- **Journey planner is minimal.** Source/destination pick any two
  stations on the one route; there's no multi-route pathfinding since
  there's only one route.

## Running locally

### Backend

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Runs entirely in-memory (simulator + WebSocket hub) — no database
required to see live trains. `uv run pytest` / `uv run ruff check .` for
tests and lint.

### Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Open the printed localhost URL. The client fetches route geometry over
REST once, then live positions over `/ws/live`.

### Full stack with PostGIS/Redis (optional, needs Docker)

```bash
cp .env.example .env
docker compose up -d postgres redis
cd backend && uv run alembic upgrade head && uv run python scripts/seed_db.py
```
