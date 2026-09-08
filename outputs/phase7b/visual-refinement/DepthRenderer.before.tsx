import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import {
  type FieldView,
  type Layer,
  type Palette,
  type Selection,
} from "../field/contract";
import { rangeFor, type ScaleMode } from "../field/colors";
import {
  CAMERA,
  coastlineGeometry,
  frameGeometry,
  LAYER_GAP,
  landGeometry,
  layerLayout,
  planeGeometry,
  position,
  skirtGeometry,
  visibleLevels,
} from "../field/geometry";
import { Colorbar } from "./Colorbar";
import { MapView } from "./MapView";
import { Button } from "./ui/button";

export interface DepthRendererProps {
  field: FieldView;
  layer: Layer;
  depth: number;
  palette: Palette;
  selection: Selection;
  exaggeration: number;
  clip: [number, number];
  scaleMode: ScaleMode;
  /**
   * 0 = every sheet at its true depth, so height reads as metres.
   * 1 = sheets evenly separated, which is the only way a 0 m and a 1000 m sheet
   * are both legible in one frame. Above 0 the vertical position is a drawing
   * device and the view says so.
   */
  explode: number;
  /** How many sheets the stack draws at once. Four to six stays readable. */
  layerCount: number;
  onSelect: (lat: number, lon: number) => void;
}
/** Canonical reusable renderer. No replay import, transport, filesystem or inference. */
export default function DepthRenderer(props: DepthRendererProps) {
  const host = useRef<HTMLDivElement>(null);
  const controlRef = useRef<OrbitControls | null>(null);
  const sceneData = useRef<{
    group: THREE.Group;
    camera: THREE.PerspectiveCamera;
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
  } | null>(null);
  const latest = useRef(props);
  latest.current = props;
  const [failed, setFailed] = useState(false),
    [fps, setFps] = useState<number | null>(null);
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!host.current) return;
    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({
        antialias: true,
        powerPreference: "high-performance",
      });
    } catch {
      setFailed(true);
      return;
    }
    const element = host.current;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.5));
    renderer.outputColorSpace = THREE.LinearSRGBColorSpace;
    element.appendChild(renderer.domElement);
    renderer.domElement.setAttribute(
      "aria-label",
      "3D depth field. Drag to orbit, right-drag to pan, scroll to zoom; click the slice to select a column.",
    );
    renderer.domElement.dataset.testid = "depth-canvas";
    const scene = new THREE.Scene();
    scene.background = new THREE.Color().setRGB(5 / 255, 7 / 255, 11 / 255);
    scene.fog = new THREE.Fog(0x05070b, 90, 230);
    // Soft key + fill so the land relief and slice stack read as solid surfaces
    // instead of flat colour. Lighting is presentation only: the ocean slices
    // stay MeshBasic so their colours remain the exact colormap values.
    scene.add(new THREE.AmbientLight(0xbfd4ee, 1.15));
    const key = new THREE.DirectionalLight(0xffffff, 1.35);
    key.position.set(-24, 40, 26);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0x5fd6e8, 0.5);
    rim.position.set(30, 12, -30);
    scene.add(rim);
    const camera = new THREE.PerspectiveCamera(
      CAMERA.fov,
      1,
      CAMERA.near,
      CAMERA.far,
    );
    camera.position.set(...CAMERA.position);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.minDistance = 8;
    controls.maxDistance = 120;
    controls.maxPolarAngle = Math.PI * 0.88;
    controls.target.set(...CAMERA.target);
    controls.update();
    controls.saveState();
    controlRef.current = controls;
    const group = new THREE.Group();
    scene.add(group);
    sceneData.current = { group, camera, renderer, scene };
    const resize = new ResizeObserver(() => {
      const w = element.clientWidth,
        h = element.clientHeight;
      renderer.setSize(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    });
    resize.observe(element);
    let frame = 0,
      frames = 0,
      start = performance.now();
    const loop = (now: number) => {
      controls.update();
      renderer.render(scene, camera);
      frames++;
      if (now - start >= 1500) {
        setFps((frames * 1000) / (now - start));
        start = now;
        frames = 0;
      }
      frame = requestAnimationFrame(loop);
    };
    frame = requestAnimationFrame(loop);
    let downX = 0,
      downY = 0;
    const down = (e: PointerEvent) => {
      downX = e.clientX;
      downY = e.clientY;
    };
    const up = (e: PointerEvent) => {
      if (
        e.button !== 0 ||
        Math.hypot(e.clientX - downX, e.clientY - downY) > 5
      )
        return;
      const rect = renderer.domElement.getBoundingClientRect();
      const ray = new THREE.Raycaster();
      ray.setFromCamera(
        new THREE.Vector2(
          ((e.clientX - rect.left) / rect.width) * 2 - 1,
          (-(e.clientY - rect.top) / rect.height) * 2 + 1,
        ),
        camera,
      );
      const mesh = group.getObjectByName("selected-depth");
      if (!mesh) return;
      const hit = ray.intersectObject(mesh)[0];
      if (hit?.faceIndex != null) {
        const cell = mesh.userData.cells[Math.floor(hit.faceIndex / 2)],
          f = latest.current.field;
        latest.current.onSelect(
          f.lat[Math.floor(cell / f.lon.length)],
          f.lon[cell % f.lon.length],
        );
      }
    };
    const lost = (e: Event) => {
      e.preventDefault();
      setFailed(true);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("webglcontextlost", lost);
    setReady(true);
    return () => {
      cancelAnimationFrame(frame);
      resize.disconnect();
      controls.dispose();
      disposeGroup(group);
      renderer.dispose();
      renderer.domElement.removeEventListener("webglcontextlost", lost);
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointerup", up);
      renderer.domElement.remove();
      sceneData.current = null;
      controlRef.current = null;
    };
  }, []);
  const {
    field: f,
    layer,
    depth,
    exaggeration,
    clip,
    palette,
    scaleMode,
    explode,
    layerCount,
  } = props;
  const band = f.depths
    .map((_, k) => k)
    .filter((k) => k >= clip[0] && k <= clip[1]);
  // The colour scale reads the whole band (or the whole field), not just the
  // sheets currently drawn, so thinning the stack never rescales the colours.
  const range = rangeFor(f, layer, band, scaleMode);
  const levels = visibleLevels(clip, layerCount, depth);
  // Even gap between exploded sheets, and a THIN slab body — a stack reads as
  // layers when the gap dominates the thickness. Both are constant for every
  // cell of every layer: they are drawing devices, and no cell is ever made
  // thicker, higher or lower by its value.
  const gap = LAYER_GAP;
  const slab = gap * 0.13;
  const ys = layerLayout(f.depths, levels, exaggeration, explode, gap);
  const yOf = (k: number) => ys[levels.indexOf(k)];
  useEffect(() => {
    if (!sceneData.current) return;
    const { group } = sceneData.current;
    disposeGroup(group);
    // --- The exploded stack ---------------------------------------------
    // Each visible level is one thin floating sheet: a glass plate spanning the
    // identical geographic footprint, the data drawn on its top face, and a
    // constant-thickness body so it reads as a slab and not as paper. Nothing
    // is interpolated between levels and no volume is drawn between them — the
    // gaps are honestly empty, and they are a legibility device, not distance.
    levels.forEach((k, i) => {
      const y = ys[i];
      const selected = k === depth;
      // Glass plate: the full domain rectangle, carrying NO data. It exists so
      // every layer shows the same footprint even where a sheet has few
      // supported cells, and so the stack reads as sheets rather than clouds.
      const frame = frameGeometry(y, slab);
      const fg = new THREE.BufferGeometry();
      fg.setAttribute("position", new THREE.BufferAttribute(frame.positions, 3));
      const outline = new THREE.LineSegments(
        fg,
        new THREE.LineBasicMaterial({
          color: new THREE.Color().setRGB(
            0.36,
            0.62,
            0.78,
            THREE.LinearSRGBColorSpace,
          ),
          transparent: true,
          opacity: selected ? 0.5 : 0.22,
        }),
      );
      outline.renderOrder = -1;
      group.add(outline);
      const data = planeGeometry(
        f,
        layer,
        k,
        exaggeration,
        range,
        palette,
        y,
      );
      if (!data.positions.length) return;
      // Deeper sheets fade, so the stack has aerial depth without hiding any
      // level. Opacity is presentation only and never alters a colormap value.
      const fade = selected
        ? 1
        : Math.max(0.34, 0.62 - 0.05 * Math.abs(i - levels.indexOf(depth)));
      const material = () =>
        new THREE.MeshBasicMaterial({
          vertexColors: true,
          side: THREE.DoubleSide,
          transparent: !selected,
          opacity: fade,
          depthWrite: selected,
        });
      const mesh = new THREE.Mesh(geometry(data), material());
      if (selected) {
        // Only the selected sheet is pickable, and its geometry stays exactly
        // two triangles per grid cell — the click maths depends on that, so the
        // body below is always a SEPARATE mesh.
        mesh.name = "selected-depth";
        mesh.userData.cells = data.cells;
      }
      mesh.renderOrder = selected ? 2 : 0;
      group.add(mesh);
      const body = skirtGeometry(
        f,
        layer,
        k,
        exaggeration,
        range,
        palette,
        slab,
        y,
      );
      if (body.positions.length) {
        const wall = new THREE.Mesh(geometry(body), material());
        wall.name = selected ? "selected-depth-skirt" : "";
        wall.renderOrder = selected ? 2 : 0;
        group.add(wall);
      }
    });

    // --- Land, for spatial context -------------------------------------
    // ocean_mask === 0, drawn neutral, never coloured by temperature and with
    // no elevation implied. It makes the volume recognisable as the North
    // Indian Ocean instead of a floating rectangle.
    // Thin, and sitting ON the topmost sheet — the reference is explicit that
    // land is "slightly extruded" and must not become a thick border wall.
    const landThickness = slab * 1.3;
    const land = landGeometry(
      f,
      levels[0],
      exaggeration,
      landThickness,
      ys[0],
    );
    if (land.positions.length) {
      const lg = new THREE.BufferGeometry();
      lg.setAttribute("position", new THREE.BufferAttribute(land.positions, 3));
      lg.setAttribute("normal", new THREE.BufferAttribute(land.normals, 3));
      const landMesh = new THREE.Mesh(
        lg,
        // Near-black landmass raised above the ocean slab, as in the reference.
        // Form comes entirely from LIGHTING — the lit top face against the
        // unlit side walls is what makes the slab read as a solid block. It is
        // deliberately not tinted: colour would suggest land cover we do not
        // have, and the slab is constant-thickness so it implies no elevation.
        //
        // The colours are declared in LINEAR space on purpose. The renderer
        // outputs LinearSRGBColorSpace so that the MeshBasic ocean slices emit
        // the colormap RGB byte-for-byte; a plain sRGB hex here would be
        // converted into that working space and come out gamma-crushed to near
        // black, which is what a hex literal did.
        new THREE.MeshLambertMaterial({
          color: new THREE.Color().setRGB(
            0.105,
            0.11,
            0.12,
            THREE.LinearSRGBColorSpace,
          ),
          emissive: new THREE.Color().setRGB(
            0.008,
            0.009,
            0.011,
            THREE.LinearSRGBColorSpace,
          ),
        }),
      );
      landMesh.name = "land";
      landMesh.position.y += 0.02;
      landMesh.renderOrder = 1;
      group.add(landMesh);
    }
    const coast = coastlineGeometry(f, levels[0], exaggeration, ys[0]);
    if (coast.positions.length) {
      const cg = new THREE.BufferGeometry();
      cg.setAttribute("position", new THREE.BufferAttribute(coast.positions, 3));
      const coastline = new THREE.LineSegments(
        cg,
        new THREE.LineBasicMaterial({
          // Linear, for the same reason as the land material above.
          color: new THREE.Color().setRGB(
            0.62,
            0.79,
            0.9,
            THREE.LinearSRGBColorSpace,
          ),
          transparent: true,
          opacity: 0.85,
        }),
      );
      coastline.name = "coastline";
      // sit on top of the raised land slab, not inside it
      coastline.position.y += landThickness + 0.03;
      coastline.renderOrder = 3;
      group.add(coastline);
    }

    // NO container prism. An enclosing box around the whole stack was tried and
    // removed: it reads as an aquarium, adds base volume the data does not
    // have, and buries the vertical separation that is the whole point of the
    // view. Each sheet carries its own outline instead.
    //
    // Every sheet is labelled with its OWN true depth in metres. That matters
    // most when the stack is exploded, because a layer's height is then a
    // legibility device rather than a measurement — the label, not the
    // position, is what states the depth.
    levels.forEach((k, i) => {
      const label = textSprite(`${f.depths[k]} m`);
      label.position.set(-36, ys[i], 13);
      group.add(label);
    });
    for (const [text, lon, lat] of [
      ["45°E", 45, 5],
      ["75°E", 75, 5],
      ["105°E", 105, 5],
      ["30°N", 45, 30],
    ] as const) {
      const label = textSprite(text);
      const [x, , z] = position(lon, lat, 0, exaggeration);
      label.position.set(x, ys[0], z + 1.2);
      group.add(label);
    }
    // No plumb line through the stack. It was drawn with depthTest off, so it
    // painted over every sheet and the land, and it cut across the very
    // separation the exploded view exists to show. The selected column is still
    // reported by the 2D map marker, the lat/lon fields and the vertical
    // profile panel, none of which obstruct the stack.
    //
    // range and levels derive wholly from these inputs.
  }, [
    f,
    layer,
    depth,
    exaggeration,
    clip[0],
    clip[1],
    palette,
    scaleMode,
    explode,
    layerCount,
    ready,
    // `selection` is deliberately absent: nothing in the scene depends on it
    // any more, and leaving it here rebuilt every sheet's geometry on each
    // click. `props.selection` still reaches the 2D fallback below.
  ]);
  if (failed)
    return (
      <div>
        <p className="notice" role="status">
          3D view unavailable on this device. The 2D map, depth controls and
          full profile remain available.
        </p>
        <MapView {...props} />
      </div>
    );
  return (
    <>
      <div className="three-toolbar">
        <span>Drag to orbit · right-drag to pan · scroll / pinch to zoom</span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => controlRef.current?.reset()}
        >
          Reset camera
        </Button>
      </div>
      <div ref={host} className="depth-renderer" data-testid="depth-renderer" />
      <div className="three-footer">
        <span>
          {levels.length} of 15 levels shown ·{" "}
          {levels.map((k) => f.depths[k]).join(" / ")} m · selected{" "}
          {f.depths[depth]} m · vertical exaggeration {exaggeration}×
        </span>
        <span data-testid="fps">
          {fps === null ? "Measuring frame rate…" : `${fps.toFixed(1)} fps`}
        </span>
      </div>
      <Colorbar range={range} layer={layer} palette={palette} />
      {explode > 0 && (
        <p className="notice" role="status" data-testid="explode-notice">
          <strong>Exploded view — vertical spacing is not to scale.</strong> The
          sheets are separated so all of them are legible at once; eleven of the
          fifteen levels sit in the top fifth of the real depth axis. Each sheet
          is labelled with its own true depth, and the vertical profile, the CSV
          and the NetCDF export all use true depths. Set separation to 0 for the
          true-depth layout.
        </p>
      )}
      <p className="muted small">
        {scaleMode === "field"
          ? "Colors span the whole reconstruction — all 15 depths of this date — so every depth and date is directly comparable."
          : "Colors are auto-stretched to the visible depth band only: high contrast within this band, but NOT comparable with another depth or date."}{" "}
        Every sheet is one of the 15 mandated levels, drawn at that level only —
        nothing is interpolated between them and no volume is drawn in the gaps.
        The sheets and the land are slabs of <strong>constant</strong> thickness
        on an <strong>identical</strong> geographic footprint: the thickness is a
        drawing device so a layer reads in 3D, and it encodes no elevation,
        bathymetry or temperature. This is not a topography product.
      </p>
    </>
  );
}
function geometry(data: { positions: Float32Array; colors: Float32Array }) {
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(data.positions, 3));
  g.setAttribute("color", new THREE.BufferAttribute(data.colors, 3));
  return g;
}
function textSprite(text: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 48;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#d9e5f5";
  ctx.font = "26px system-ui";
  ctx.fillText(text, 3, 34);
  const texture = new THREE.CanvasTexture(canvas),
    material = new THREE.SpriteMaterial({ map: texture, depthTest: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(9, 1.69, 1);
  return sprite;
}
function disposeGroup(group: THREE.Group) {
  group.traverse((object) => {
    const item = object as THREE.Mesh;
    item.geometry?.dispose();
    if (item.material)
      for (const material of Array.isArray(item.material)
        ? item.material
        : [item.material]) {
        (material as THREE.SpriteMaterial).map?.dispose();
        material.dispose();
      }
  });
  group.clear();
}
