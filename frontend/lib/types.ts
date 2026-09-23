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
  origin: StationOut;
  destination: StationOut;
  current_station: StationOut | null;
  next_station: StationOut | null;
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
  last_updated_iso: string;
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

export interface SnapshotMessage {
  type: "snapshot";
  server_time_epoch: number;
  trains: TrainPositionUpdate[];
}

export type ConnectionStatus = "connecting" | "live" | "reconnecting";
