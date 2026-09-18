import { create } from "zustand";
import type { ConnectionStatus, RouteOut, TrainPositionUpdate, ViewMode } from "./types";

export interface TrainSnapshotPair {
  from: TrainPositionUpdate;
  to: TrainPositionUpdate;
  toReceivedAtMs: number;
}

interface RailPulseState {
  route: RouteOut | null;
  trainPairs: Record<string, TrainSnapshotPair>;
  selectedTrainId: string | null;
  viewMode: ViewMode;
  connectionStatus: ConnectionStatus;
  followSelected: boolean;

  setRoute: (route: RouteOut) => void;
  applySnapshot: (trains: TrainPositionUpdate[]) => void;
  selectTrain: (trainId: string | null) => void;
  setViewMode: (mode: ViewMode) => void;
  setConnectionStatus: (status: ConnectionStatus) => void;
  setFollowSelected: (value: boolean) => void;
}

export const useRailPulseStore = create<RailPulseState>((set) => ({
  route: null,
  trainPairs: {},
  selectedTrainId: null,
  viewMode: "network",
  connectionStatus: "connecting",
  followSelected: false,

  setRoute: (route) => set({ route }),

  applySnapshot: (trains) =>
    set((state) => {
      const now = performance.now();
      const next = { ...state.trainPairs };
      for (const train of trains) {
        const existing = next[train.train_id];
        next[train.train_id] = {
          from: existing ? existing.to : train,
          to: train,
          toReceivedAtMs: now,
        };
      }
      return { trainPairs: next };
    }),

  selectTrain: (trainId) =>
    set({
      selectedTrainId: trainId,
      followSelected: trainId !== null,
      viewMode: trainId !== null ? "journey" : "network",
    }),

  setViewMode: (mode) =>
    set((state) => ({
      viewMode: mode,
      followSelected: mode === "journey" ? state.followSelected : false,
      selectedTrainId: mode === "network" ? null : state.selectedTrainId,
    })),

  setConnectionStatus: (status) => set({ connectionStatus: status }),

  setFollowSelected: (value) => set({ followSelected: value }),
}));
