// Mirrors backend/app/schemas/*.py. Keep in sync by hand; a client
// generated from the FastAPI OpenAPI schema is the natural upgrade once
// the API surface settles.

export interface StationOut {
  code: string;
  name: string;
  lat: number;
  lon: number;
  sequence: number;
  chainage_m: number;
  fast_halt: boolean;
}

/** A station named in a live train position. Codes are unique across the
 * network; the rest of a station's data is in the network's routes. */
export interface StationRef {
  code: string;
  name: string;
}

export interface LineOut {
  code: string;
  name: string;
  color_hex: string;
}

/** One end-to-end path within a line (Central forks at Kalyan into a
 * Kasara route and a Karjat route that share the trunk). */
export interface RouteOut {
  route_id: string;
  line_code: string;
  line_name: string;
  color_hex: string;
  name: string;
  length_m: number;
  origin_name: string;
  destination_name: string;
  stations: StationOut[];
  polyline: [number, number][];
  /** Per direction, [chainage_m, sideways offset_m] breakpoints to the
   * track that direction runs on (positive = left facing increasing
   * chainage; Mumbai runs on the left). */
  running_lanes: { forward: [number, number][]; backward: [number, number][] };
}

export interface NetworkOut {
  attribution: string;
  generated_at: string;
  lines: LineOut[];
  routes: RouteOut[];
}

export interface StationIndexEntry {
  id: string;
  name: string;
  lat: number;
  lon: number;
  lines: string[];
}

export type TrainType = "FAST" | "SLOW";
export type TrainStatus = "live" | "stale";

export interface TrainPositionUpdate {
  /** The train number in the official timetable. */
  train_id: string;
  train_type: TrainType;
  /** Central Railway's service code, e.g. "N 5"; Western doesn't publish them. */
  service_code: string | null;
  ac: boolean;
  line_code: string;
  line_name: string;
  route_code: string;
  coach_count: number;
  origin: StationRef;
  destination: StationRef;
  current_station: StationRef | null;
  next_station: StationRef | null;
  direction_forward: boolean;
  direction_label: string;
  lat: number;
  lon: number;
  heading_deg: number;
  chainage_m: number;
  speed_kmh: number;
  delay_seconds: number;
  eta_seconds: number | null;
  destination_eta_seconds: number;
  status: TrainStatus;
  last_updated_epoch: number;
}

export type StopState = "departed" | "at_platform" | "next" | "upcoming";

export interface StopTime {
  station: StationOut;
  state: StopState;
  scheduled_epoch: number;
  expected_epoch: number;
  observed_arrival_epoch: number | null;
}

export interface TrainDetail {
  position: TrainPositionUpdate;
  stops: StopTime[];
}

export type JourneySort = "fastest" | "soonest";

export interface JourneyOption {
  train_id: string;
  train_type: TrainType;
  service_code: string | null;
  ac: boolean;
  /** Running now (times include its delay); otherwise it hasn't started. */
  is_live: boolean;
  board_scheduled_epoch: number;
  line_code: string;
  line_name: string;
  route_code: string;
  direction_label: string;
  board_expected_epoch: number;
  alight_expected_epoch: number;
  duration_seconds: number;
  delay_seconds: number;
  intermediate_stops: number;
}

export interface JourneyPlan {
  from_station: StationIndexEntry;
  to_station: StationIndexEntry;
  sort: JourneySort;
  options: JourneyOption[];
  interchange_hint: string | null;
}

/** Which timetable the network is running today, in Mumbai. */
export interface ServiceDay {
  date: string;
  sunday_schedule: boolean;
  /** Set when the Sunday schedule is for a holiday rather than a Sunday. */
  holiday_name: string | null;
}

/** One value in a snapshot row: a TrainPositionUpdate field, with station
 * fields reduced to station codes. */
export type SnapshotCell = string | number | boolean | null;

/** One tick of `/ws/live`: every known train as a table. `fields` names
 * the columns, each row of `trains` is one train's values in that order,
 * and station fields hold a code whose name is in `stations`. Decoded by
 * `lib/liveWire.ts`. */
export interface SnapshotTableMessage {
  type: "snapshot.table";
  server_time_epoch: number;
  fields: string[];
  stations: Record<string, string>;
  trains: SnapshotCell[][];
}

export type ConnectionStatus = "connecting" | "live" | "reconnecting";
