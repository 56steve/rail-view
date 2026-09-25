import { create } from "zustand";
import { type RouteLanes, routeLanes } from "./lanes";
import type { LiveSnapshot } from "./liveWire";
import { nextPair, SnapshotRhythm } from "./motion";
import { TrackPath } from "./track";
import type {
  ConnectionStatus,
  LineOut,
  NetworkOut,
  RouteOut,
  StationIndexEntry,
  TrainPositionUpdate,
} from "./types";

export type TabName = "explore" | "trains" | "saved" | "more";

/** What the user picked; "auto" follows the real sun over Mumbai. */
export type Appearance = "auto" | "day" | "night";
export type SceneMode = "day" | "night";

export interface SceneLighting {
  mode: SceneMode;
  /** Unit vector from the ground towards the sun, in scene space. */
  sunDirection: [number, number, number];
  sunElevationDeg: number;
}

export type Screen =
  | { name: TabName }
  | { name: "follow"; trainId: string }
  | { name: "train"; trainId: string }
  | { name: "journey"; fromId: string | null; toId: string | null };

export interface TrainSnapshotPair {
  from: TrainPositionUpdate;
  to: TrainPositionUpdate;
  receivedAtMs: number;
  /** How long the train takes to glide from `from` to `to`. */
  glideMs: number;
}

export interface SavedJourney {
  fromId: string;
  toId: string;
}

export interface ArrivalAlert {
  id: string;
  trainId: string;
  stationCode: string;
  stationName: string;
  leadSeconds: number;
  createdAtMs: number;
}

export interface Toast {
  id: string;
  title: string;
  body: string;
  tone: "info" | "success" | "warning";
}

export type CameraRequest =
  | { kind: "frame-network"; lineCode: string | null }
  | { kind: "frame-points"; points: { x: number; z: number }[] }
  | { kind: "focus-point"; x: number; z: number; distance: number }
  | { kind: "recenter-follow" };

/** Screen pixels of the map covered by UI on each side. */
export interface ViewInsets {
  left: number;
  top: number;
  bottom: number;
}

interface RailViewState {
  network: NetworkOut | null;
  /** Keyed by line code (WR, CR...): name and colour. */
  lines: Record<string, LineOut>;
  /** Keyed by route id (CR-KSRA...). */
  routes: Record<string, RouteOut>;
  /** Route centrelines, keyed by route id - what train chainages index. */
  tracks: Record<string, TrackPath>;
  /** Each route's per-direction running tracks, keyed by route id. */
  lanes: Record<string, RouteLanes>;
  stations: StationIndexEntry[];
  trainPairs: Record<string, TrainSnapshotPair>;
  connectionStatus: ConnectionStatus;

  stack: Screen[];
  lineFilter: string | null;
  view2D: boolean;
  showBuildings: boolean;
  showLabels: boolean;
  appearance: Appearance;
  lighting: SceneLighting;
  savedTrainIds: string[];
  savedJourneys: SavedJourney[];
  alerts: ArrivalAlert[];
  toasts: Toast[];
  cameraRequest: { seq: number; request: CameraRequest } | null;
  focusedStationId: string | null;
  viewInsets: ViewInsets;

  setNetwork: (network: NetworkOut) => void;
  setStations: (stations: StationIndexEntry[]) => void;
  applySnapshot: (snapshot: LiveSnapshot) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;

  openTab: (tab: TabName) => void;
  push: (screen: Screen) => void;
  pop: () => void;
  replaceTop: (screen: Screen) => void;

  setLineFilter: (lineCode: string | null) => void;
  setView2D: (value: boolean) => void;
  setShowBuildings: (value: boolean) => void;
  setShowLabels: (value: boolean) => void;
  setAppearance: (value: Appearance) => void;
  setLighting: (lighting: SceneLighting) => void;
  toggleSavedTrain: (trainId: string) => void;
  toggleSavedJourney: (journey: SavedJourney) => void;
  addAlert: (alert: Omit<ArrivalAlert, "id" | "createdAtMs">) => void;
  removeAlert: (id: string) => void;
  pushToast: (toast: Omit<Toast, "id">) => void;
  dismissToast: (id: string) => void;
  requestCamera: (request: CameraRequest) => void;
  focusStation: (stationId: string | null) => void;
  setViewInsets: (insets: Partial<ViewInsets>) => void;
  hydratePreferences: (prefs: Partial<Pick<RailViewState, PreferenceKey>>) => void;
}

export type PreferenceKey =
  | "showBuildings"
  | "showLabels"
  | "appearance"
  | "savedTrainIds"
  | "savedJourneys"
  | "alerts";

const snapshotRhythm = new SnapshotRhythm();

let idCounter = 0;
function nextId(prefix: string): string {
  idCounter += 1;
  return `${prefix}-${Date.now().toString(36)}-${idCounter}`;
}

export const useRailView = create<RailViewState>((set, get) => ({
  network: null,
  lines: {},
  routes: {},
  tracks: {},
  lanes: {},
  stations: [],
  trainPairs: {},
  connectionStatus: "connecting",

  stack: [{ name: "explore" }],
  lineFilter: null,
  view2D: false,
  showBuildings: true,
  showLabels: true,
  appearance: "auto",
  lighting: { mode: "night", sunDirection: [0, 1, 0], sunElevationDeg: -90 },
  savedTrainIds: [],
  savedJourneys: [],
  alerts: [],
  toasts: [],
  cameraRequest: null,
  focusedStationId: null,
  viewInsets: { left: 0, top: 0, bottom: 0 },

  setNetwork: (network) =>
    set({
      network,
      lines: Object.fromEntries(network.lines.map((l) => [l.code, l])),
      routes: Object.fromEntries(network.routes.map((r) => [r.route_id, r])),
      tracks: Object.fromEntries(network.routes.map((r) => [r.route_id, new TrackPath(r.polyline)])),
      lanes: Object.fromEntries(network.routes.map((r) => [r.route_id, routeLanes(r)])),
    }),

  setStations: (stations) => set({ stations }),

  applySnapshot: (snapshot) =>
    set((state) => {
      const now = performance.now();
      const glideMs = snapshotRhythm.arrived(now);
      const next: Record<string, TrainSnapshotPair> = {};
      if (snapshot.kind === "full") {
        for (const train of snapshot.trains) {
          next[train.train_id] = nextPair(state.trainPairs[train.train_id], train, now, glideMs);
        }
      } else {
        // Only trains already known move on; one that has just started
        // appears with the next full snapshot.
        for (const update of snapshot.trains) {
          const previous = state.trainPairs[update.train_id];
          if (previous) next[update.train_id] = nextPair(previous, { ...previous.to, ...update }, now, glideMs);
        }
      }
      return { trainPairs: next };
    }),

  setConnectionStatus: (connectionStatus) => set({ connectionStatus }),

  openTab: (tab) => set({ stack: [{ name: tab }], view2D: false }),
  push: (screen) => set((state) => ({ stack: [...state.stack, screen] })),
  pop: () => set((state) => (state.stack.length > 1 ? { stack: state.stack.slice(0, -1) } : state)),
  replaceTop: (screen) => set((state) => ({ stack: [...state.stack.slice(0, -1), screen] })),

  setLineFilter: (lineFilter) => {
    set({ lineFilter });
    get().requestCamera({ kind: "frame-network", lineCode: lineFilter });
  },
  setView2D: (view2D) => set({ view2D }),
  setShowBuildings: (showBuildings) => set({ showBuildings }),
  setShowLabels: (showLabels) => set({ showLabels }),
  setAppearance: (appearance) => set({ appearance }),
  setLighting: (lighting) => set({ lighting }),

  toggleSavedTrain: (trainId) =>
    set((state) => ({
      savedTrainIds: state.savedTrainIds.includes(trainId)
        ? state.savedTrainIds.filter((id) => id !== trainId)
        : [...state.savedTrainIds, trainId],
    })),

  toggleSavedJourney: (journey) =>
    set((state) => {
      const exists = state.savedJourneys.some((j) => j.fromId === journey.fromId && j.toId === journey.toId);
      return {
        savedJourneys: exists
          ? state.savedJourneys.filter((j) => !(j.fromId === journey.fromId && j.toId === journey.toId))
          : [...state.savedJourneys, journey],
      };
    }),

  addAlert: (alert) =>
    set((state) => ({
      alerts: [
        ...state.alerts.filter((a) => !(a.trainId === alert.trainId && a.stationCode === alert.stationCode)),
        { ...alert, id: nextId("alert"), createdAtMs: Date.now() },
      ],
    })),
  removeAlert: (id) => set((state) => ({ alerts: state.alerts.filter((a) => a.id !== id) })),

  pushToast: (toast) => set((state) => ({ toasts: [...state.toasts.slice(-2), { ...toast, id: nextId("toast") }] })),
  dismissToast: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),

  requestCamera: (request) =>
    set((state) => ({ cameraRequest: { seq: (state.cameraRequest?.seq ?? 0) + 1, request } })),

  focusStation: (focusedStationId) => set({ focusedStationId }),
  setViewInsets: (partial) =>
    set((state) => {
      const next = { ...state.viewInsets, ...partial };
      const unchanged =
        next.left === state.viewInsets.left &&
        next.top === state.viewInsets.top &&
        next.bottom === state.viewInsets.bottom;
      return unchanged ? state : { viewInsets: next };
    }),

  hydratePreferences: (prefs) => set(prefs),
}));

export function currentScreen(state: Pick<RailViewState, "stack">): Screen {
  return state.stack[state.stack.length - 1]!;
}

/** The train the camera and panels are focused on, if any. */
export function focusedTrainId(state: Pick<RailViewState, "stack">): string | null {
  const screen = currentScreen(state);
  return screen.name === "follow" || screen.name === "train" ? screen.trainId : null;
}
