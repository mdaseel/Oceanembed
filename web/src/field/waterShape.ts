/** Presentation-only water curvature. Ocean values and nominal depths are not
 * inputs. CPU deformation keeps rendering and raycast picking on the same mesh.
 */
import { horizontalCos } from "./geometry";

export function waterShape(cells: number[], rows: number, cols: number, amplitude: number) {
  const supported = new Uint8Array(rows * cols);
  cells.forEach(cell => { supported[cell] = 1; });
  const distance = Float32Array.from(supported, v => v ? rows + cols : 0);
  for (let r = 0; r < rows; r++) for (let c = 0; c < cols; c++) {
    const i = r * cols + c;
    if (r) distance[i] = Math.min(distance[i], distance[i-cols]+1);
    if (c) distance[i] = Math.min(distance[i], distance[i-1]+1);
  }
  for (let r = rows-1; r >= 0; r--) for (let c = cols-1; c >= 0; c--) {
    const i = r * cols + c;
    if (r+1 < rows) distance[i] = Math.min(distance[i], distance[i+cols]+1);
    if (c+1 < cols) distance[i] = Math.min(distance[i], distance[i+1]+1);
  }
  return (positions: Float32Array) => {
    const result = positions.slice();
    for (let i = 0; i < result.length; i += 3) {
      const x = positions[i], z = positions[i+2];
      const cv = Math.round((x / horizontalCos + 30.125) / .25);
      const rv = Math.round((12.625 - z) / .25);
      let shoreDistance = 3;
      for (const r of [rv-1, rv]) for (const c of [cv-1, cv]) {
        if (r >= 0 && c >= 0 && r < rows && c < cols)
          shoreDistance = Math.min(shoreDistance, distance[r*cols+c]);
      }
      // Fix coastline/missing-data edges to their nominal sheet height; the
      // open-ocean crop boundary may curve, so thickness reads from the side.
      const t = Math.min(1, shoreDistance / 3);
      const taper = t*t*(3-2*t);
      const wave = .72*Math.sin(x*.72+z*.38) + .28*Math.cos(z*.91-x*.27);
      result[i+1] += amplitude * taper * wave;
    }
    return result;
  };
}
