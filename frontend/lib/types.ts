// Mirrors backend/app/schemas/*.py exactly. Keep these two in sync by hand
// for the MVP; a generated client (e.g. from the FastAPI OpenAPI schema)
// is the natural upgrade once the API surface stabilizes.

export interface StationOut {
  code: string;
  name: string;
  lat: number;
  lon: number;
  sequence: number;
  chainage_m: number;
}

export interface RouteOut {
  route_id: string;
  line_code: string;
  line_name: string;
  color_hex: string;
  length_m: number;
  origin_name: string;
  destination_name: string;
  stations: StationOut[];
  polyline: [number, number][];
}

export type TrainType = "FAST" | "SLOW";
export type TrainStatus = "live" | "stale";

export interface TrainPositionUpdate {
  train_id: string;
  train_type: TrainType;
  line_code: string;
  line_name: string;
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
  status: TrainStatus;
  last_updated_epoch: number;
  last_updated_iso: string;
}

export interface SnapshotMessage {
  type: "snapshot";
  server_time_epoch: number;
  trains: TrainPositionUpdate[];
}

export type ConnectionStatus = "connecting" | "live" | "reconnecting";
export type ViewMode = "journey" | "network";
