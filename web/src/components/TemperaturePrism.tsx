import * as THREE from "three";
import type { Layer, Palette } from "../field/contract";
import type { Range } from "../field/colors";
import { depthColor } from "../field/depthColors";

export function prismTicks(range: Range, layer: Layer) {
  if (!range.count || !Number.isFinite(range.min) || !Number.isFinite(range.max)) return [];
  if (range.min === range.max) return [range.min];
  return Array.from({ length: 7 }, (_, i) =>
    layer === "anomaly" && i === 3 ? 0 : range.max+(range.min-range.max)*i/6);
}

/** Physical legend in the same scene and camera as the ocean, outside its footprint. */
export function createTemperaturePrism(range: Range, layer: Layer, palette: Palette,
  surfaceY: number, bottomY: number) {
  const group = new THREE.Group();
  group.name = "temperature-prism";
  const ticks = prismTicks(range,layer);
  if (!ticks.length) return group;
  const height = Math.max(10, Math.abs(surfaceY-bottomY));
  group.position.set(34, surfaceY-height/2, -17);
  group.userData = { legend:true, ticks, title:layer === "anomaly" ? "Temperature Anomaly (°C)" : "Temperature (°C)" };
  const pixels = new Uint8Array(1024*4);
  for (let i=0;i<1024;i++) pixels.set([
    ...depthColor(range.min+(range.max-range.min)*i/1023,range,layer,palette),255],i*4);
  const texture = new THREE.DataTexture(pixels,1,1024,THREE.RGBAFormat);
  texture.magFilter = texture.minFilter = THREE.LinearFilter;
  texture.colorSpace = THREE.LinearSRGBColorSpace; texture.needsUpdate = true;
  const face = (shade:number) => new THREE.MeshBasicMaterial({map:texture,
    color:new THREE.Color().setRGB(shade,shade,shade),toneMapped:false});
  const cap = (value:number, shade:number) => {
    const rgb=depthColor(value,range,layer,palette);
    return new THREE.MeshBasicMaterial({color:new THREE.Color().setRGB(
      rgb[0]/255*shade,rgb[1]/255*shade,rgb[2]/255*shade),toneMapped:false});
  };
  const geometry = new THREE.BoxGeometry(3.2,height,3.2);
  group.add(new THREE.Mesh(geometry,[face(.76),face(.76),cap(range.max,.88),cap(range.min,.6),face(1),face(.85)]));
  group.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry),
    new THREE.LineBasicMaterial({color:0x7194a5,transparent:true,opacity:.32})));
  const heading = label(layer === "anomaly" ? "Temp. Anomaly (°C)" : "Temperature (°C)", 14, true);
  heading.position.set(0,height/2+2.5,0); group.add(heading);
  const caption = label("COLOR LEGEND",8,true);
  caption.position.set(0,-height/2-1.4,0); group.add(caption);
  for (const value of ticks) {
    const t = range.min===range.max ? .5 : (value-range.min)/(range.max-range.min);
    const text = label(value===0 ? "0" : value.toFixed(2),8);
    text.position.set(2.5,t*height-height/2,-1.6); group.add(text);
    const line = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(1.6,t*height-height/2,-1.6),new THREE.Vector3(2.3,t*height-height/2,-1.6)]);
    group.add(new THREE.Line(line,new THREE.LineBasicMaterial({color:0x9bb3c2,transparent:true,opacity:.6})));
  }
  return group;
}

function label(text:string, width:number, centered=false) {
  const canvas = document.createElement("canvas"); canvas.width=512; canvas.height=80;
  const ctx=canvas.getContext("2d")!;
  ctx.fillStyle="#dce8ee"; ctx.font=centered ? "46px system-ui" : "60px system-ui";
  ctx.textAlign=centered ? "center" : "left";
  ctx.fillText(text,centered ? 256 : 4,54);
  const texture=new THREE.CanvasTexture(canvas);
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,depthWrite:false,toneMapped:false}));
  sprite.scale.set(width,width*80/512,1); sprite.center.set(centered ? .5 : 0,.5);
  return sprite;
}
