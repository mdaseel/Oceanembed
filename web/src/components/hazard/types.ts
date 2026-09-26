import type { ReactNode } from "react";
import type { MapLayer, Selection } from "../../field/contract";
import type { ReplayData } from "../../field/replayAdapter";

/** "support" is the Phase 7D thermal-support category map; the rest are App layers. */
export type HazardLayer = MapLayer | "support";

/**
 * How the dashboard borrows the App's ONE map / 3D / profile. The App renders
 * the panel; the dashboard only chooses the layer and adds overlays, so there
 * is still a single MapView and a single DepthRenderer in the application.
 */
export interface MapPanelOptions {
  layer: HazardLayer;
  threeD: boolean;
  setThreeD: (value: boolean) => void;
  eyebrow?: string;
  title?: string;
  headerExtra?: ReactNode;
  /** Drawn over the 2D map only, in the shared map projection. */
  overlay?: ReactNode;
  /** The thermal-support category canvas, used when `layer` is "support". */
  supportMap?: ReactNode;
}
export type RenderMapPanel = (
  source: ReplayData,
  selection: Selection,
  options: MapPanelOptions,
) => ReactNode;
export type RenderProfile = (source: ReplayData, selection: Selection) => ReactNode;
