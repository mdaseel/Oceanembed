import { useEffect, useState } from "react";
import { type FieldView, isSupported } from "./contract";
export interface Bathymetry { depths: Float64Array; metadata: {dataset:string;version:string;lat:number[];lon:number[];depthSha256:string;schema:number} }
let cached: Promise<Bathymetry> | undefined;
export function loadBathymetry(): Promise<Bathymetry> {
  return cached ??= (async()=>{
    const [meta,bin]=await Promise.all([fetch("/assets/bathymetry/metadata.json"),fetch("/assets/bathymetry/depth.bin")]);
    if(!meta.ok || !bin.ok) throw Error("Local bathymetry unavailable");
    const metadata=await meta.json(),bytes=await bin.arrayBuffer();
    if(metadata.schema!==1 || bytes.byteLength!==101*241*8 ||
       metadata.lat?.length!==101 || metadata.lon?.length!==241 ||
       metadata.lat.some((v:number,i:number)=>v!==5+i*.25) ||
       metadata.lon.some((v:number,i:number)=>v!==45+i*.25)) throw Error("Noncanonical bathymetry grid");
    const hash=Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256",bytes))).map(v=>v.toString(16).padStart(2,"0")).join("");
    if(hash!==metadata.depthSha256) throw Error("Bathymetry checksum mismatch");
    const view=new DataView(bytes);
    const depths=Float64Array.from({length:101*241},(_,i)=>view.getFloat64(i*8,true));
    if(depths.some(v=>v<0 || v===Infinity || v===-Infinity)) throw Error("Invalid bathymetry depth");
    return {metadata,depths};
  })();
}
export function useBathymetry() {
  const [data,setData]=useState<Bathymetry|null>(null),[error,setError]=useState(false);
  useEffect(()=>{let active=true;loadBathymetry().then(d=>{if(active)setData(d);}).catch(()=>{if(active)setError(true);});return()=>{active=false;};},[]);
  return {data,error};
}
/** Additional DISPLAY support only; no L0 support or model values are inputs. */
export function displayDepthValid(f:FieldView,b:Bathymetry|null,row:number,col:number,depth:number) {
  if(!b || row<0 || col<0 || row>=f.lat.length || col>=f.lon.length || !isSupported(f,row,col)) return false;
  const waterDepth=b.depths[row*f.lon.length+col];
  return Number.isFinite(waterDepth) && waterDepth>=depth;
}
