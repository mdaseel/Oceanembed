import { readFileSync } from "node:fs";
import { it, expect } from "vitest";
import * as THREE from "three";
import { adaptReplay } from "../field/replayAdapter";
import { resolve, profile } from "../field/contract";
import { planeGeometry, position } from "../field/geometry";
import { rangeFor } from "../field/colors";
import { waterShape } from "../field/waterShape";
import { createLocationProbe } from "../components/LocationProbe";
it("anchors the profile's canonical cell to the actual surface without changing science",()=>{
  const f=adaptReplay(JSON.parse(readFileSync("../outputs/phase7b/test-field.json","utf8"))).field;
  const before=f.temperature.slice();
  const data=planeGeometry(f,"temperature",0,700,rangeFor(f,"temperature",[0],"field"),"thermal",0);
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute("position",new THREE.BufferAttribute(waterShape(data.cells,f.lat.length,f.lon.length,.36)(data.positions),3));
  const mesh=new THREE.Mesh(geometry); mesh.userData.cells=data.cells;
  for(const [lat,lon] of [[15.02,65.03],[12,70]]) {
    const s=resolve(f,lat,lon), probe=createLocationProbe(f,s,mesh,-24);
    expect(probe.children.length).toBeGreaterThan(0);
    expect(probe.userData.cell).toBe(s.row*f.lon.length+s.col);
    const [x,,z]=position(f.lon[s.col],f.lat[s.row],0,700);
    expect(probe.position.x).toBe(x); expect(probe.position.z).toBe(z);
    expect(profile(f,s)[0].temperature).toBe(f.temperature[probe.userData.cell*15]);
    const deeper=createLocationProbe(f,s,mesh,-36);
    expect(deeper.position.toArray()).toEqual(probe.position.toArray());
    const i=data.cells.indexOf(probe.userData.cell)*6;
    expect(probe.position.y).toBe((geometry.attributes.position.getY(i)+geometry.attributes.position.getY(i+2))/2);
  }
  for(const status of ["OUTSIDE_DOMAIN","INVALID_OCEAN_CELL","INPUT_NOT_VALID"] as const)
    expect(createLocationProbe(f,{...resolve(f,15,65),status},mesh,-24).children).toHaveLength(0);
  expect(f.temperature).toEqual(before);
});
