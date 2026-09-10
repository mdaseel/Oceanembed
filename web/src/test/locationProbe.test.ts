import { readFileSync } from "node:fs";
import { it, expect } from "vitest";
import * as THREE from "three";
import { adaptReplay } from "../field/replayAdapter";
import { resolve, profile } from "../field/contract";
import { planeGeometry, position, visibleLevels, layerLayout, LAYER_GAP } from "../field/geometry";
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
    const s=resolve(f,lat,lon), probe=createLocationProbe(f,s,mesh,mesh);
    expect(probe.children.length).toBeGreaterThan(0);
    expect(probe.userData.cell).toBe(s.row*f.lon.length+s.col);
    const [x,,z]=position(f.lon[s.col],f.lat[s.row],0,700);
    expect(probe.position.x).toBe(x); expect(probe.position.z).toBe(z);
    expect(profile(f,s)[0].temperature).toBe(f.temperature[probe.userData.cell*15]);
    const deeper=createLocationProbe(f,s,mesh,undefined);
    expect(deeper.position.toArray()).toEqual(probe.position.toArray());
    const i=data.cells.indexOf(probe.userData.cell)*6;
    expect(probe.position.y).toBe((geometry.attributes.position.getY(i)+geometry.attributes.position.getY(i+2))/2);
  }
  for(const status of ["OUTSIDE_DOMAIN","INVALID_OCEAN_CELL","INPUT_NOT_VALID"] as const)
    expect(createLocationProbe(f,{...resolve(f,15,65),status},mesh,undefined).children).toHaveLength(0);
  expect(f.temperature).toEqual(before);
});

it("ends at the actual selected sheet, withholds invalid extent and follows separation",()=>{
  const f=adaptReplay(JSON.parse(readFileSync("../outputs/phase7b/test-field.json","utf8"))).field;
  const s=resolve(f,15,65),range=rangeFor(f,"temperature",[0,14],"field");
  const make=(k:number,y:number)=>{
    const data=planeGeometry(f,"temperature",k,700,range,"thermal",y);
    const geometry=new THREE.BufferGeometry();
    geometry.setAttribute("position",new THREE.BufferAttribute(data.positions,3));
    const mesh=new THREE.Mesh(geometry);mesh.userData.cells=data.cells;return mesh;
  };
  const top=make(0,0);
  for(const separation of [0,.5,1]) for(const k of [0,4,7,11,14]) {
    const levels=visibleLevels([0,14],5,k),ys=layerLayout(f.depths,levels,700,separation,LAYER_GAP);
    const target=make(k,ys[levels.indexOf(k)]);
    const probe=createLocationProbe(f,s,top,target);
    expect(probe.position.x).toBe(position(65,15,0,1)[0]);
    expect(probe.position.z).toBe(position(65,15,0,1)[2]);
    expect(probe.userData.endpointY).toBeCloseTo(ys[levels.indexOf(k)],5);
    const guides=probe.children.filter(o=>o.name==="probe-column-guide");
    if(k===0) expect(guides).toHaveLength(0);
    else {
      expect(guides).toHaveLength(2);
      for(const guide of guides) {
        const mesh=guide as THREE.Mesh<THREE.CylinderGeometry>;
        expect(probe.position.y+mesh.position.y-mesh.geometry.parameters.height/2).toBeCloseTo(probe.userData.endpointY,5);
      }
    }
  }
  const missing=make(14,-24);missing.userData.cells=[];
  const invalid=createLocationProbe(f,s,top,missing);
  expect(invalid.children.filter(o=>o.name==="probe-column-guide")).toHaveLength(0);
  expect(invalid.userData.depthValid).toBe(false);
});
