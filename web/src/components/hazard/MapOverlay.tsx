import { useMemo } from "react";
import {
  outlinePath,
  type EventTrack,
  type MonitoringArea,
} from "../../field/hazardIntelligence";
import { PROJECTION } from "../MapView";

const { W, H, left, top, width, height } = PROJECTION;

export interface ExternalTrackOverlay {
  label: string;
  test: boolean;
  points: { lat: number; lon: number; point_type: string; valid_time: string }[];
}

/**
 * Drawn over the shared 2D map in its own projection: numbered monitoring-area
 * outlines; for a historical event date, the observed best track up to that day;
 * an external advisory track with observed and forecast positions kept distinct;
 * or a user-drawn scenario path. Nothing here is a model quantity.
 */
export function MapOverlay({
  rows,
  cols,
  areas,
  activeKey,
  onArea,
  track,
  trackDate,
  externalTrack = null,
  scenarioPath = [],
  drawing = false,
  onDraw,
  toLatLon,
}: {
  rows: number;
  cols: number;
  areas: MonitoringArea[];
  activeKey: string | null;
  onArea: (area: MonitoringArea) => void;
  track: EventTrack | null;
  trackDate: string | null;
  externalTrack?: ExternalTrackOverlay | null;
  scenarioPath?: { lat: number; lon: number }[];
  drawing?: boolean;
  onDraw?: (lat: number, lon: number) => void;
  toLatLon?: (x: number, y: number) => [number, number] | null;
}) {
  const cw = width / cols,
    ch = height / rows;
  const project = (lat: number, lon: number): [number, number] => [
    left + ((lon - 45) / 0.25 + 0.5) * cw,
    top + ((30 - lat) / 0.25 + 0.5) * ch,
  ];
  const outlines = useMemo(
    () => areas.map((a) => outlinePath(a.members, rows, cols, PROJECTION)),
    [areas, rows, cols],
  );
  const points = track && trackDate ? track.points : [];
  const travelled = trackDate ? points.filter((p) => p.time.slice(0, 10) <= trackDate) : [];
  const last = travelled[travelled.length - 1];
  const line = (pts: { lat: number; lon: number }[]) =>
    pts
      .map((p) =>
        project(p.lat, p.lon)
          .map((v) => v.toFixed(1))
          .join(","),
      )
      .join(" ");
  const observed = externalTrack?.points.filter((p) => p.point_type === "observed") ?? [];
  const forecast = externalTrack?.points.filter((p) => p.point_type === "forecast") ?? [];
  const forecastLine = observed.length ? [observed[observed.length - 1], ...forecast] : forecast;

  return (
    <svg
      className="map-overlay"
      viewBox={`0 0 ${W} ${H}`}
      data-testid="map-overlay"
      data-track-points={travelled.length}
      data-areas={areas.length}
      data-external-observed={observed.length}
      data-external-forecast={forecast.length}
      data-scenario-points={scenarioPath.length}
      data-drawing={drawing ? "true" : "false"}
    >
      <defs>
        <clipPath id="hazard-plot-area">
          <rect x={left} y={top} width={width} height={height} />
        </clipPath>
      </defs>
      {points.length > 1 && (
        <g className="track" clipPath="url(#hazard-plot-area)" data-testid="track-overlay">
          <polyline className="track-full" points={line(points)} />
          {travelled.length > 1 && <polyline className="track-travelled" points={line(travelled)} />}
          {last &&
            (() => {
              const [x, y] = project(last.lat, last.lon);
              return (
                <g className="track-position" data-testid="track-position">
                  <circle cx={x} cy={y} r={8} />
                  <text x={x + 13} y={y - 11}>{`IBTrACS ${last.time.slice(5, 16)} UTC`}</text>
                </g>
              );
            })()}
        </g>
      )}
      {areas.map((a, i) => {
        const [x, y] = project(a.lat, a.lon);
        const key = `${a.row},${a.col}`;
        return (
          <g
            key={key}
            className={`hotspot-mark tier-${a.tier.toLowerCase()}${key === activeKey ? " active" : ""}`}
            data-testid={`hotspot-mark-${a.rank}`}
            role="button"
            tabIndex={0}
            aria-label={`Thermal monitoring area ${a.rank}: ${a.tier}, peak TCHP ${a.tchp.toFixed(1)} kJ/cm²`}
            onClick={() => onArea(a)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onArea(a);
              }
            }}
          >
            <path d={outlines[i]} className="hotspot-outline" />
            <circle cx={x} cy={y} r={17} className="hotspot-ring" />
            <text x={x} y={y + 5} textAnchor="middle" className="hotspot-number">
              {a.rank}
            </text>
          </g>
        );
      })}
      {externalTrack && externalTrack.points.length > 0 && (
        <g className="external-track" clipPath="url(#hazard-plot-area)" data-testid="external-track-overlay">
          {observed.length > 1 && <polyline className="ext-observed-line" points={line(observed)} />}
          {forecastLine.length > 1 && <polyline className="ext-forecast-line" points={line(forecastLine)} />}
          {observed.map((p) => {
            const [x, y] = project(p.lat, p.lon);
            return <circle key={`o-${p.valid_time}`} className="ext-observed" cx={x} cy={y} r={5} />;
          })}
          {forecast.map((p) => {
            const [x, y] = project(p.lat, p.lon);
            return <circle key={`f-${p.valid_time}`} className="ext-forecast" cx={x} cy={y} r={6} />;
          })}
        </g>
      )}
      {externalTrack && (
        <g className="overlay-legend" data-testid="external-track-legend" transform={`translate(${left + width - 395}, ${top + 12})`}>
          <rect width="385" height="94" rx="8" />
          <circle className="ext-observed" cx="18" cy="20" r="5" />
          <text x="32" y="25">Observed position — external source</text>
          <circle className="ext-forecast" cx="18" cy="42" r="6" />
          <text x="32" y="47">Forecast position — external source</text>
          <rect className="legend-area" x="11" y="56" width="14" height="12" />
          <text x="32" y="67">OceanEmbed thermal monitoring area</text>
          <text className="legend-provenance" x="12" y="86">
            {externalTrack.test ? "HISTORICAL / TEST EVENT · " : ""}
            {externalTrack.label.length > 58 ? `${externalTrack.label.slice(0, 57)}…` : externalTrack.label}
          </text>
        </g>
      )}
      {scenarioPath.length > 0 && (
        <g className="scenario-path" data-testid="scenario-overlay">
          {scenarioPath.length > 1 && <polyline points={line(scenarioPath)} />}
          {scenarioPath.map((p, i) => {
            const [x, y] = project(p.lat, p.lon);
            return (
              <g key={`${p.lat},${p.lon},${i}`}>
                <circle cx={x} cy={y} r={9} />
                <text x={x} y={y + 4} textAnchor="middle">
                  {i + 1}
                </text>
              </g>
            );
          })}
        </g>
      )}
      {drawing && (
        <rect
          className="draw-capture"
          data-testid="draw-capture"
          x={left}
          y={top}
          width={width}
          height={height}
          onClick={(e) => {
            const svg = e.currentTarget.ownerSVGElement;
            if (!svg || !toLatLon) return;
            const r = svg.getBoundingClientRect();
            const hit = toLatLon(((e.clientX - r.left) / r.width) * W, ((e.clientY - r.top) / r.height) * H);
            if (hit) onDraw?.(Math.round(hit[0] * 100) / 100, Math.round(hit[1] * 100) / 100);
          }}
        />
      )}
    </svg>
  );
}
