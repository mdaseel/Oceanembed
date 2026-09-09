import { expect, it, vi } from "vitest";
import * as THREE from "three";
import { prismTicks, createTemperaturePrism } from "../components/TemperaturePrism";
import { depthColor } from "../field/depthColors";

it("creates a world-space prism outside the ocean with the active palette", () => {
  const context=vi.spyOn(HTMLCanvasElement.prototype,"getContext").mockReturnValue({fillText:vi.fn()} as unknown as CanvasRenderingContext2D);
  try {
    const range={min:-4,max:4,actualMin:-3,actualMax:4,count:20};
    const model=createTemperaturePrism(range,"anomaly","thermal",0,-24);
    const mesh=model.children[0] as THREE.Mesh<THREE.BoxGeometry,THREE.MeshBasicMaterial[]>;
    expect(model.position.x-mesh.geometry.parameters.width/2).toBeGreaterThan(29);
    expect(model.position.y+mesh.geometry.parameters.height/2).toBe(0);
    expect(model.position.y-mesh.geometry.parameters.height/2).toBe(-24);
    const texture=mesh.material[4].map as THREE.DataTexture;
    const data=texture.image.data!;
    expect(Array.from(data.slice(0,3))).toEqual(depthColor(-4,range,"anomaly","thermal"));
    expect(Array.from(data.slice(-4,-1))).toEqual(depthColor(4,range,"anomaly","thermal"));
    expect(model.userData.ticks[3]).toBe(0);
    const separators=model.children.filter(o=>o.name==="legend-separator");
    expect(separators.map(o=>o.userData.value)).toEqual(model.userData.ticks);
    expect(separators).toHaveLength(7);
    const camera=new THREE.PerspectiveCamera(38,1,0.1,500);
    camera.position.set(76,49,62); camera.lookAt(0,-12,0); camera.updateMatrixWorld();
    const before=model.position.clone().project(camera);
    camera.position.set(62,49,76); camera.lookAt(0,-12,0); camera.updateMatrixWorld();
    expect(model.position.clone().project(camera).distanceTo(before)).toBeGreaterThan(.01);
  } finally { context.mockRestore(); }
});
it("derives seven descending ticks from the actual active range", () => {
  const ticks = prismTicks({min:6.091,max:32.452,actualMin:6.091,actualMax:32.452,count:20},"temperature");
  expect(ticks).toHaveLength(7);
  expect(ticks[0]).toBe(32.452);
  expect(ticks[6]).toBeCloseTo(6.091,12);
  expect(ticks.every((v,i)=>!i || v<ticks[i-1])).toBe(true);
});
it("includes anomaly zero and handles constant/missing scales honestly", () => {
  const range={min:-3.78,max:3.78,actualMin:-3.78,actualMax:2.1,count:20};
  const ticks=prismTicks(range,"anomaly");
  expect(ticks[3]).toBe(0);
  expect(ticks[0]).toBeCloseTo(-ticks[6],12);
  expect(prismTicks({...range,min:5,max:5},"temperature")).toEqual([5]);
  expect(prismTicks({...range,count:0},"anomaly")).toEqual([]);
});
