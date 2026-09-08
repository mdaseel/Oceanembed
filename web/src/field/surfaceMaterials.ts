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

export function oceanMaterial(opacity: number, surface: boolean) {
  const material = new THREE.MeshBasicMaterial({
    vertexColors: true, side: THREE.DoubleSide, transparent: true,
    opacity, depthWrite: false, toneMapped: false,
  });
  material.onBeforeCompile = shader => {
    shader.vertexShader = "varying vec3 vSurfacePosition;\n" + shader.vertexShader;
    shader.vertexShader = shader.vertexShader.replace("#include <begin_vertex>",
      "#include <begin_vertex>\nvSurfacePosition = (modelMatrix * vec4(position, 1.0)).xyz;");
    shader.fragmentShader = `varying vec3 vSurfacePosition;
      float waterHash(vec2 p) { return fract(sin(dot(p, vec2(127.1,311.7))) * 43758.5453); }
      float waterNoise(vec2 p) {
        vec2 i = floor(p), f = fract(p); f = f*f*(3.0-2.0*f);
        return mix(mix(waterHash(i),waterHash(i+vec2(1.,0.)),f.x),
                   mix(waterHash(i+vec2(0.,1.)),waterHash(i+vec2(1.,1.)),f.x),f.y);
      }
    ` + shader.fragmentShader;
    shader.fragmentShader = shader.fragmentShader.replace("#include <color_fragment>", `
      #include <color_fragment>
      // Stationary wave-like normals/shading, not measured waves or geometry.
      vec2 p = vSurfacePosition.xz;
      float phase = p.x * 2.6 + p.y * 3.8 + 5.0 * waterNoise(p * 0.65);
      float finePhase = p.x * 7.3 - p.y * 4.1 + 6.0 * waterNoise(p * 0.9 + 30.0);
      float longRipple = sin(phase);
      float fineRipple = sin(finePhase);
      vec3 opticalNormal = normalize(vec3(
        0.22 * cos(phase) + 0.07 * cos(finePhase), 1.0,
        0.16 * cos(phase) - 0.04 * cos(finePhase)));
      vec3 eye = normalize(cameraPosition - vSurfacePosition);
      float grazing = pow(1.0 - abs(dot(opticalNormal, eye)), 3.0);
      float glint = pow(max(0.0, dot(reflect(-normalize(vec3(0.5, 1.0, 0.5)), opticalNormal), eye)), 18.0);
      float strength = ${surface ? "1.0" : "0.22"};
      diffuseColor.rgb *= 1.0 - strength * (0.055 + 0.045 * longRipple + 0.015 * fineRipple);
      float sheen = min(0.12, grazing * 0.10 + glint * 0.12) * strength;
      diffuseColor.rgb = mix(diffuseColor.rgb, vec3(0.85, 0.94, 1.0), sheen);
    `);
  };
  material.customProgramCacheKey = () => `ocean-ripples-v3-${surface}`;
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
