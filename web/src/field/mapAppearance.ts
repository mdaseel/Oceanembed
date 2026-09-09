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

/** Bilinear scalar display resampling, gated by the ORIGINAL containing cell.
 * Missing/land pixels never receive invented values. Weights only use directly
 * adjacent supported cells. No model array or selection coordinate is changed.
 */
export function mapRaster(f: FieldView, layer: Layer, depth: number, palette: Palette,
  range: Range, width: number, height: number) {
  const out = new Uint8ClampedArray(width * height * 4);
  const nr = f.lat.length, nc = f.lon.length;
  const sample = (r: number, c: number) => {
    const cell = r*nc+c;
    return f.ocean[cell] && f.inputValid[cell] ? f[layer][offset(f,r,c,depth)] : NaN;
  };
  for (let y=0; y<height; y++) for (let x=0; x<width; x++) {
    const rr = nr - .5 - (y+.5)/height*nr, cc = (x+.5)/width*nc - .5;
    const r = Math.max(0,Math.min(nr-1,Math.round(rr)));
    const c = Math.max(0,Math.min(nc-1,Math.round(cc)));
    let value = sample(r,c);
    let rgb = [10,22,30];
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
      rgb = rgb.map((v,i) => [10,22,30][i]*(1-alpha)+v*alpha);
    }
    const i = (y*width+x)*4;
    out.set([...rgb,255],i);
  }
  return out;
}
