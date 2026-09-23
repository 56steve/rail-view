"use client";

import { useAppLifecycle } from "@/hooks/useAppLifecycle";
import { useArrivalAlerts } from "@/hooks/useArrivalAlerts";
import { useDesktopInsets } from "@/hooks/useLayout";
import { useLiveTrains } from "@/hooks/useLiveTrains";
import { useNetworkData } from "@/hooks/useNetworkData";
import { currentScreen, focusedTrainId, useRailView, type Screen } from "@/lib/store";
import { ExploreScreen } from "./screens/ExploreScreen";
import { FollowScreen } from "./screens/FollowScreen";
import { JourneyScreen } from "./screens/JourneyScreen";
import { MoreScreen } from "./screens/MoreScreen";
import { SavedScreen } from "./screens/SavedScreen";
import { TrainDetailsScreen } from "./screens/TrainDetailsScreen";
import { TrainsScreen } from "./screens/TrainsScreen";
import { Scene } from "./three/Scene";
import { LogoMark } from "./ui/Logo";
import { NextStationPin } from "./ui/NextStationPin";
import { StationLabels } from "./ui/StationLabels";
import { TabBar } from "./ui/TabBar";
import { Toasts } from "./ui/Toasts";

const TAB_SCREENS = new Set<Screen["name"]>(["explore", "trains", "saved", "more"]);

export function RailViewApp() {
  useAppLifecycle();
  useLiveTrains();
  useArrivalAlerts();
  useDesktopInsets();
  const { failed } = useNetworkData();
  const screen = useRailView(currentScreen);
  const followedTrain = useRailView(focusedTrainId);
  const networkLoaded = useRailView((s) => s.network !== null);

  return (
    <div className="fixed inset-0 overflow-hidden bg-ink-950">
      <div className="absolute inset-0">
        <Scene />
      </div>
      <StationLabels />
      {followedTrain && <NextStationPin trainId={followedTrain} />}

      <div className="pointer-events-none absolute inset-0 flex">
        <div className="relative flex h-full w-full flex-col md:w-[444px] md:p-3">
          <ScreenView screen={screen} />
          {TAB_SCREENS.has(screen.name) && (
            <div className="shrink-0 md:mt-3">
              <TabBar />
            </div>
          )}
        </div>
      </div>

      {!networkLoaded && <LoadingVeil failed={failed} />}
      <Toasts />
    </div>
  );
}

function ScreenView({ screen }: { screen: Screen }) {
  switch (screen.name) {
    case "explore":
      return <ExploreScreen />;
    case "trains":
      return <TrainsScreen />;
    case "saved":
      return <SavedScreen />;
    case "more":
      return <MoreScreen />;
    case "follow":
      return <FollowScreen trainId={screen.trainId} />;
    case "train":
      return <TrainDetailsScreen trainId={screen.trainId} />;
    case "journey":
      return <JourneyScreen fromId={screen.fromId} toId={screen.toId} />;
  }
}

function LoadingVeil({ failed }: { failed: boolean }) {
  return (
    <div className="absolute inset-0 z-30 flex flex-col items-center justify-center gap-4 bg-ink-950">
      <LogoMark className="h-12 w-12 animate-soft-pulse" />
      <p className="text-[14px] text-fg-muted">
        {failed ? "Can't reach RailView right now — retrying…" : "Loading the network…"}
      </p>
    </div>
  );
}
