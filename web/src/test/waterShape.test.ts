import { expect, it } from "vitest";
import { readFileSync } from "node:fs";
import * as THREE from "three";
import { adaptReplay } from "../field/replayAdapter";
import { planeGeometry, position } from "../field/geometry";
import { rangeFor } from "../field/colors";
import { waterShape } from "../field/waterShape";
const f = adaptReplay(JSON.parse(readFileSync("../outputs/phase7b/test-field.json", "utf8"))).field;
const data = planeGeometry(f, "temperature", 7, 700, rangeFor(f, "temperature", [7]), "thermal", -12);

it("curves water vertically only and keeps side thickness constant", () => {
  const original = data.positions.slice();
  const curve = waterShape(data.cells, f.lat.length, f.lon.length, .36);
  const curved = curve(original), bottom = original.slice();
  for (let i = 1; i < bottom.length; i += 3) bottom[i] -= .8;
  const curvedBottom = curve(bottom);
  let raised = false;
  for (let i = 0; i < original.length; i += 3) {
    expect(curved[i]).toBe(original[i]);
    expect(curved[i+2]).toBe(original[i+2]);
    expect(Math.abs(curved[i+1] - original[i+1])).toBeLessThanOrEqual(.360001);
    expect(curved[i+1] - curvedBottom[i+1]).toBeCloseTo(.8, 5);
    raised ||= curved[i+1] !== original[i+1];
  }
  expect(raised).toBe(true);
  expect(data.positions).toEqual(original);
  expect(waterShape(data.cells, f.lat.length, f.lon.length, 0)(original)).toEqual(original);
});

it("raycasts the curved geometry to the original scientific grid cell", () => {
  const curved = waterShape(data.cells, f.lat.length, f.lon.length, .36)(data.positions);
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(curved, 3));
  const material = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
  const mesh = new THREE.Mesh(geometry, material);
  const [x, , z] = position(65, 15, 0, 1);
  const ray = new THREE.Raycaster(new THREE.Vector3(x, 5, z), new THREE.Vector3(0,-1,0));
  const hit = ray.intersectObject(mesh)[0];
  expect(hit).toBeDefined();
  const cell = data.cells[Math.floor(hit.faceIndex! / 2)];
  expect(f.lat[Math.floor(cell/f.lon.length)]).toBe(15);
  expect(f.lon[cell%f.lon.length]).toBe(65);
  geometry.dispose(); material.dispose();
});
