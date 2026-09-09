import { it, expect } from "vitest";
import * as THREE from "three";
import { createStackFrame } from "../components/StackFrame";
import { visibleLevels, layerLayout, LAYER_GAP } from "../field/geometry";
import { DEPTHS } from "../field/contract";
import { OCEAN_VISUAL_CONFIG as V } from "../field/visualConfig";
it("highlights only the exact selected depth across all 15 levels using edges only",()=>{
  for(let selected=0;selected<DEPTHS.length;selected++) {
    const levels=visibleLevels([0,14],5,selected);
    const ys=layerLayout(DEPTHS,levels,700,1,LAYER_GAP);
    const before=[...ys];
    const frame=createStackFrame(levels,ys,selected,.8);
    const active=frame.children.filter(o=>o.userData.selected);
    expect(active).toHaveLength(1); expect(active[0].userData.level).toBe(selected);
    for(const child of frame.children.filter(o=>o instanceof THREE.Group)) {
      const line=child.children[0] as THREE.Line<THREE.BufferGeometry,THREE.LineBasicMaterial>;
      expect(line.material.color.getHex()).toBe(child.userData.selected?V.selectedOutlineColor:V.normalOutlineColor);
      expect(line.material.opacity).toBe(child.userData.selected?V.selectedOutlineIntensity:V.outlineOpacity);
    }
    expect(ys).toEqual(before);
    expect(frame.children.at(-1)).toBeInstanceOf(THREE.LineSegments);
  }
});
