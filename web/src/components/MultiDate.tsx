import { lazy, Suspense, useState } from "react";
import { loadReplay } from "../field/api";
import { offset, resolve, DEPTHS } from "../field/contract";
import { Button } from "./ui/button";
const Plot = lazy(() => import("./Plot"));
export default function MultiDate({
  date,
  coords,
  depth,
}: {
  date: string;
  coords: [number, number];
  depth: number;
}) {
  const [start, setStart] = useState(date),
    [end, setEnd] = useState(date),
    [rows, setRows] = useState<
      { date: string; t: number | null; c: number | null }[]
    >([]),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [label, setLabel] = useState("");
  return (
    <details className="panel">
      <summary>Compare historical dates at the selected location</summary>
      <p className="muted small">
        Each day is an independent reconstruction. Up to 14 days per request.
      </p>
      <form
        className="action-row"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          setRows([]);
          const a = Date.parse(start),
            b = Date.parse(end),
            n = (b - a) / 86400000 + 1;
          if (!Number.isFinite(n) || n < 1 || n > 14) {
            setError("Choose an ordered range of 1–14 days.");
            return;
          }
          setBusy(true);
          setLabel(
            `${coords[0].toFixed(3)}°N, ${coords[1].toFixed(3)}°E · ${DEPTHS[depth]} m`,
          );
          try {
            const result = [];
            for (let t = a; t <= b; t += 86400000) {
              const day = new Date(t).toISOString().slice(0, 10),
                f = (await loadReplay(day)).field,
                s = resolve(f, ...coords),
                i = s.row >= 0 ? offset(f, s.row, s.col, depth) : -1;
              result.push({
                date: day,
                t:
                  i >= 0 && Number.isFinite(f.temperature[i])
                    ? f.temperature[i]
                    : null,
                c:
                  i >= 0 && Number.isFinite(f.climatology[i])
                    ? f.climatology[i]
                    : null,
              });
            }
            setRows(result);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          From
          <input
            aria-label="Comparison start"
            type="date"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            required
          />
        </label>
        <label>
          To
          <input
            aria-label="Comparison end"
            type="date"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            required
          />
        </label>
        <Button disabled={busy} type="submit">
          Compare dates
        </Button>
      </form>
      {busy && <p role="status">Loading independent daily fields…</p>}
      {error && <p role="alert">{error}</p>}
      {!busy && !error && !rows.length && (
        <p className="muted small">Choose dates to load a comparison.</p>
      )}
      {rows.length > 0 && (
        <>
          <p>{label}</p>
          <Suspense fallback={<p>Loading comparison chart…</p>}>
            <Plot
              data={["t", "c"].map((k, i) => ({
                x: rows.map((r) => r.date),
                y: rows.map((r) => r[k as "t" | "c"]),
                name: i ? "L0 climatology" : "OceanEmbed L2",
                type: "scatter" as const,
                mode: "lines+markers" as const,
                connectgaps: false,
                line: { color: i ? "#aab8cd" : "#67e8f9" },
              }))}
              layout={{
                height: 260,
                autosize: true,
                paper_bgcolor: "transparent",
                plot_bgcolor: "transparent",
                font: { color: "#aebfd5" },
                margin: { l: 50, r: 20, t: 20, b: 60 },
                xaxis: { title: { text: "Historical date" } },
                yaxis: { title: { text: "Temperature (°C)" } },
                legend: { orientation: "h" },
              }}
              config={{ responsive: true, displayModeBar: false }}
              style={{ width: "100%" }}
              useResizeHandler
            />
          </Suspense>
        </>
      )}
    </details>
  );
}
