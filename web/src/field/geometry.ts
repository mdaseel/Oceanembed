import {
  isSupported,
  offset,
  type FieldView,
  type Layer,
  type Palette,
} from "./contract";
import { color, type Range } from "./colors";
// Local equirectangular context, 1 scene unit = 111 km; depth in physical metres.
export const horizontalCos = Math.cos((17.5 * Math.PI) / 180);
/**
 * Default camera for the shared 3D renderer. Exported so the renderer and any
 * test that needs to project a world point into screen space use the SAME
 * constants — duplicating them let a camera tweak silently break a calibrated
 * click test.
 */
export const CAMERA = {
  fov: 38,
  // Look along the long east-west axis, with enough elevation to reveal the
  // land silhouette and each slab's top. No geographic scaling is involved.
  position: [76, 49, 62] as const,
  target: [0, -12, 0] as const,
  near: 0.1,
  far: 500,
};
export const position = (
  lon: number,
  lat: number,
  metres: number,
  exaggeration: number,
): [number, number, number] => [
  (lon - 75) * horizontalCos,
  (-metres / 111000) * exaggeration,
  17.5 - lat,
];
/**
 * Vertical separation between fully exploded sheets, in scene units. Exported
 * so the renderer and any test that projects a sheet into screen space use the
 * SAME constant — duplicating it would let a spacing tweak silently break the
 * click calibration, which is exactly how the earlier camera constants broke.
 */
export const LAYER_GAP = 6;
/** Scene height of a depth in metres, at the current vertical exaggeration. */
export const depthY = (metres: number, exaggeration: number) =>
  (-metres / 111000) * exaggeration;
/** Cell-edge extent of the canonical domain, used for the layer outlines. */
export const DOMAIN = {
  west: 44.875,
  east: 105.125,
  south: 4.875,
  north: 30.125,
};
/**
 * Vertical placement of each visible level — the exploded-view layout.
 *
 * `explode = 0` places every layer at its **true depth**: the y axis is then
 * readable as metres and the returned values are exactly `depthY`.
 *
 * `explode = 1` spaces the layers **evenly**, which is what makes a 0 m and a
 * 1000 m sheet both legible in one frame — the true spacing crams eleven of the
 * fifteen levels into the top fifth of the axis. At any explode above zero the
 * vertical position is a legibility device and is **no longer readable as
 * depth**. The view must say so, and every layer keeps its own metre label, so
 * the depth of each sheet stays stated rather than inferred from its height.
 *
 * Order is always preserved: a deeper level never rises above a shallower one.
 */
export function layerLayout(
  depths: readonly number[],
  levels: number[],
  exaggeration: number,
  explode: number,
  gap: number,
): number[] {
  if (!levels.length) return [];
  const top = depthY(depths[levels[0]], exaggeration);
  return levels.map((k, i) => {
    const trueY = depthY(depths[k], exaggeration);
    return trueY * (1 - explode) + (top - i * gap) * explode;
  });
}
/**
 * Choose which levels the exploded stack shows: `count` of them, evenly spaced
 * across the clip band, with the band's own ends always anchored and the
 * selected level always present. Every level remains reachable through the
 * depth scrubber and the profile — this only governs how many sheets are drawn
 * at once, because a readable stack is four to six, not fifteen.
 */
export function visibleLevels(
  clip: [number, number],
  count: number,
  selected: number,
): number[] {
  const [lo, hi] = clip;
  const span = hi - lo;
  if (span <= 0) return [lo];
  const n = Math.max(2, Math.min(count, span + 1));
  const picked = new Set<number>();
  for (let i = 0; i < n; i++)
    picked.add(lo + Math.round((i * span) / (n - 1)));
  if (selected >= lo && selected <= hi && !picked.has(selected)) {
    let nearest = -1,
      best = Infinity;
    for (const k of picked) {
      if (k === lo || k === hi) continue;
      const d = Math.abs(k - selected);
      if (d < best) {
        best = d;
        nearest = k;
      }
    }
    if (nearest >= 0) picked.delete(nearest);
    picked.add(selected);
  }
  return [...picked].sort((a, b) => a - b);
}
/**
 * Outline of one layer's slab: the domain rectangle at `y`, the same rectangle
 * at `y - thickness`, and the four corner uprights. Drawn as thin lines, this
 * is the "glass edge" of a sheet — it carries no data, and it is identical for
 * every layer because every layer has the **same geographic footprint**.
 */
export function frameGeometry(y: number, thickness: number) {
  const { west, east, south, north } = DOMAIN;
  const x0 = (west - 75) * horizontalCos,
    x1 = (east - 75) * horizontalCos,
    z0 = 17.5 - north,
    z1 = 17.5 - south;
  const corners: [number, number][] = [
    [x0, z0],
    [x1, z0],
    [x1, z1],
    [x0, z1],
  ];
  const vertices: number[] = [];
  for (const level of [y, y - thickness])
    for (let i = 0; i < 4; i++) {
      const a = corners[i],
        b = corners[(i + 1) % 4];
      vertices.push(a[0], level, a[1], b[0], level, b[1]);
    }
  for (const [x, z] of corners)
    vertices.push(x, y, z, x, y - thickness, z);
  return { positions: new Float32Array(vertices) };
}
export function planeGeometry(
  f: FieldView,
  layer: Layer,
  depth: number,
  exaggeration: number,
  range: Range,
  palette: Palette,
  /** Scene height to draw this layer at. Omitted = its true depth. */
  y?: number,
  colorFn: typeof color = color,
) {
  const baseY = y ?? depthY(f.depths[depth], exaggeration);
  const vertices: number[] = [],
    colors: number[] = [],
    cells: number[] = [];
  const corners = [
    [-0.125, -0.125],
    [0.125, -0.125],
    [0.125, 0.125],
    [-0.125, -0.125],
    [0.125, 0.125],
    [-0.125, 0.125],
  ];
  for (let r = 0; r < f.lat.length; r++)
    for (let c = 0; c < f.lon.length; c++) {
      const value = f[layer][offset(f, r, c, depth)];
      if (!isSupported(f, r, c) || !Number.isFinite(value)) continue;
      const rgb = colorFn(value, range, layer, palette).map((x) => x / 255);
      for (const [dx, dy] of corners) {
        vertices.push(
          (f.lon[c] + dx - 75) * horizontalCos,
          baseY,
          17.5 - (f.lat[r] + dy),
        );
        colors.push(...rgb);
      }
      cells.push(r * f.lon.length + c);
    }
  return {
    positions: new Float32Array(vertices),
    colors: new Float32Array(colors),
    cells,
  };
}
/**
 * Land geometry for spatial context.
 *
 * Land is `ocean_mask === 0` — the frozen store's own definition ("the GLORYS
 * target is defined at the shallowest level"). It is drawn in a neutral slate,
 * NEVER coloured by temperature, and it carries no elevation: this is a
 * land/sea distinction from the model-ready store, not a topography product.
 * It exists so the volume is recognisable as the North Indian Ocean rather
 * than a floating rectangle.
 */
export function landGeometry(
  f: FieldView,
  depth: number,
  exaggeration: number,
  /**
   * Slab thickness in scene units. CONSTANT for every land cell — it is a
   * drawing device that gives the landmass a visible edge against the ocean
   * surface, and it encodes NO elevation. Land is not extruded by height
   * because we have no topography source; every land cell is exactly as thick
   * as every other.
   */
  thickness = 0.55,
  /** Scene height of the slab base. Omitted = the layer's true depth. */
  y?: number,
) {
  const baseY = y ?? depthY(f.depths[depth], exaggeration);
  const vertices: number[] = [];
  const normals: number[] = [];
  const nlon = f.lon.length;
  // An edge of the cropped map is not a coastline. Extrude only boundaries
  // between actual land and ocean cells, never the rectangular domain edge.
  const isOcean = (r: number, c: number) =>
    r >= 0 && c >= 0 && r < f.lat.length && c < nlon &&
    Boolean(f.ocean[r * nlon + c]);
  const quad = (
    a: [number, number, number],
    b: [number, number, number],
    c2: [number, number, number],
    d: [number, number, number],
    n: [number, number, number],
  ) => {
    vertices.push(...a, ...b, ...c2, ...a, ...c2, ...d);
    for (let i = 0; i < 6; i++) normals.push(...n);
  };

  for (let r = 0; r < f.lat.length; r++)
    for (let c = 0; c < nlon; c++) {
      if (f.ocean[r * nlon + c]) continue;
      const lon = f.lon[c];
      const lat = f.lat[r];
      const at = (dx: number, dy: number, lift: number) =>
        [
          (lon + dx - 75) * horizontalCos,
          baseY + lift,
          17.5 - (lat + dy),
        ] as [number, number, number];
      const t = thickness;
      // top face
      quad(at(-0.125, -0.125, t), at(0.125, -0.125, t), at(0.125, 0.125, t),
           at(-0.125, 0.125, t), [0, 1, 0]);
      // No backing or underside. Top cells preserve every island and water
      // hole exactly; coastline walls start at the ocean surface.
      if (isOcean(r, c + 1))
        quad(at(0.125, -0.125, t), at(0.125, -0.125, 0), at(0.125, 0.125, 0),
             at(0.125, 0.125, t), [1, 0, 0]);
      if (isOcean(r, c - 1))
        quad(at(-0.125, 0.125, t), at(-0.125, 0.125, 0), at(-0.125, -0.125, 0),
             at(-0.125, -0.125, t), [-1, 0, 0]);
      if (isOcean(r + 1, c))
        quad(at(-0.125, 0.125, t), at(0.125, 0.125, t), at(0.125, 0.125, 0),
             at(-0.125, 0.125, 0), [0, 0, -1]);
      if (isOcean(r - 1, c))
        quad(at(-0.125, -0.125, 0), at(0.125, -0.125, 0), at(0.125, -0.125, t),
             at(-0.125, -0.125, t), [0, 0, 1]);
    }
  return {
    positions: new Float32Array(vertices),
    normals: new Float32Array(normals),
    thickness,
  };
}
/**
 * Downward skirt for the selected slice, so the displayed layer reads as a
 * body of water with thickness rather than a sheet of paper.
 *
 * Like the land slab this is a CONSTANT depth for every cell. Temperature is
 * never encoded as height — the y axis means depth in metres and nothing else,
 * and a warm cell is not drawn thicker than a cold one. Walls are emitted only
 * where a supported cell borders an unsupported one (coastline, domain edge or
 * data gap), so the interior stays one flat sheet and the triangle count stays
 * proportional to the perimeter, not the area.
 *
 * The lower edge is drawn at 55% brightness of the cell's true colormap colour.
 * That is shading on a vertical face, not a second data channel: the top face,
 * which is the surface being read, keeps the exact colormap value.
 */
export function skirtGeometry(
  f: FieldView,
  layer: Layer,
  depth: number,
  exaggeration: number,
  range: Range,
  palette: Palette,
  thickness = 0.5,
  /** Scene height of the layer's top face. Omitted = its true depth. */
  y?: number,
  colorFn: typeof color = color,
) {
  const baseY = y ?? depthY(f.depths[depth], exaggeration);
  const vertices: number[] = [];
  const colors: number[] = [];
  const nlon = f.lon.length;
  const shown = (r: number, c: number) =>
    r >= 0 &&
    c >= 0 &&
    r < f.lat.length &&
    c < nlon &&
    isSupported(f, r, c) &&
    Number.isFinite(f[layer][offset(f, r, c, depth)]);
  for (let r = 0; r < f.lat.length; r++)
    for (let c = 0; c < nlon; c++) {
      if (!shown(r, c)) continue;
      const top = colorFn(
        f[layer][offset(f, r, c, depth)],
        range,
        layer,
        palette,
      ).map((x) => x / 255);
      const low = top.map((x) => x * 0.55);
      const at = (dx: number, dy: number, drop: number) =>
        [
          (f.lon[c] + dx - 75) * horizontalCos,
          baseY - drop,
          17.5 - (f.lat[r] + dy),
        ] as [number, number, number];
      const wall = (
        dx1: number,
        dy1: number,
        dx2: number,
        dy2: number,
      ) => {
        const a = at(dx1, dy1, 0),
          b = at(dx2, dy2, 0),
          c2 = at(dx2, dy2, thickness),
          d = at(dx1, dy1, thickness);
        vertices.push(...a, ...b, ...c2, ...a, ...c2, ...d);
        colors.push(...top, ...top, ...low, ...top, ...low, ...low);
      };
      if (!shown(r, c + 1)) wall(0.125, -0.125, 0.125, 0.125);
      if (!shown(r, c - 1)) wall(-0.125, 0.125, -0.125, -0.125);
      if (!shown(r + 1, c)) wall(0.125, 0.125, -0.125, 0.125);
      if (!shown(r - 1, c)) wall(-0.125, -0.125, 0.125, -0.125);
    }
  return {
    positions: new Float32Array(vertices),
    colors: new Float32Array(colors),
    thickness,
  };
}
/** Outline of the ocean/land boundary, drawn as line segments at one depth. */
export function coastlineGeometry(
  f: FieldView,
  depth: number,
  exaggeration: number,
  /** Scene height to draw at. Omitted = the layer's true depth. */
  yOverride?: number,
) {
  const vertices: number[] = [];
  const nlon = f.lon.length;
  const isLand = (r: number, c: number) =>
    r < 0 || c < 0 || r >= f.lat.length || c >= nlon
      ? true
      : !f.ocean[r * nlon + c];
  const baseY = yOverride ?? depthY(f.depths[depth], exaggeration);
  const at = (lon: number, lat: number): [number, number, number] => [
    (lon - 75) * horizontalCos,
    baseY,
    17.5 - lat,
  ];
  for (let r = 0; r < f.lat.length; r++)
    for (let c = 0; c < nlon; c++) {
      if (isLand(r, c)) continue;
      const lat = f.lat[r];
      const lon = f.lon[c];
      // emit an edge wherever an ocean cell touches land
      if (isLand(r, c + 1))
        vertices.push(
          ...at(lon + 0.125, lat - 0.125),
          ...at(lon + 0.125, lat + 0.125),
        );
      if (isLand(r, c - 1))
        vertices.push(
          ...at(lon - 0.125, lat - 0.125),
          ...at(lon - 0.125, lat + 0.125),
        );
      if (isLand(r + 1, c))
        vertices.push(
          ...at(lon - 0.125, lat + 0.125),
          ...at(lon + 0.125, lat + 0.125),
        );
      if (isLand(r - 1, c))
        vertices.push(
          ...at(lon - 0.125, lat - 0.125),
          ...at(lon + 0.125, lat - 0.125),
        );
    }
  return { positions: new Float32Array(vertices) };
}
/** A stacked translucent slice at one depth — gives the stack volume. */
export function sliceGeometry(
  f: FieldView,
  layer: Layer,
  depth: number,
  exaggeration: number,
  range: Range,
  palette: Palette,
  y?: number,
) {
  return planeGeometry(f, layer, depth, exaggeration, range, palette, y);
}
export function depthPoints(
  f: FieldView,
  layer: Layer,
  depths: number[],
  exaggeration: number,
  range: Range,
  palette: Palette,
) {
  const vertices: number[] = [],
    colors: number[] = [];
  for (const k of depths)
    for (let r = 0; r < f.lat.length; r++)
      for (let c = 0; c < f.lon.length; c++) {
        const value = f[layer][offset(f, r, c, k)];
        if (!isSupported(f, r, c) || !Number.isFinite(value)) continue;
        vertices.push(
          ...position(f.lon[c], f.lat[r], f.depths[k], exaggeration),
        );
        colors.push(...color(value, range, layer, palette).map((x) => x / 255));
      }
  return {
    positions: new Float32Array(vertices),
    colors: new Float32Array(colors),
  };
}
