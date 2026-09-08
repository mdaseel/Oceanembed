import { profile, type FieldView, type Selection } from "./contract";
import { drawMap, type MapProps } from "../components/MapView";
export function download(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const csv = (x: unknown) => `"${String(x ?? "").replaceAll('"', '""')}"`;
export function profileCsv(f: FieldView, selection: Selection) {
  const header = [
    "date",
    "requested_lat",
    "requested_lon",
    "grid_lat",
    "grid_lon",
    "location_status",
    "depth_m",
    "temperature_c",
    "climatology_c",
    "anomaly_c",
    "l2_sha256",
    "inference_source",
    "credits",
    "nominal_zero_m_note",
    "deep_skill_note",
  ];
  const lines = profile(f, selection).map((row) =>
    [
      f.effectiveDate,
      selection.requestedLat,
      selection.requestedLon,
      f.lat[selection.row],
      f.lon[selection.col],
      selection.status,
      row.depth,
      ...[row.temperature, row.climatology, row.anomaly].map((v) =>
        Number.isFinite(v) ? v : "",
      ),
      f.provenance.l2_state_dict_sha256,
      f.provenance.inference_source,
      f.credits,
      f.provenance.nominal_zero_m_note,
      f.provenance.deep_skill_note,
    ]
      .map(csv)
      .join(","),
  );
  return [header.join(","), ...lines].join("\r\n");
}
export async function mapPng(props: Omit<MapProps, "onSelect">) {
  const canvas = document.createElement("canvas");
  drawMap(canvas, props);
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/png"),
  );
  if (!blob) throw Error("PNG export unavailable");
  download(
    blob,
    `OceanEmbed-${props.field.effectiveDate}-${props.field.depths[props.depth]}m-${props.layer}.png`,
  );
}
