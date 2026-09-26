import { useEffect, useState } from "react";
import { getJson } from "../../field/api";
import type { RiComparison, RiResult, RiStorm, RiSummary, RiVariable } from "./scienceApi";

const fmt = (v: number | null | undefined, d = 2) => (v == null || !Number.isFinite(v) ? "—" : v.toFixed(d));

/** One variable: every eligible storm as a point, with the group median and IQR. */
function Strip({ variable, storms }: { variable: RiVariable; storms: RiStorm[] }) {
  const w = 300;
  const h = 170;
  const pad = { l: 44, r: 10, t: 14, b: 26 };
  const groups: [string, RiStorm[]][] = [
    ["RI", storms.filter((s) => s.ri === true)],
    ["Non-RI", storms.filter((s) => s.ri === false)],
  ];
  const values = storms.map((s) => s.values?.[variable.variable]).filter((v): v is number => v != null);
  if (!values.length) return null;
  let lo = Math.min(...values);
  let hi = Math.max(...values);
  if (hi === lo) {
    lo -= 1;
    hi += 1;
  }
  const y = (v: number) => pad.t + (1 - (v - lo) / (hi - lo)) * (h - pad.t - pad.b);
  const x0 = (g: number) => pad.l + (g + 0.5) * ((w - pad.l - pad.r) / 2);
  const stats = [variable.ri, variable.non_ri];
  return (
    <svg className="strip heatmap" viewBox={`0 0 ${w} ${h}`} role="img" aria-label={`${variable.label} by group`}>
      {[lo, (lo + hi) / 2, hi].map((t) => (
        <g key={t}>
          <line x1={pad.l} x2={w - pad.r} y1={y(t)} y2={y(t)} stroke="#1b2633" />
          <text x={pad.l - 6} y={y(t) + 3} textAnchor="end">
            {t.toFixed(variable.unit === "°C" ? 1 : 0)}
          </text>
        </g>
      ))}
      {groups.map(([name, list], g) => {
        const s = stats[g];
        return (
          <g key={name}>
            {s && (
              <>
                <rect x={x0(g) - 34} y={y(s.q3)} width={68} height={Math.max(1, y(s.q1) - y(s.q3))} fill="#16303c" rx={3} />
                <line x1={x0(g) - 40} x2={x0(g) + 40} y1={y(s.median)} y2={y(s.median)} stroke="#67e8f9" strokeWidth={2} />
              </>
            )}
            {list.map((st, i) => {
              const v = st.values?.[variable.variable];
              if (v == null) return null;
              const jitter = ((i * 37) % 21) - 10;
              return (
                <circle key={st.sid} cx={x0(g) + jitter * 2.2} cy={y(v)} r={3.2} fill={g === 0 ? "#f3a26b" : "#9fb8cc"} opacity={0.85}>
                  <title>{`${st.name} ${st.season}: ${v.toFixed(2)} ${variable.unit}`}</title>
                </circle>
              );
            })}
            <text x={x0(g)} y={h - 8} textAnchor="middle">
              {`${name} (n=${g === 0 ? variable.n_ri : variable.n_non_ri})`}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function statement(c: RiComparison): string {
  if (!c.tests_run) return `Descriptive only: ${c.tests_note}.`;
  const clear = c.variables.filter((v) => v.p_holm != null && v.p_holm < 0.05);
  if (!clear.length)
    return `No clear retrospective association: after Holm adjustment, none of the ${c.variables.length} pre-registered ocean variables differs between the ${c.n_ri} rapid-intensification storms and the ${c.n_non_ri} storms without it.`;
  return `Retrospective association after Holm adjustment for: ${clear
    .map((v) => `${v.label} (RI median ${fmt(v.ri?.median)} vs ${fmt(v.non_ri?.median)} ${v.unit})`)
    .join("; ")}. Association is not prediction.`;
}

/** RETROSPECTIVE RAPID-INTENSIFICATION STUDY - exploratory, never a predictor. */
export function RiStudy() {
  const [data, setData] = useState<RiSummary | null>(null);
  const [error, setError] = useState("");
  const [wind, setWind] = useState("imd");
  useEffect(() => {
    getJson<RiSummary>("/api/science/ri-study")
      .then((d) => setData(d?.results ? d : null))
      .catch((e) => setError((e as Error).message));
  }, []);
  if (error) return <p className="notice">RI study unavailable: {error}</p>;
  if (!data) return <p className="muted small">Reading the pre-computed study…</p>;
  const r: RiResult = data.results[wind];
  const c = r.comparison;
  const eligible = r.storms.filter((s) => s.eligible);
  const primary = c.variables.find((v) => v.primary) ?? c.variables[0];
  return (
    <div className="ws" data-testid="ri-study" data-wind={wind}>
      <div className="panel-heading compact">
        <div>
          <span className="eyebrow">
            RETROSPECTIVE RESEARCH · EXPLORATORY N={r.counts.eligible} · NOT A PREDICTOR
          </span>
          <h2>Ocean heat ahead of real storms and their observed intensity change</h2>
        </div>
        <div className="segmented" role="group" aria-label="Intensity source">
          {Object.keys(data.results).map((k) => (
            <button key={k} type="button" className={wind === k ? "active" : ""} aria-pressed={wind === k} data-testid={`ri-wind-${k}`} onClick={() => setWind(k)}>
              {data.results[k].wind_source}
            </button>
          ))}
        </div>
      </div>
      <p className="finding" data-testid="ri-null-statement">
        {statement(c)}
      </p>
      <div className="fig-row">
        <div className="fig-card" data-testid="ri-counts">
          <h3>Storms</h3>
          <table className="science-table">
            <tbody>
              <tr>
                <td>North Indian storms 2015–2024 in IBTrACS</td>
                <td>{r.counts.storms_in_file_2015_2024}</td>
              </tr>
              <tr>
                <td>Eligible under the frozen rule</td>
                <td>{r.counts.eligible}</td>
              </tr>
              <tr className="highlight">
                <td>Rapid intensification (≥ 30 kt / 24 h)</td>
                <td>{r.counts.ri}</td>
              </tr>
              <tr className="highlight">
                <td>No rapid intensification</td>
                <td>{r.counts.non_ri}</td>
              </tr>
              {Object.entries(r.exclusion_reasons).map(([reason, n]) => (
                <tr key={reason}>
                  <td>Excluded: {reason}</td>
                  <td>{n}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="ws-note">{data.definition}</p>
        </div>
        <div className="fig-card">
          <h3>
            {primary.label} · primary variable ({primary.unit})
          </h3>
          <Strip variable={primary} storms={eligible} />
          <p className="ws-note">
            Median {fmt(primary.ri?.median, 1)} vs {fmt(primary.non_ri?.median, 1)} {primary.unit}
            {primary.median_difference_ci95
              ? ` · difference ${fmt(primary.median_difference, 1)} (bootstrap interval ${fmt(primary.median_difference_ci95[0], 1)} to ${fmt(primary.median_difference_ci95[1], 1)})`
              : ""}
            .
          </p>
        </div>
      </div>
      <details className="fig-card" data-testid="ri-table">
        <summary className="eyebrow">ALL PRE-REGISTERED VARIABLES · MEDIAN [IQR], TESTS AND EFFECT SIZE</summary>
        <div className="table-scroll">
          <table className="science-table">
            <thead>
              <tr>
                <th>Variable</th>
                <th>RI median [IQR]</th>
                <th>Non-RI median [IQR]</th>
                <th>n</th>
                <th>Rank-biserial</th>
                <th>p</th>
                <th>p (Holm)</th>
              </tr>
            </thead>
            <tbody>
              {c.variables.map((v) => (
                <tr key={v.variable} className={v.primary ? "highlight" : ""}>
                  <td>
                    {v.label} ({v.unit})
                  </td>
                  <td>
                    {fmt(v.ri?.median)} [{fmt(v.ri?.q1)}, {fmt(v.ri?.q3)}]
                  </td>
                  <td>
                    {fmt(v.non_ri?.median)} [{fmt(v.non_ri?.q1)}, {fmt(v.non_ri?.q3)}]
                  </td>
                  <td>
                    {v.n_ri} / {v.n_non_ri}
                  </td>
                  <td>{fmt(v.rank_biserial)}</td>
                  <td>{fmt(v.p_value, 3)}</td>
                  <td>{fmt(v.p_holm, 3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="fig-row">
          {c.variables
            .filter((v) => !v.primary)
            .map((v) => (
              <div key={v.variable}>
                <p className="ws-note">
                  {v.label} ({v.unit})
                </p>
                <Strip variable={v} storms={eligible} />
              </div>
            ))}
        </div>
        <p className="ws-note" data-testid="ri-sensitivity">
          Out-of-sample sensitivity (2021–2024 storms, n={r.sensitivity_2021_2024.n_storms}):{" "}
          {statement(r.sensitivity_2021_2024)}
        </p>
        {r.storm_level_spearman_max_dv_vs_tchp && (
          <p className="ws-note">
            Storm-level Spearman correlation between the largest 24-h wind change and along-path TCHP: ρ ={" "}
            {r.storm_level_spearman_max_dv_vs_tchp.rho.toFixed(2)} (n={r.storm_level_spearman_max_dv_vs_tchp.n}).
          </p>
        )}
      </details>
      <p className="ws-note" data-testid="ri-wording">
        {data.wording} {data.sampling} {data.split_disclosure} Source: {data.source.dataset}. Protocol:{" "}
        {data.protocol}.
      </p>
    </div>
  );
}
