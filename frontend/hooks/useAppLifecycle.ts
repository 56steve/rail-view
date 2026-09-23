"use client";

import { useEffect } from "react";
import { handlePopState } from "@/lib/navigation";
import { readStored, writeStored } from "@/lib/persist";
import { useRailView, type ArrivalAlert, type SavedJourney } from "@/lib/store";

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null;
const isBoolean = (v: unknown): v is boolean => typeof v === "boolean";
const isStringArray = (v: unknown): v is string[] => Array.isArray(v) && v.every((x) => typeof x === "string");
const isJourneyArray = (v: unknown): v is SavedJourney[] =>
  Array.isArray(v) && v.every((x) => isRecord(x) && typeof x.fromId === "string" && typeof x.toId === "string");
const isAlertArray = (v: unknown): v is ArrivalAlert[] =>
  Array.isArray(v) &&
  v.every(
    (x) =>
      isRecord(x) &&
      typeof x.id === "string" &&
      typeof x.trainId === "string" &&
      typeof x.stationCode === "string" &&
      typeof x.stationName === "string" &&
      typeof x.leadSeconds === "number" &&
      typeof x.createdAtMs === "number",
  );

/** Browser-history navigation plus per-device preference persistence. */
export function useAppLifecycle(): void {
  useEffect(() => {
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    useRailView.getState().hydratePreferences({
      showBuildings: readStored("showBuildings", true, isBoolean),
      showLabels: readStored("showLabels", true, isBoolean),
      savedTrainIds: readStored("savedTrainIds", [], isStringArray),
      savedJourneys: readStored("savedJourneys", [], isJourneyArray),
      alerts: readStored("alerts", [], isAlertArray),
    });

    return useRailView.subscribe((state, previous) => {
      if (state.showBuildings !== previous.showBuildings) writeStored("showBuildings", state.showBuildings);
      if (state.showLabels !== previous.showLabels) writeStored("showLabels", state.showLabels);
      if (state.savedTrainIds !== previous.savedTrainIds) writeStored("savedTrainIds", state.savedTrainIds);
      if (state.savedJourneys !== previous.savedJourneys) writeStored("savedJourneys", state.savedJourneys);
      if (state.alerts !== previous.alerts) writeStored("alerts", state.alerts);
    });
  }, []);
}
