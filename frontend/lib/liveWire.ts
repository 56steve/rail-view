// Decodes `/ws/live` snapshots. The server sends every train as a row of
// values under one list of field names, with station names listed once
// (see backend/app/services/live_wire.py): a fifth of the size of plain
// objects, which matters when a phone receives one every second.

import type { SnapshotCell, SnapshotTableMessage, StationRef, TrainPositionUpdate } from "./types";

type TrainField = keyof TrainPositionUpdate;

const TRAIN_FIELDS = [
  "train_id",
  "train_type",
  "service_code",
  "ac",
  "line_code",
  "line_name",
  "route_code",
  "coach_count",
  "origin",
  "destination",
  "current_station",
  "next_station",
  "direction_forward",
  "direction_label",
  "lat",
  "lon",
  "heading_deg",
  "chainage_m",
  "speed_kmh",
  "delay_seconds",
  "eta_seconds",
  "destination_eta_seconds",
  "status",
  "last_updated_epoch",
] as const satisfies readonly TrainField[];

// Compile-time check that every TrainPositionUpdate field is decoded.
type UndecodedField = Exclude<TrainField, (typeof TRAIN_FIELDS)[number]>;
const everyFieldDecoded: [UndecodedField] extends [never] ? true : never = true;
void everyFieldDecoded;

const STATION_FIELDS: ReadonlySet<TrainField> = new Set(["origin", "destination", "current_station", "next_station"]);

export class SnapshotDecodeError extends Error {
  constructor(message: string) {
    super(`Malformed live snapshot: ${message}`);
    this.name = "SnapshotDecodeError";
  }
}

function isSnapshotTable(value: unknown): value is SnapshotTableMessage {
  if (typeof value !== "object" || value === null) return false;
  const message = value as Partial<SnapshotTableMessage>;
  return (
    message.type === "snapshot.table" &&
    Array.isArray(message.fields) &&
    Array.isArray(message.trains) &&
    typeof message.stations === "object" &&
    message.stations !== null
  );
}

/**
 * The trains in a `/ws/live` message, or `null` for a message that isn't a
 * snapshot. Throws SnapshotDecodeError when a snapshot doesn't match the
 * fields this client knows.
 */
export function decodeSnapshot(message: unknown): TrainPositionUpdate[] | null {
  if (!isSnapshotTable(message)) return null;

  const columns = TRAIN_FIELDS.map((field) => {
    const index = message.fields.indexOf(field);
    if (index < 0) throw new SnapshotDecodeError(`no "${field}" column`);
    return [field, index] as const;
  });

  const station = (cell: SnapshotCell): StationRef | null => {
    if (cell === null) return null;
    if (typeof cell !== "string") throw new SnapshotDecodeError(`station ${String(cell)} isn't a code`);
    const name = message.stations[cell];
    if (name === undefined) throw new SnapshotDecodeError(`station ${cell} isn't listed`);
    return { code: cell, name };
  };

  return message.trains.map((row) => {
    if (!Array.isArray(row) || row.length !== message.fields.length) {
      throw new SnapshotDecodeError("a row doesn't match the columns");
    }
    const train: Record<string, SnapshotCell | StationRef | null> = {};
    for (const [field, index] of columns) {
      const cell = row[index] ?? null;
      train[field] = STATION_FIELDS.has(field) ? station(cell) : cell;
    }
    return train as unknown as TrainPositionUpdate;
  });
}
