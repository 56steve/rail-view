import { deflateRawSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { decodeSnapshot, inflateMessage, SnapshotDecodeError } from "./liveWire";
import type { SnapshotTableMessage } from "./types";

const FULL_FIELDS = [
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
  "chainage_m",
  "speed_kmh",
  "delay_seconds",
  "eta_seconds",
  "destination_eta_seconds",
  "status",
  "last_updated_epoch",
  "next_platform",
  "next_platform_certain",
  "next_platform_door",
];

const FULL_ROW = [
  "90001", "SLOW", null, false, "WR", "Western", "WR-VR", 12, "CCG", "VR", null, "MEL",
  true, "Churchgate → Virar", 1200.5, 42.1, 30, 55, 3600, "live", 1790000000.25, "2", true, "right",
];

// A server from before platforms: the full table without their columns.
const PLATFORM_COLUMNS = 3;
const OLDER_FIELDS = FULL_FIELDS.slice(0, -PLATFORM_COLUMNS);
const OLDER_ROW = FULL_ROW.slice(0, -PLATFORM_COLUMNS);

function table(overrides: Partial<SnapshotTableMessage>): SnapshotTableMessage {
  return {
    type: "snapshot.table",
    server_time_epoch: 1790000000,
    fields: FULL_FIELDS,
    stations: { CCG: "Churchgate", VR: "Virar", MEL: "Marine Lines" },
    trains: [FULL_ROW],
    ...overrides,
  };
}

describe("decodeSnapshot", () => {
  it("decodes a full table into trains", () => {
    const snapshot = decodeSnapshot(table({ full: true }));
    expect(snapshot?.kind).toBe("full");
    const [train] = snapshot!.kind === "full" ? snapshot!.trains : [];
    expect(train).toMatchObject({
      train_id: "90001",
      origin: { code: "CCG", name: "Churchgate" },
      next_station: { code: "MEL", name: "Marine Lines" },
      chainage_m: 1200.5,
      next_platform: "2",
      next_platform_certain: true,
      next_platform_door: "right",
    });
  });

  it("decodes a full table from a server without platforms, with no platform", () => {
    const snapshot = decodeSnapshot(table({ full: true, fields: OLDER_FIELDS, trains: [OLDER_ROW] }));
    expect(snapshot?.kind).toBe("full");
    expect(snapshot?.trains[0]).toMatchObject({
      train_id: "90001",
      next_platform: null,
      next_platform_certain: false,
      next_platform_door: null,
    });
  });

  it("treats a table without the flag as full, and ignores columns it doesn't use", () => {
    const fields = [...FULL_FIELDS, "lat", "lon", "heading_deg"];
    const snapshot = decodeSnapshot(table({ fields, trains: [[...FULL_ROW, 18.9, 72.8, 10]] }));
    expect(snapshot?.kind).toBe("full");
    expect(snapshot?.trains[0]).not.toHaveProperty("lat");
  });

  it("decodes a moving-parts table into partial updates", () => {
    const fields = ["train_id", "current_station", "next_station", "chainage_m", "status"];
    const snapshot = decodeSnapshot(
      table({ full: false, fields, stations: { MEL: "Marine Lines" }, trains: [["90001", null, "MEL", 1300, "live"]] }),
    );
    expect(snapshot).toEqual({
      kind: "moving",
      trains: [
        { train_id: "90001", current_station: null, next_station: { code: "MEL", name: "Marine Lines" }, chainage_m: 1300, status: "live" },
      ],
    });
  });

  it("updates the next platform from a moving-parts table", () => {
    const fields = ["train_id", "next_station", "next_platform", "next_platform_certain", "next_platform_door"];
    const snapshot = decodeSnapshot(
      table({ full: false, fields, stations: { MEL: "Marine Lines" }, trains: [["90001", "MEL", "5,6,7", false, null]] }),
    );
    expect(snapshot).toEqual({
      kind: "moving",
      trains: [
        {
          train_id: "90001",
          next_station: { code: "MEL", name: "Marine Lines" },
          next_platform: "5,6,7",
          next_platform_certain: false,
          next_platform_door: null,
        },
      ],
    });
  });

  it("rejects a full table missing a column", () => {
    expect(() => decodeSnapshot(table({ fields: FULL_FIELDS.slice(1), trains: [FULL_ROW.slice(1)] }))).toThrow(
      SnapshotDecodeError,
    );
  });

  it("ignores messages that aren't snapshots", () => {
    expect(decodeSnapshot({ type: "hello" })).toBeNull();
  });
});

describe("inflateMessage", () => {
  it("reads the server's raw-deflate frames", async () => {
    const text = JSON.stringify(table({ full: true }));
    const frame = new Uint8Array(deflateRawSync(Buffer.from(text))).buffer;
    expect(await inflateMessage(frame)).toBe(text);
  });

  it("passes text frames through", async () => {
    expect(await inflateMessage('{"a":1}')).toBe('{"a":1}');
  });
});
