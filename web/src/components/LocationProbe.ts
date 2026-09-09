import * as THREE from "three";
import { type FieldView, type Selection, isSupported } from "../field/contract";
import { DOMAIN, horizontalCos, position } from "../field/geometry";

/** A visual probe for the existing canonical selection; never resolves a new cell. */
export function createLocationProbe(f: FieldView, selection: Selection,
  surface: THREE.Mesh | undefined, bottomY: number) {
  const group = new THREE.Group();
  group.name = "selected-location-probe";
  const {row,col,status}=selection;
  if (status!=="OK" || row<0 || col<0 || row>=f.lat.length || col>=f.lon.length ||
      !isSupported(f,row,col) || !surface) return group;
  const cell=row*f.lon.length+col;
  const index=(surface.userData.cells as number[]).indexOf(cell);
  if (index<0) return group;
  // The canonical cell centre is on the shared diagonal of its two triangles.
  // Sample those actual deformed vertices, so the stem meets the drawn water.
  const vertices=surface.geometry.getAttribute("position");
  const y=(vertices.getY(index*6)+vertices.getY(index*6+2))/2;
  const [x,,z]=position(f.lon[col],f.lat[row],0,1);
  group.position.set(x,y,z);
  group.userData={cell,lat:f.lat[row],lon:f.lon[col]};
  const span=(DOMAIN.east-DOMAIN.west)*horizontalCos;
  const height=span*.038, bead=span*.0036, radius=span*.010;
  const cyan=new THREE.Color().setRGB(.07,.85,1);
  const material=new THREE.MeshBasicMaterial({color:cyan,toneMapped:false});
  const stem=new THREE.Mesh(new THREE.CylinderGeometry(span*.00065,span*.00065,height,12),material);
  stem.position.y=height/2; group.add(stem);
  const sphere=new THREE.Mesh(new THREE.SphereGeometry(bead,24,16),
    new THREE.MeshStandardMaterial({color:0xc9ffff,emissive:0x20d8ee,emissiveIntensity:1.1,roughness:.28,toneMapped:false}));
  sphere.position.y=height; group.add(sphere);
  const ring=new THREE.Mesh(new THREE.TorusGeometry(radius,span*.00065,8,64),
    new THREE.MeshBasicMaterial({color:cyan,transparent:true,opacity:.8,depthWrite:false,toneMapped:false}));
  ring.rotation.x=Math.PI/2; ring.position.y=.04; group.add(ring);
  // Soft local glow without bloom, lights, or continuous animation.
  const pixels=new Uint8Array(64*64*4);
  for(let r=0;r<64;r++) for(let c=0;c<64;c++) {
    const d=Math.hypot((r-31.5)/31.5,(c-31.5)/31.5);
    pixels.set([35,225,255,Math.round(100*Math.pow(Math.max(0,1-d),3))],(r*64+c)*4);
  }
  const glowTexture=new THREE.DataTexture(pixels,64,64); glowTexture.needsUpdate=true;
  const glow=new THREE.Sprite(new THREE.SpriteMaterial({map:glowTexture,transparent:true,depthWrite:false,toneMapped:false}));
  glow.scale.setScalar(bead*7); glow.position.y=height; group.add(glow);
  if(bottomY<y-.1) {
    const guide=new THREE.Line(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0,0,0),new THREE.Vector3(0,bottomY-y,0)]),
      new THREE.LineBasicMaterial({color:cyan,transparent:true,opacity:.14,depthWrite:false,toneMapped:false}));
    guide.renderOrder=100; group.add(guide);
  }
  group.traverse(object=>{object.renderOrder=100;});
  return group;
}
