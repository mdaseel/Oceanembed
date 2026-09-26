import { useEffect, useRef, useState } from "react";
import { HAZARD_ORDER, type FieldView, type Selection } from "../../field/contract";
import { currentMapRelief, loadMapRelief } from "../../field/mapAppearance";
import { PROJECTION, pixelToLatLon } from "../MapView";

/**
 * The Phase 7D thermal-support category map. Categories arrive from the
 * backend (`hazard.category`); this canvas only colours them. Nothing is
 * categorised, thresholded or recomputed here.
 */
export const CATEGORY_RGB: Record<string, [number, number, number]> = {
  LOW: [38, 84, 124],
  MODERATE: [64, 145, 140],
  ELEVATED: [222, 158, 54],
  HIGH: [193, 61, 44],
  NOT_CATEGORIZED: [48, 52, 58],
};
const OUTSIDE: [number, number, number] = [10, 22, 30];
const { W, H, left, top, width, height } = PROJECTION;

export function ThermalSupportMap({
  field: f,
  selection,
  onSelect,
  trackNote,
}: {
  field: FieldView;
  selection: Selection;
  onSelect: (lat: number, lon: number) => void;
  trackNote: string;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [reliefReady, setReliefReady] = useState(!!currentMapRelief());
  useEffect(() => {
    let active = true;
    loadMapRelief()
      .then(() => active && setReliefReady(true))
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const hazard = f.hazard;
    if (!canvas.current || !hazard) return;
    const element = canvas.current;
    element.width = W;
    element.height = H;
    const c = element.getContext("2d")!;
    c.fillStyle = "#06080d";
    c.fillRect(0, 0, W, H);
    const rows = f.lat.length,
      cols = f.lon.length;
    const image = c.createImageData(width, height);
    if (image?.data) {
      for (let y = 0; y < height; y++)
        for (let x = 0; x < width; x++) {
          const r = rows - 1 - Math.min(rows - 1, Math.floor((y / height) * rows));
          const col = Math.min(cols - 1, Math.floor((x / width) * cols));
          const i = r * cols + col;
          const inside = !!(f.ocean[i] && f.inputValid[i]);
          const name = hazard.categoryLabels[hazard.category[i]] ?? "NOT_CATEGORIZED";
          const rgb = inside ? (CATEGORY_RGB[name] ?? OUTSIDE) : OUTSIDE;
          const o = (y * width + x) * 4;
          image.data[o] = rgb[0];
          image.data[o + 1] = rgb[1];
          image.data[o + 2] = rgb[2];
          image.data[o + 3] = 255;
        }
      c.putImageData(image, left, top);
    }
    const relief = currentMapRelief();
    if (relief) c.drawImage(relief, left, top, width, height);

    const cw = width / cols,
      ch = height / rows;
    if (selection.row >= 0) {
      const x = left + (selection.col + 0.5) * cw,
        y = top + (rows - 1 - selection.row + 0.5) * ch;
      c.strokeStyle = "#ffffff";
      c.lineWidth = 3;
      c.beginPath();
      c.arc(x, y, 9, 0, Math.PI * 2);
      c.stroke();
    }
    c.font = "600 19px system-ui";
    c.fillStyle = "#ced9e7";
    c.fillText(
      `${f.effectiveDate}  /  Ocean Thermal Support for Cyclone Intensification`,
      left,
      28,
    );
    // Labelled THERMAL SUPPORT so HIGH cannot be read as "high cyclone risk".
    c.font = "600 13px system-ui";
    c.fillStyle = "#8fa6bd";
    c.fillText("THERMAL SUPPORT (ocean heat available, not cyclone risk)", left, 668);
    c.font = "14px system-ui";
    let x0 = left;
    for (const name of [...HAZARD_ORDER, "NOT_CATEGORIZED"]) {
      const rgb = CATEGORY_RGB[name];
      c.fillStyle = `rgb(${rgb.join(",")})`;
      c.fillRect(x0, 680, 22, 12);
      c.fillStyle = "#d5dfed";
      const count = hazard.categoryCounts[name] ?? 0;
      const text = `${name.replace("_", " ")} (${count.toLocaleString()})`;
      c.fillText(text, x0 + 28, 691);
      x0 += 32 + c.measureText(text).width + 24;
    }
    c.font = "12px system-ui";
    c.fillStyle = "#94a8c1";
    c.fillText(trackNote, left, 716);
    c.fillText(f.credits, left, 736);
  }, [f, selection, trackNote, reliefReady]);

  return (
    <canvas
      ref={canvas}
      className="map-canvas"
      data-testid="hazard-map"
      data-field-date={f.effectiveDate}
      role="img"
      aria-label="Ocean thermal support categories. Click to select a grid cell."
      onClick={(e) => {
        const rect = e.currentTarget.getBoundingClientRect();
        const hit = pixelToLatLon(
          ((e.clientX - rect.left) / rect.width) * W,
          ((e.clientY - rect.top) / rect.height) * H,
          f,
        );
        if (hit) onSelect(hit[0], hit[1]);
      }}
    />
  );
}
