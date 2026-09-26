import {
  AREA_RULE,
  TRACK_RELATION_RULE,
  coordText,
  signed,
  type MonitoringArea,
  type MonitoringResult,
} from "../../field/hazardIntelligence";
import { InfoTip } from "./InfoTip";

export type AreaRelation = { kind: "TRACK INTERSECTION" | "OUTSIDE TRACK LINE"; distanceKm: number | null };

const anomaly = (v: number) => (Number.isFinite(v) ? signed(v, 2, "°C") : "Unavailable");

/** THERMAL MONITORING AREAS — contiguous HIGH/ELEVATED cells, ranked by a stated rule. */
export function MonitoringAreas({
  result,
  activeKey,
  onArea,
  date,
  mode,
  rmse,
  relations,
}: {
  result: MonitoringResult;
  activeKey: string | null;
  onArea: (area: MonitoringArea) => void;
  date: string;
  mode: "historical" | "nrt" | "scenario";
  rmse: number;
  relations?: Record<string, AreaRelation>;
}) {
  return (
    <section className="panel monitoring" data-testid="monitoring-areas" data-date={date}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">
            THERMAL MONITORING AREAS · {mode === "nrt" ? "QUALIFIED STATE" : "FIELD DATE"} {date}
          </span>
          <h2>
            Where upper-ocean heat is concentrated <InfoTip term="monitoring" />
          </h2>
        </div>
      </div>
      {result.areas.length === 0 ? (
        <p className="notice" data-testid="no-hotspot">
          No HIGH/ELEVATED thermal monitoring area found under the frozen thermal-support
          protocol.
        </p>
      ) : (
        <ol className="hotspot-list">
          {result.areas.map((a) => {
            const key = `${a.row},${a.col}`;
            const active = key === activeKey;
            const relation = relations?.[key];
            return (
              <li
                key={key}
                className={active ? "active" : ""}
                data-testid={`hotspot-${a.rank}`}
                data-tier={a.tier}
                data-lat={a.lat}
                data-lon={a.lon}
                data-tchp={a.tchp.toFixed(1)}
                data-relation={relation?.kind ?? ""}
              >
                <button type="button" className="hotspot-row" onClick={() => onArea(a)} aria-pressed={active}>
                  <span className={`hotspot-rank tier-${a.tier.toLowerCase()}`}>{a.rank}</span>
                  <span className="hotspot-main">
                    <strong>{a.basin ?? coordText(a.lat, a.lon)}</strong>
                    <span className="small muted">
                      {a.basin ? coordText(a.lat, a.lon) : "outside the named basins"} ·{" "}
                      {a.cells} {a.cells === 1 ? "cell" : "cells"} · ~{Math.round(a.areaKm2).toLocaleString("en-US")} km²
                    </span>
                    {relation && (
                      <span className={`relation-pill ${relation.kind === "TRACK INTERSECTION" ? "intersect" : ""}`} data-testid={`hotspot-relation-${a.rank}`}>
                        {relation.kind === "TRACK INTERSECTION"
                          ? "TRACK INTERSECTION"
                          : `OUTSIDE TRACK LINE · nearest ${relation.distanceKm === null ? "—" : `${Math.round(relation.distanceKm)} km`}`}
                      </span>
                    )}
                  </span>
                  <span className={`tier-pill tier-${a.tier.toLowerCase()}`}>{a.tier}</span>
                  <span className="hotspot-value">
                    {a.tchp.toFixed(1)}
                    <small>kJ/cm²</small>
                  </span>
                </button>
                {active && (
                  <div className="hotspot-card" data-testid="hotspot-card">
                    <span className="eyebrow">THERMAL MONITORING AREA {a.rank}</span>
                    <dl className="metric-list compact">
                      <div><dt>Thermal support</dt><dd>{a.tier}</dd></div>
                      <div><dt>Peak TCHP</dt><dd data-testid="hotspot-card-tchp">{a.tchp.toFixed(1)} kJ/cm²</dd></div>
                      <div><dt>Median TCHP</dt><dd data-testid="hotspot-card-median">{Number.isFinite(a.medianTchp) ? `${a.medianTchp.toFixed(1)} kJ/cm²` : "—"}</dd></div>
                      <div><dt>50 m anomaly (peak)</dt><dd>{anomaly(a.anomaly50)}</dd></div>
                      <div><dt>75 m anomaly (peak)</dt><dd>{anomaly(a.anomaly75)}</dd></div>
                      <div><dt>100 m anomaly (peak)</dt><dd data-testid="hotspot-card-anomaly">{anomaly(a.anomaly100)}</dd></div>
                      <div><dt>Centroid</dt><dd>{coordText(a.centroidLat, a.centroidLon)}</dd></div>
                      <div><dt>Extent</dt><dd data-testid="hotspot-card-area">{a.cells} valid cells · ~{Math.round(a.areaKm2).toLocaleString("en-US")} km²</dd></div>
                    </dl>
                    <h3>WHY MONITOR THIS AREA?</h3>
                    <p>
                      {a.tier === "HIGH"
                        ? "A large warm-water reservoir exists beneath the surface."
                        : "A substantial warm-water reservoir exists beneath the surface."}
                      {Number.isFinite(a.anomaly100) && a.anomaly100 > 0
                        ? ` At the peak cell, water at 100 m is ${a.anomaly100.toFixed(2)} °C warmer than the climatological expectation.`
                        : ""}
                    </p>
                    <p>
                      {a.tier === "HIGH"
                        ? "If an official cyclone track enters this region, the ocean could provide strong thermal support."
                        : "If an official cyclone track enters this region, ocean thermal conditions could support storm maintenance or intensification."}
                    </p>
                    <p className="small muted">This is not a cyclone forecast.</p>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <p className="small muted" data-testid="hotspot-rule">
        Ranking rule: contiguous areas of cells the frozen protocol labels HIGH or ELEVATED;
        areas containing HIGH cells first, each group ordered by peak TCHP. The 100 m anomaly
        is shown beside each area and never weighted. {result.components} areas found (
        {result.highCells.toLocaleString("en-US")} HIGH and {result.elevatedCells.toLocaleString("en-US")}{" "}
        ELEVATED cells); up to five are listed. Cell-level TCHP RMSE {rmse} kJ/cm². {AREA_RULE}
        {relations ? ` ${TRACK_RELATION_RULE}` : ""}
      </p>
    </section>
  );
}
