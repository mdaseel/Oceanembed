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
  LAYER_GAP,
  layerLayout,
  planeGeometry,
  position,
  skirtGeometry,
  visibleLevels,
} from "../field/geometry";
import { Colorbar } from "./Colorbar";
import { MapView } from "./MapView";
import { Button } from "./ui/button";
import { loadTerrain, terrainGeometry, type TerrainData } from "../field/terrain";
import { landMaterial, oceanMaterial, smoothWaterColors } from "../field/surfaceMaterials";

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
  const [terrain, setTerrain] = useState<TerrainData | null>(null);
  const [terrainError, setTerrainError] = useState(false);
  const [terrainExaggeration, setTerrainExaggeration] = useState(75);
  useEffect(() => {
    let active = true;
    loadTerrain().then(data => { if (active) setTerrain(data); })
      .catch(() => { if (active) setTerrainError(true); });
    return () => { active = false; };
  }, []);
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
    // Soft key + fill so the land relief and slice stack read as solid surfaces
    // instead of flat colour. Lighting is presentation only: the ocean slices
    // stay MeshBasic so their colours remain the exact colormap values.
    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const key = new THREE.DirectionalLight(0xffffff, 2.1);
    key.position.set(-24, 40, 26);
    scene.add(key);
    const rim = new THREE.DirectionalLight(0xd5dae0, 0.8);
    rim.position.set(35, 8, 30);
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
    controls.maxDistance = 180;
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
      // Keep the western depth labels and the full footprint inside narrow
      // viewports. This changes the lens, never the geographic geometry.
      camera.fov = THREE.MathUtils.radToDeg(
        2 * Math.atan(
          Math.tan(THREE.MathUtils.degToRad(CAMERA.fov / 2)) *
            Math.max(1, 1.2 / camera.aspect),
        ),
      );
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
  const slab = 0.22;
  const ys = layerLayout(f.depths, levels, exaggeration, explode, gap);
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
      // Let the supported water footprint define each sheet, without a
      // rectangular wireframe cage around the land and missing-data regions.
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
      const fade = i === 0 ? 1 : Math.max(0.68, 0.9 - i * 0.055);
      const material = () =>
        new THREE.MeshBasicMaterial({
          vertexColors: true,
          side: THREE.DoubleSide,
          transparent: true,
          opacity: fade,
          depthWrite: false,
          toneMapped: false,
        });
      const waterGeometry = geometry({
        positions: data.positions,
        colors: smoothWaterColors(data, f.lat.length, f.lon.length),
      });
      const mesh = new THREE.Mesh(waterGeometry, oceanMaterial(fade, i === 0));
      if (selected) {
        // Only the selected sheet is pickable, and its geometry stays exactly
        // two triangles per grid cell — the click maths depends on that, so the
        // body below is always a SEPARATE mesh.
        mesh.name = "selected-depth";
        mesh.userData.cells = data.cells;
      }
      // Draw the deeper transparent sheets first. Selection must never move a
      // buried sheet visually in front of the surface.
      mesh.renderOrder = (levels.length - i) * 3 + 1;
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
        const wallMaterial = material();
        wallMaterial.opacity = fade * 0.25;
        const wall = new THREE.Mesh(geometry(body), wallMaterial);
        wall.name = selected ? "selected-depth-skirt" : "";
        wall.renderOrder = (levels.length - i) * 3;
        group.add(wall);
      }
    });

    // Real, static DEM context replaces the flat land extrusion. It has no
    // scientific field/mask dependency and is never included in point picking.
    if (terrain) {
      const landMesh = new THREE.Mesh(
        terrainGeometry(terrain, terrainExaggeration),
        landMaterial(),
      );
      landMesh.name = "dem-terrain";
      landMesh.position.y = ys[0];
      landMesh.renderOrder = 1;
      group.add(landMesh);
    }

    // NO container prism. An enclosing box around the whole stack was tried and
    // removed: it reads as an aquarium, adds base volume the data does not
    // have, and buries the vertical separation that is the whole point of the
    // view. The water footprint itself defines each sheet.
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
    terrain,
    terrainExaggeration,
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
          onClick={() => {
            const controls = controlRef.current;
            if (!controls) return;
            // Flush residual orbit momentum before restoring the saved pose.
            controls.enableDamping = false;
            controls.update();
            controls.reset();
            controls.update();
            controls.enableDamping = true;
          }}
        >
          Reset camera
        </Button>
      </div>
      <div ref={host} className="depth-renderer" data-testid="depth-renderer" />
      {terrain ? (
        <div className="three-toolbar" data-testid="terrain-context">
          <label className="small muted">
            Terrain relief vertically exaggerated for visualization · {terrainExaggeration}×
            <input aria-label="Terrain relief exaggeration" type="range" min="20" max="150" step="5"
              value={terrainExaggeration} onChange={e => setTerrainExaggeration(Number(e.target.value))} />
          </label>
          <span className="small muted">{terrain.metadata.dataset} · NOAA NCEI · static geographic context</span>
        </div>
      ) : (
        <p className="muted small" role="status">
          {terrainError ? "Terrain unavailable: build the local DEM bundle using scripts/poc/build_terrain.py. Ocean data remain available."
            : "Loading local elevation context…"}
        </p>
      )}
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
          ? "Colors span all 15 depths of this date. Depths share one scale; compare dates using their displayed ranges."
          : "Colors are auto-stretched to the visible depth band only: high contrast within this band, but NOT comparable with another depth or date."}{" "}
        Every sheet is one of the 15 mandated levels, drawn at that level only —
        nothing is interpolated between them and no volume is drawn in the gaps.
        Ocean sheets have constant display thickness on an identical geographic
        footprint. The separate land terrain uses real DEM elevations above sea
        level, with display-only exaggeration. Its finer coastline may differ
        from the scientific ocean mask; neither that mask nor any field or
        export value is modified. Terrain is geographic context, not an
        OceanEmbed prediction. Terrain relief is gently smoothed for display,
        with its coastline fixed. Water uses display-only color smoothing
        within supported regions and illustrative ripple shading, not measured waves;
        values are read from the scale and profile.
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
  ctx.font = "34px system-ui";
  ctx.fillText(text, 3, 34);
  const texture = new THREE.CanvasTexture(canvas),
    material = new THREE.SpriteMaterial({ map: texture, depthTest: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(13, 2.44, 1);
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
