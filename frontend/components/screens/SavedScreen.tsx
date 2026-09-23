"use client";

import { ArrowRight, Bell, BellOff, Star } from "lucide-react";
import { navigate } from "@/lib/navigation";
import { useRailView } from "@/lib/store";
import { PanelScreen } from "../ui/PanelScreen";
import { EmptyState, SectionTitle } from "../ui/primitives";
import { TrainRow } from "../ui/TrainRow";

export function SavedScreen() {
  const savedTrainIds = useRailView((s) => s.savedTrainIds);
  const savedJourneys = useRailView((s) => s.savedJourneys);
  const alerts = useRailView((s) => s.alerts);
  const trainPairs = useRailView((s) => s.trainPairs);
  const lines = useRailView((s) => s.lines);
  const stations = useRailView((s) => s.stations);
  const nameOf = (id: string) => stations.find((s) => s.id === id)?.name ?? id;

  const nothingSaved = savedTrainIds.length === 0 && savedJourneys.length === 0 && alerts.length === 0;

  return (
    <PanelScreen title="Saved" subtitle="Trains, journeys and alerts on this device">
      {nothingSaved && (
        <EmptyState
          title="Nothing saved yet"
          body="Tap the star on a train or a journey to keep it here, or set an alert to be told before your train arrives."
        />
      )}

      {savedJourneys.length > 0 && (
        <section className="flex flex-col gap-2.5">
          <SectionTitle>Journeys</SectionTitle>
          {savedJourneys.map((journey) => (
            <button
              key={`${journey.fromId}-${journey.toId}`}
              type="button"
              onClick={() => navigate({ name: "journey", fromId: journey.fromId, toId: journey.toId })}
              className="flex items-center gap-3 rounded-2xl border hairline bg-ink-800 px-4 py-3.5 text-left transition hover:bg-ink-750"
            >
              <span className="flex flex-1 items-center gap-2 text-[15px] font-medium text-fg">
                {nameOf(journey.fromId)}
                <ArrowRight className="h-4 w-4 text-fg-subtle" />
                {nameOf(journey.toId)}
              </span>
              <Star className="h-4 w-4 fill-warning text-warning" />
            </button>
          ))}
        </section>
      )}

      {savedTrainIds.length > 0 && (
        <section className="mt-6 flex flex-col gap-2.5">
          <SectionTitle>Trains</SectionTitle>
          {savedTrainIds.map((id) => {
            const train = trainPairs[id]?.to;
            return train ? (
              <TrainRow key={id} train={train} color={lines[train.line_code]?.color_hex ?? "#888"} />
            ) : (
              <div key={id} className="flex items-center justify-between rounded-2xl border hairline bg-ink-800 px-4 py-3.5">
                <span className="text-[14px] text-fg-muted">{id} isn&apos;t running right now</span>
                <button
                  type="button"
                  onClick={() => useRailView.getState().toggleSavedTrain(id)}
                  className="text-[13px] text-fg-subtle hover:text-fg"
                >
                  Remove
                </button>
              </div>
            );
          })}
        </section>
      )}

      {alerts.length > 0 && (
        <section className="mt-6 flex flex-col gap-2.5">
          <SectionTitle>Alerts</SectionTitle>
          {alerts.map((alert) => (
            <div key={alert.id} className="flex items-center gap-3 rounded-2xl border hairline bg-ink-800 px-4 py-3.5">
              <Bell className="h-4 w-4 text-primary" />
              <span className="flex-1 text-[14px] text-fg">
                {alert.trainId} <span className="text-fg-muted">before</span> {alert.stationName}
              </span>
              <button
                type="button"
                aria-label={`Cancel alert for ${alert.stationName}`}
                onClick={() => useRailView.getState().removeAlert(alert.id)}
                className="text-fg-subtle hover:text-fg"
              >
                <BellOff className="h-4 w-4" />
              </button>
            </div>
          ))}
        </section>
      )}
    </PanelScreen>
  );
}
