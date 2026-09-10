import { depthColor } from "./depthColors";
import { offset, type FieldView, type Layer, type Palette } from "./contract";
import type { Range } from "./colors";

let relief: HTMLImageElement | null = null;
let pending: Promise<HTMLImageElement> | undefined;
export const currentMapRelief = () => relief;
export function loadMapRelief() {
  return pending ??= new Promise<HTMLImageElement>((resolve, reject) => {
    const image = new Image();
    image.onload = () => { relief = image; resolve(image); };
    image.onerror = () => reject(new Error("Local ETOPO map relief unavailable"));
    image.src = "/assets/terrain/map-relief.png";
  });
}

/** Land, missing input, or no finite model value. */
export const MISSING_RGB: [number, number, number] = [10, 22, 30];
/** Ocean with a real prediction, but no water column at the selected depth.
 * Neutral charcoal: deliberately unlike the cold end of every temperature ramp
 * (thermal 48,18,59 · viridis 68,1,84 · cividis 0,34,78) and lighter than the
 * missing-data colour, so "not applicable here" cannot be read as "cold". */
export const UNSUPPORTED_DEPTH_RGB: [number, number, number] = [48, 52, 58];

/** Bilinear scalar display resampling, gated by the ORIGINAL containing cell.
 * Missing/land pixels never receive invented values. Weights only use directly
 * adjacent supported cells. No model array or selection coordinate is changed.
 *
 * ``displayValid`` carries physical water-column support. It is supplied by the
 * caller from the SAME ``displayDepthValid`` utility the 3D renderer uses, so
 * the two views cannot disagree about where the seafloor is. A cell that fails
 * it keeps its raw value untouched and is merely drawn as unsupported, and it
 * is never smoothed into or out of, because a feathered edge would imply a
 * measurement in rock.
 */
export function mapRaster(f: FieldView, layer: Layer, depth: number, palette: Palette,
  range: Range, width: number, height: number,
  displayValid: (row: number, col: number) => boolean = () => true) {
  const out = new Uint8ClampedArray(width * height * 4);
  const nr = f.lat.length, nc = f.lon.length;
  const sample = (r: number, c: number) => {
    const cell = r*nc+c;
    return f.ocean[cell] && f.inputValid[cell] && displayValid(r,c)
      ? f[layer][offset(f,r,c,depth)] : NaN;
  };
  for (let y=0; y<height; y++) for (let x=0; x<width; x++) {
    const rr = nr - .5 - (y+.5)/height*nr, cc = (x+.5)/width*nc - .5;
    const r = Math.max(0,Math.min(nr-1,Math.round(rr)));
    const c = Math.max(0,Math.min(nc-1,Math.round(cc)));
    const cell = r*nc+c;
    let value = sample(r,c);
    // Three distinct outcomes, never merged: no data, no water column, a value.
    let rgb: number[] = f.ocean[cell] && f.inputValid[cell] && !displayValid(r,c)
      ? UNSUPPORTED_DEPTH_RGB as unknown as number[]
      : MISSING_RGB as unknown as number[];
    if (Number.isFinite(value)) {
      const r0 = Math.max(0,Math.min(nr-1,Math.floor(rr)));
      const c0 = Math.max(0,Math.min(nc-1,Math.floor(cc)));
      const r1 = Math.min(nr-1,r0+1), c1 = Math.min(nc-1,c0+1);
      const ry = Math.max(0,Math.min(1,rr-r0)), cx = Math.max(0,Math.min(1,cc-c0));
      const values = [sample(r0,c0), sample(r0,c1), sample(r1,c0), sample(r1,c1)];
      // Require full support: no smoothing across missing observations/coasts.
      if (values.every(Number.isFinite)) value = values[0]*(1-ry)*(1-cx) +
        values[1]*(1-ry)*cx + values[2]*ry*(1-cx) + values[3]*ry*cx;
      rgb = depthColor(value,range,layer,palette);
      // Feather the inside of coarse support edges; never color an unsupported
      // containing cell or invent values beyond the original scientific mask.
      const weights = [(1-ry)*(1-cx),(1-ry)*cx,ry*(1-cx),ry*cx];
      const coverage = values.reduce((sum,v,i) => sum + (Number.isFinite(v) ? weights[i] : 0),0);
      const t = Math.max(0,Math.min(1,(coverage-.4)/.6));
      const alpha = t*t*(3-2*t);
      rgb = rgb.map((v,i) => MISSING_RGB[i]*(1-alpha)+v*alpha);
    }
    const i = (y*width+x)*4;
    out.set([...rgb,255],i);
  }
  return out;
}
