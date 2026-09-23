# RailView

Real-time 3D tracking for Mumbai's suburban local trains, built mobile-first.
It covers four lines:

| Line | Routes |
| --- | --- |
| Western | Churchgate – Borivali |
| Central | CSMT – Kasara and CSMT – Karjat (forking at Kalyan) |
| Harbour | CSMT – Vashi |
| Trans-Harbour | Thane – Vashi |

Train movements are **simulated**. They run through the same pipeline a
real feed would use, and no authorised real-time feed for Mumbai locals
is connected yet (see [Live data](#live-data)).

The 3D view shows where your train is, how far it is from the next
station, and whether it's on time. Station positions, track centrelines,
the individual tracks and platforms at every station, buildings and the
coastline all come from OpenStreetMap. Train positions live in the same
rail-relative coordinate system from the backend to the scene.

## How it works

```
Telemetry source (simulator today, authorised railway feed later)
        |  raw, noisy GPS fixes
        v
Position processor   snaps each fix onto the train's route (GPS-to-track
        |            matching), smooths chainage with a Kalman filter to
        |            get speed and direction, and compares progress with
        |            the timetable for current/next station, ETA and delay
        v
Live train cache     last-known state per train; marks a train "stale"
        |            after 15 s of silence instead of inventing positions
        v
WebSocket hub        one snapshot per tick to every client (/ws/live)
        v
Next.js client       interpolates along the track between snapshots and
                     renders trains on the track their direction runs on
```

### Network model

- A **line** (Central, Western...) is what commuters see: a name and a
  colour. A **route** is one end-to-end path trains run on. Central has
  two routes that share the trunk up to Kalyan. Track matching,
  simulation and timetables all work per route.
- **Chainage** (metres along a route from its first station) is how
  every position is addressed on both the server and the client.
- **Left-hand running.** Mumbai runs on the left, so Up trains (towards
  CSMT or Churchgate) and Down trains keep to different tracks. The data
  build measures, every 10 m along each route, the sideways offset to
  each direction's real track. The client draws trains there, and at a
  terminus both directions share the platform track before crossing over.

### Backend (`backend/`, FastAPI)

- `scripts/network_definitions.py`: the curated part of the network:
  which stations each route calls at, their order and fast halts.
- `scripts/build_osm_data.py`: builds everything else from OpenStreetMap
  through the Overpass API. It snaps stations onto the rail graph,
  map-matches each route through that graph, and collects every running
  track and platform near the routes. It also derives each direction's
  running lane, and bakes buildings and land into compact tiles for the
  client. Overpass responses are cached in `backend/.osm-cache/`
  (git-ignored).
- `app/services/track_matching.py`: GPS fix → chainage on a route.
- `app/services/track_filter.py`: constant-velocity Kalman filter over
  chainage.
- `app/services/simulator/`: the simulated feed. Trains follow a shared
  speed profile, dwell times vary, and each rake forms its return working
  after a layover, so delays emerge instead of being made up. GPS fixes
  get jitter and dropouts.
- `app/services/position_processor.py`: the pipeline's middle stage.
- `app/services/journey_planner.py`: direct trains between two stations
  from the live timetable, or where to change (another line, or the
  other Central branch).
- `app/services/telemetry.py`: the `TelemetrySource` / `ScheduleProvider`
  protocols a real feed implements.
- `app/models/` + `alembic/`: the PostGIS schema for the static network
  and timetables (`scripts/seed_db.py` loads it). The live path runs in
  memory and doesn't need a database.

### Frontend (`frontend/`, Next.js + React Three Fiber)

- `lib/geo.ts` mirrors the backend projection exactly.
- `lib/track.ts` addresses a route by chainage, and `lib/lanes.ts` offsets
  a chainage onto the direction's running track.
- `lib/motion.ts` interpolates between snapshots along the track.
- `components/three/` holds the scene: ground and coastline, building
  tiles, individual tracks and platforms, route lines, and trains. Trains
  are a true-scale 12-coach rake up close and a legible glyph from far
  away. The camera rig handles network framing, following a train and 2D.
- `components/screens/` holds the app screens: Explore, Follow, Train
  details, Plan journey, Trains, Saved, More.

## Running locally

Backend (in-memory, no database needed):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev -- --port 3010
```

Checks: `uv run ruff check . && uv run pytest` in `backend/`;
`npm run lint && npx tsc --noEmit && npm run build` in `frontend/`.

### Rebuilding the map data

```bash
cd backend
uv run python scripts/build_osm_data.py            # uses the local Overpass cache
uv run python scripts/build_osm_data.py --refresh  # refetches from OpenStreetMap
```

This regenerates `backend/app/data/generated/network.json` and
`frontend/public/city/*`. Both are committed, so you don't need to run
it just to work on the app.

### Database (optional)

With a PostGIS database reachable at `DATABASE_URL`:

```bash
cd backend
uv run alembic upgrade head
uv run python scripts/seed_db.py
```

## Live data

There is no public, freely licensed real-time GPS feed for Mumbai locals.
A live source plugs in by implementing `TelemetrySource` and
`ScheduleProvider`; nothing downstream changes. Real timetables (for
example the m-Indicator schedule) will replace the simulator's generated
timetable.

## Attribution

Map data © OpenStreetMap contributors, available under the
[ODbL](https://www.openstreetmap.org/copyright).
