import * as THREE from "three";
import { DOMAIN, position } from "../field/geometry";
import { OCEAN_VISUAL_CONFIG as V } from "../field/visualConfig";

/** Edges only: no panels, field geometry, or picking targets. */
export function createStackFrame(levels:number[], ys:number[], selected:number, thickness:number) {
  const group=new THREE.Group(); group.name="stack-frame";
  const [x0,,z0]=position(DOMAIN.west,DOMAIN.south,0,1);
  const [x1,,z1]=position(DOMAIN.east,DOMAIN.north,0,1);
  const corners=[[x0,z0],[x1,z0],[x1,z1],[x0,z1]];
  const perimeter=(y:number)=>corners.map(([x,z])=>new THREE.Vector3(x,y,z));
  levels.forEach((level,i)=>{
    const active=level===selected;
    const frame=new THREE.Group(); frame.userData={level,selected:active};
    const points=perimeter(ys[i]); points.push(points[0].clone());
    frame.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),
      new THREE.LineBasicMaterial({color:active?V.selectedOutlineColor:V.normalOutlineColor,
        transparent:true,opacity:active?V.selectedOutlineIntensity:V.outlineOpacity,depthWrite:false,toneMapped:false})));
    if(active) {
      const material=new THREE.MeshBasicMaterial({color:V.selectedOutlineColor,transparent:true,
        opacity:V.selectedOutlineIntensity*.75,depthWrite:false,toneMapped:false});
      for(let j=0;j<4;j++) {
        const a=points[j],b=points[j+1],delta=b.clone().sub(a);
        const edge=new THREE.Mesh(new THREE.CylinderGeometry(V.selectedOutlineRadius,V.selectedOutlineRadius,delta.length(),6),material);
        edge.position.copy(a).add(b).multiplyScalar(.5);
        edge.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),delta.normalize()); frame.add(edge);
      }
    }
    frame.renderOrder=90; frame.traverse(o=>o.renderOrder=90); group.add(frame);
  });
  if(ys.length) {
    const bottom=ys[ys.length-1]-thickness;
    const points=perimeter(bottom); points.push(points[0].clone());
    const lines:THREE.Vector3[]=[];
    for(let j=0;j<4;j++) lines.push(points[j],points[j+1],new THREE.Vector3(corners[j][0],ys[0],corners[j][1]),points[j]);
    group.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(lines),
      new THREE.LineBasicMaterial({color:V.normalOutlineColor,transparent:true,opacity:V.cornerOpacity,depthWrite:false,toneMapped:false})));
  }
  return group;
}
