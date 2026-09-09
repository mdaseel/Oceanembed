import { expect, it } from "vitest";
import { mapRaster } from "../field/mapAppearance";
import { depthColor } from "../field/depthColors";
import type { FieldView } from "../field/contract";
const range = { min:0,max:30,actualMin:0,actualMax:30,count:4 };
function field(): FieldView {
  return { lat:new Float64Array([5,5.25]),lon:new Float64Array([45,45.25]),
    depths:[0],temperature:new Float64Array([0,10,20,30]),
    ocean:new Uint8Array([1,1,1,1]),inputValid:new Uint8Array([1,1,1,1]),
  } as unknown as FieldView; // minimal raster-only fixture; no inference contract validation
}
it("interpolates display pixels while preserving exact field values", () => {
  const f=field(), original=f.temperature.slice();
  const pixels=mapRaster(f,"temperature",0,"thermal",range,3,3);
  expect(Array.from(pixels.slice(16,19))).toEqual(depthColor(15,range,"temperature","thermal"));
  expect(f.temperature).toEqual(original);
});
it("does not fill unsupported cells or interpolate through a missing neighbor", () => {
  const f=field(); f.inputValid[3]=0;
  const pixels=mapRaster(f,"temperature",0,"thermal",range,3,3);
  expect(Array.from(pixels.slice(16,20))).toEqual([10,22,30,255]);
  expect(f.inputValid[3]).toBe(0);
  f.ocean.fill(0);
  expect(Array.from(mapRaster(f,"temperature",0,"thermal",range,1,1))).toEqual([10,22,30,255]);
});
