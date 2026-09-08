/** Display-only surface finishes. No displacement, model values or masks. */
import * as THREE from "three";

/** Interpolate display RGB only inside fully supported four-cell patches.
 * Geometry, cell ordering, masks and scientific scalar arrays remain intact.
 */
export function smoothWaterColors(data: { colors: Float32Array; cells: number[] }, rows: number, cols: number) {
  const index = new Int32Array(rows * cols).fill(-1);
  data.cells.forEach((cell, i) => { index[cell] = i; });
  const colors = data.colors.slice();
  const corners = [[-1,-1],[1,-1],[1,1],[-1,-1],[1,1],[-1,1]];
  data.cells.forEach((cell, i) => {
    const row = Math.floor(cell / cols), col = cell % cols;
    corners.forEach(([dx, dy], v) => {
      const r = row + dy, c = col + dx;
      if (r < 0 || c < 0 || r >= rows || c >= cols) return;
      const neighbors = [index[cell], index[row * cols + c], index[r * cols + col], index[r * cols + c]];
      if (neighbors.some(n => n < 0)) return;
      for (let channel = 0; channel < 3; channel++) {
        colors[i * 18 + v * 3 + channel] = neighbors.reduce(
          (sum, n) => sum + data.colors[n * 18 + channel], 0) / 4;
      }
    });
  });
  return colors;
}

export function oceanMaterial(opacity: number, surface: boolean, cells: number[], rows: number, cols: number) {
  const support = new Uint8Array(rows * cols);
  cells.forEach(cell => { support[cell] = 255; });
  const edgeMask = new THREE.DataTexture(support, cols, rows, THREE.RedFormat);
  edgeMask.minFilter = edgeMask.magFilter = THREE.LinearFilter;
  edgeMask.needsUpdate = true;
  const material = new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.DoubleSide, transparent: true,
    opacity, depthWrite: false, toneMapped: false,
  });
  material.addEventListener("dispose", () => edgeMask.dispose());
  material.onBeforeCompile = shader => {
    shader.uniforms.waterSupport = { value: edgeMask };
    shader.vertexShader = "varying vec3 vSurfacePosition;\n" + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>",
      "#include <begin_vertex>\nvSurfacePosition = (modelMatrix * vec4(position, 1.0)).xyz;");
    shader.fragmentShader = `varying vec3 vSurfacePosition;
      uniform sampler2D waterSupport;
      float waterHash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
      float waterNoise(vec2 p) {
        vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
        return mix(mix(waterHash(i),waterHash(i+vec2(1.,0.)),f.x),
                   mix(waterHash(i+vec2(0.,1.)),waterHash(i+vec2(1.,1.)),f.x),f.y);
      }
      float waterDetail(vec2 p) {
        return 0.55 * waterNoise(p * 1.7) + 0.30 * waterNoise(p * 4.8 + 17.0)
             + 0.15 * waterNoise(p * 12.0 + 31.0);
      }
    ` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace("#include <color_fragment>", `
      #include <color_fragment>
      // Irregular optical micro-relief, never measured waves or displaced depth.
      vec2 p = vSurfacePosition.xz;
      float detail = waterDetail(p);
      vec2 slope = vec2(waterDetail(p + vec2(0.045,0.0)) - detail,
                        waterDetail(p + vec2(0.0,0.045)) - detail) / 0.045;
      vec3 opticalNormal = normalize(vec3(-slope.x * 0.32, 1.0, -slope.y * 0.32));
      vec3 eye = normalize(cameraPosition - vSurfacePosition);
      float grazing = pow(1.0 - abs(dot(opticalNormal, eye)), 3.0);
      float glint = pow(max(0.0, dot(reflect(-normalize(vec3(0.5, 1.0, 0.5)), opticalNormal), eye)), 18.0);
      float strength = ${surface ? "1.0" : "0.4"};
      diffuseColor.rgb *= 1.0 - strength * (0.09 - 0.12 * detail);
      float sheen = min(0.13, grazing * 0.08 + glint * 0.12) * strength;
      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.85, 0.94, 1.0), sheen);
      // Feather only within existing triangles; never draw into masked cells.
      vec2 supportUV = vec2((p.x / 0.95371695075 + 30.125) / 60.25,
                            (12.625 - p.y) / 25.25);
      diffuseColor.a *= smoothstep(0.25, 0.75, texture2D(waterSupport, supportUV).r);
    `);
  };
  material.customProgramCacheKey = () => `ocean-microrelief-v4-${surface}`;
  return material;
}

export function landMaterial() {
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color().setRGB(0.17, 0.18, 0.19, THREE.LinearSRGBColorSpace),
    roughness: 0.95, metalness: 0,
    side: THREE.DoubleSide,
  });
  return material;
}
