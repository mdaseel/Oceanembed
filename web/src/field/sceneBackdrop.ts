import * as THREE from "three";
import { OCEAN_VISUAL_CONFIG as V } from "./visualConfig";
/** Small static backdrop texture; no postprocessing or per-frame work. */
export function sceneBackdrop() {
  const size=256, pixels=new Uint8Array(size*size*4);
  const rgb=(hex:string)=>[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
  const center=rgb(V.backgroundCenter),edge=rgb(V.backgroundEdge);
  for(let y=0;y<size;y++) for(let x=0;x<size;x++) {
    const u=(x/(size-1)-.48)*2,v=(y/(size-1)-.53)*2;
    const radial=Math.min(1,Math.hypot(u,v)/1.2);
    const mix=Math.pow(1-radial,1.25);
    const halo=Math.exp(-3.2*(u*u+v*v*.65))*V.haloIntensity;
    for(let c=0;c<3;c++) pixels[(y*size+x)*4+c]=Math.round(
      (edge[c]+(center[c]-edge[c])*mix+[4,24,42][c]*halo)*(1-V.vignetteStrength*radial*radial));
    pixels[(y*size+x)*4+3]=255;
  }
  const texture=new THREE.DataTexture(pixels,size,size);
  texture.colorSpace=THREE.LinearSRGBColorSpace;
  texture.minFilter=texture.magFilter=THREE.LinearFilter;
  texture.needsUpdate=true;
  return texture;
}
