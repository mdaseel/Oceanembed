import { lazy, Suspense, useEffect, useState } from "react";
import { getJson } from "../field/api";
import { format } from "../field/contract";
import { Button } from "./ui/button";
import remarkGfm from "remark-gfm";
const Plot = lazy(() => import("./Plot"));
const Markdown = lazy(() => import("react-markdown"));
interface EvidenceTable {
  source: string;
  sha256?: string;
  rows: Record<string, string>[];
  error?: string;
}
interface Evidence {
  tables: Record<string, EvidenceTable>;
  manifest: {
    inputs: { products: Record<string, string> };
    targets: { training_target_product: string };
    model: Record<string, string | number>;
    final_core_decision: { rejected_alternatives: Record<string, string> };
  };
  inference_statement: string;
  argo_note: string;
  ablation_note: string;
}
export default function Validation() {
  const [data, setData] = useState<Evidence | null>(null),
    [error, setError] = useState(""),
    [tab, setTab] = useState("Performance"),
    [metric, setMetric] = useState("rmse");
  const [doc, setDoc] = useState<{ source: string; markdown: string } | null>(
      null,
    ),
    [docError, setDocError] = useState(""),
    [docLoading, setDocLoading] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    getJson<Evidence>("/api/evidence", controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => controller.abort();
  }, []);
  if (error)
    return (
      <p className="notice" role="alert">
        Validation evidence unavailable: {error}
      </p>
    );
  if (!data)
    return (
      <p className="empty" role="status">
        Reading executed validation artifacts…
      </p>
    );
  const table =
    data.tables[
      tab === "Argo check"
        ? "argo"
        : tab === "Ablation Studies"
          ? "ablation"
          : tab === "Error Analysis"
            ? "basins"
            : tab === "Acceptability"
              ? "architecture"
              : "grid"
    ];
  const models = Array.from(new Set(table.rows.map((r) => r.model))).filter(
    Boolean,
  );
  const colors = ["#aab8cd", "#a78bfa", "#67e8f9", "#fbbf24"];
  return (
    <div className="page-stack">
      <section className="panel">
        <span className="eyebrow">EXECUTED EVIDENCE / READ ONLY</span>
        <h2>Model Provenance &amp; Validation</h2>
        <p>{data.inference_statement}</p>
        <p className="muted">
          Grid benchmark: 2022–2024 historical reference. External observational
          check: 2022–2023 Argo. These populations are distinct; metrics are not
          pooled.
        </p>
        <div className="tabs" role="tablist" aria-label="Validation sections">
          {[
            "Performance",
            "Argo check",
            "Ablation Studies",
            "Error Analysis",
            "Acceptability",
          ].map((t) => (
            <Button
              role="tab"
              aria-selected={tab === t}
              variant={tab === t ? "default" : "ghost"}
              key={t}
              onClick={() => setTab(t)}
            >
              {t}
            </Button>
          ))}
        </div>
        {tab === "Argo check" && (
          <p className="notice">
            {data.argo_note} Argo GDAC is credited for the observational
            measurements.
          </p>
        )}
        {tab === "Ablation Studies" && (
          <p className="notice">{data.ablation_note}</p>
        )}
        {tab === "Acceptability" && (
          <p className="notice">
            Existing frozen L2 remains the final core. Temporal GRU and
            climatology-residual L2 were tested and rejected. The matrix records
            the architecture audit; its residual row predates the final
            rejection below.
          </p>
        )}
        {["Performance", "Argo check"].includes(tab) && (
          <>
            <label className="inline-label">
              Metric
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
              >
                <option value="rmse">RMSE (°C)</option>
                <option value="bias">Bias (°C)</option>
                <option value="correlation">Correlation</option>
                <option value="anomaly_correlation">Anomaly correlation</option>
              </select>
            </label>
            <Suspense fallback={<p>Loading chart…</p>}>
              <Plot
                data={models.map((model, i) => ({
                  x: table.rows
                    .filter((r) => r.model === model)
                    .map((r) => +r.depth_m),
                  y: table.rows
                    .filter((r) => r.model === model)
                    .map((r) => (r[metric] === "" ? null : +r[metric])),
                  name: model,
                  type: "scatter" as const,
                  mode: "lines+markers" as const,
                  connectgaps: false,
                  line: { color: colors[i], width: 2 },
                }))}
                layout={{
                  height: 340,
                  autosize: true,
                  paper_bgcolor: "transparent",
                  plot_bgcolor: "transparent",
                  margin: { l: 58, r: 20, t: 25, b: 70 },
                  font: { color: "#b7c7db", family: "system-ui" },
                  xaxis: { title: { text: "Depth (m)" }, gridcolor: "#27354c" },
                  yaxis: {
                    title: {
                      text: metric.includes("correlation")
                        ? metric.replaceAll("_", " ")
                        : `${metric.toUpperCase()} (°C)`,
                    },
                    gridcolor: "#27354c",
                  },
                  legend: { orientation: "h", y: -0.2 },
                }}
                config={{ responsive: true, displayModeBar: false }}
                useResizeHandler
                style={{ width: "100%" }}
              />
            </Suspense>
          </>
        )}
        <EvidenceGrid table={table} />
        {tab === "Ablation Studies" && (
          <details>
            <summary>Measured control-to-frozen run variation</summary>
            <EvidenceGrid table={data.tables.noise} />
          </details>
        )}
      </section>
      <section className="panel">
        <span className="eyebrow">SIH26066 / PRODUCT ALIGNMENT</span>
        <h2>Surface observations → frozen L2 → temperature</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Channel / role</th>
                <th>Actual product</th>
                <th>Problem statement alignment</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.manifest.inputs.products).map(
                ([channel, product]) => (
                  <tr key={channel}>
                    <td>{channel}</td>
                    <td>{product}</td>
                    <td>
                      {channel === "sss"
                        ? "Exact listed MULTIOBS DOI; SMAP + SMOS + in-situ blended"
                        : channel.includes("wind")
                          ? "CCMP is an explicitly listed alternative to ASCAT"
                          : "Matches the listed product"}
                    </td>
                  </tr>
                ),
              )}
              <tr>
                <td>Training reference</td>
                <td>{data.manifest.targets.training_target_product}</td>
                <td>Matches the GLORYS DOI; never read by replay</td>
              </tr>
              <tr>
                <td>Observational check</td>
                <td>Individual QC’d Argo GDAC profiles, 2022–2023</td>
                <td>
                  PS suggests INCOIS LAS gridded Argo; this implementation uses
                  collocated profiles
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>Architecture closure &amp; provenance</h2>
        <p>
          Absolute L2 temperature is compared with separately evaluated L0
          climatology. Anomaly = L2 − L0. No blending or residual model is used.
        </p>
        <dl className="provenance-grid">
          {Object.entries(data.manifest.model)
            .filter(([k]) =>
              [
                "l2_state_dict_sha256",
                "l2_encoder_sha256",
                "latent_dim",
                "receptive_field",
                "n_parameters",
              ].includes(k),
            )
            .map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll("_", " ")}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
        </dl>
        <ul>
          {Object.entries(
            data.manifest.final_core_decision.rejected_alternatives,
          ).map(([name, decision]) => (
            <li key={name}>
              {name}: {decision}
            </li>
          ))}
        </ul>
        <div className="action-row">
          {[
            ["closure", "Architecture closure"],
            ["architecture", "Architecture audit"],
            ["l2", "L2 report"],
            ["argo", "Argo report"],
          ].map(([key, label]) => (
            <Button
              key={key}
              variant="outline"
              onClick={async () => {
                setDocLoading(true);
                setDocError("");
                setDoc(null);
                try {
                  setDoc(await getJson(`/api/evidence/document/${key}`));
                } catch (e) {
                  setDocError((e as Error).message);
                } finally {
                  setDocLoading(false);
                }
              }}
            >
              {label}
            </Button>
          ))}
        </div>
        {docLoading && <p>Reading report…</p>}
        {docError && <p role="alert">{docError}</p>}
        {doc && (
          <details open className="report-reader">
            <summary>{doc.source} · executed report, original wording</summary>
            <p className="notice">
              Earlier report wording is preserved here. Use the
              observational-independence caveat and final architecture decisions
              shown above.
            </p>
            <Suspense fallback={<p>Loading report…</p>}>
              <Markdown remarkPlugins={[remarkGfm]}>{doc.markdown}</Markdown>
            </Suspense>
          </details>
        )}
      </section>
    </div>
  );
}
function EvidenceGrid({ table }: { table: EvidenceTable }) {
  if (!table.rows.length)
    return (
      <p className="empty">
        {table.error || "No rows in this artifact"} · {table.source}
      </p>
    );
  const keys = Object.keys(table.rows[0]);
  return (
    <>
      <p className="muted small">Source: {table.source}</p>
      <div className="table-scroll evidence-table">
        <table>
          <thead>
            <tr>
              {keys.map((k) => (
                <th key={k}>{k.replaceAll("_", " ")}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, i) => (
              <tr key={i}>
                {keys.map((k) => (
                  <td key={k}>
                    {row[k] === ""
                      ? "Unavailable"
                      : /^-?\d+\.\d+(e[-+]?\d+)?$/i.test(row[k])
                        ? format(+row[k], 4)
                        : row[k]}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Artifact checksum</summary>
        <code>{table.sha256}</code>
      </details>
    </>
  );
}
