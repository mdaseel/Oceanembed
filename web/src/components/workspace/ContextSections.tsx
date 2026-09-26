import { useEffect, useState } from "react";
import { getJson } from "../../field/api";
import { num } from "./Layout";
import type { CoastalContext, ValidationContext } from "./scienceApi";

/** COASTAL CONTEXT for one location: geography, never a damage or risk claim. */
export function CoastalContextView({
  lat,
  lon,
  label,
  testid = "coastal-context",
}: {
  lat: number;
  lon: number;
  label?: string;
  testid?: string;
}) {
  const [data, setData] = useState<CoastalContext | null>(null);
  const [error, setError] = useState("");
  const key = `${lat.toFixed(3)},${lon.toFixed(3)}`;
  useEffect(() => {
    let live = true;
    setError("");
    getJson<CoastalContext>(`/api/science/coastal?lat=${lat}&lon=${lon}`)
      .then((d) => live && setData(d?.wording ? d : null))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
    // the key captures lat/lon at display precision
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  if (error) return <p className="ws-note">Coastal context unavailable: {error}</p>;
  if (!data) return <p className="ws-note">Reading coastal geography…</p>;
  return (
    <div data-testid={testid} data-status={data.status}>
      {label && <p className="ws-note">{label}</p>}
      {data.status !== "OK" ? (
        <p className="ws-note">
          {data.status === "LAND_OR_NO_OCEAN_CELL"
            ? "This grid cell is not an ocean cell; no offshore distance is reported."
            : data.status === "OUTSIDE_DOMAIN"
              ? "Outside the OceanEmbed domain."
              : "No mapped coastline was found for this cell."}
        </p>
      ) : (
        <>
          <dl className="ws-kv">
            <dt>Nearest coastline</dt>
            <dd data-testid="coastal-state">
              {data.coastal_state}, {data.country}
            </dd>
            <dt>Offshore distance</dt>
            <dd data-testid="coastal-distance">~{data.offshore_distance_km} km</dd>
            <dt>Coastal district</dt>
            <dd data-testid="coastal-district">{data.coastal_district ?? "—"}</dd>
            <dt>Coastal segment</dt>
            <dd>{data.coastal_segment}</dd>
          </dl>
          {data.district_note && <p className="ws-note">{data.district_note}.</p>}
        </>
      )}
      <p className="ws-note" data-testid="coastal-wording">
        {data.wording}
      </p>
      {data.sources && (
        <p className="ws-note">
          Geography: {data.sources.map((s) => `${s.name} (${s.license})`).join(" · ")}.
        </p>
      )}
    </div>
  );
}

/** VALIDATION CONTEXT: historical Argo error at this depth, never an uncertainty interval. */
export function ValidationContextView({
  depth,
  lat,
  lon,
  compact = false,
  testid = "validation-context",
}: {
  depth: number;
  lat: number;
  lon: number;
  compact?: boolean;
  testid?: string;
}) {
  const [data, setData] = useState<ValidationContext | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let live = true;
    getJson<ValidationContext>(`/api/science/validation-context?depth=${depth}&lat=${lat}&lon=${lon}`)
      .then((d) => live && setData(d?.models ? d : null))
      .catch((e) => live && setError((e as Error).message));
    return () => {
      live = false;
    };
  }, [depth, lat, lon]);
  if (error) return <p className="ws-note">Validation context unavailable: {error}</p>;
  if (!data) return <p className="ws-note">Reading validation tables…</p>;
  const l2 = data.models.L2;
  const l0 = data.models.L0;
  const ci = data.bootstrap_l2_minus_l0;
  return (
    <div data-testid={testid} data-depth={data.depth_m}>
      <dl className="ws-kv">
        <dt>Depth · scope</dt>
        <dd>
          {data.depth_m} m · {data.scope}
        </dd>
        <dt>Historical Argo RMSE</dt>
        <dd data-testid="validation-l2-rmse">{num(l2?.rmse_c, 2, "°C")}</dd>
        <dt>Climatology baseline RMSE</dt>
        <dd>{num(l0?.rmse_c, 2, "°C")}</dd>
        <dt>Relative improvement</dt>
        <dd>{data.l2_improvement_vs_l0_percent == null ? "—" : `${data.l2_improvement_vs_l0_percent.toFixed(1)} %`}</dd>
        <dt>Anomaly correlation</dt>
        <dd>{num(l2?.anomaly_correlation, 2)}</dd>
        <dt>Sample count</dt>
        <dd>{l2 ? l2.n.toLocaleString("en-US") : "—"}</dd>
      </dl>
      {!compact && ci && (
        <p className="ws-note">
          L2 minus L0 RMSE {ci.rmse_difference_c.toFixed(3)} °C, bootstrap interval {ci.ci_lo.toFixed(3)} to{" "}
          {ci.ci_hi.toFixed(3)} °C, resampling {ci.clusters} {ci.cluster_unit}s.
        </p>
      )}
      {data.regional_sample_note && <p className="ws-note">{data.regional_sample_note}.</p>}
      <p className="ws-note" data-testid="validation-wording">
        {data.wording} {data.period}.
      </p>
    </div>
  );
}
