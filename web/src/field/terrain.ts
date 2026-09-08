/** Static DEM context. Never a FieldView, model mask, or predicted quantity. */
import * as THREE from "three";
import { position } from "./geometry";

export interface TerrainMetadata {
  schema: number;
  contextOnly: boolean;
  dataset: string;
  version: string;
  attribution: string;
  displayStepDegrees: number;
  vertices: number;
  triangles: number;
  maxElevationMetres: number;
  meshSha256: string;
}
export interface TerrainData {
  metadata: TerrainMetadata;
  coordinates: Float32Array;
  indices: Uint32Array;
}
let cached: Promise<TerrainData> | undefined;
export function loadTerrain(): Promise<TerrainData> {
  return cached ??= (async () => {
    const [metaResponse, meshResponse] = await Promise.all([
      fetch("/assets/terrain/metadata.json"),
      fetch("/assets/terrain/land.bin"),
    ]);
    if (!metaResponse.ok || !meshResponse.ok) throw new Error("Local DEM bundle missing");
    const metadata: TerrainMetadata = await metaResponse.json();
    const bytes = await meshResponse.arrayBuffer();
    if (metadata.schema !== 1 || !metadata.contextOnly ||
        !Number.isInteger(metadata.vertices) || metadata.vertices <= 0 ||
        !Number.isInteger(metadata.triangles) || metadata.triangles <= 0 ||
        bytes.byteLength !== metadata.vertices * 12 + metadata.triangles * 12)
      throw new Error("Invalid terrain bundle");
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)))
      .map(v => v.toString(16).padStart(2, "0")).join("");
    if (hash !== metadata.meshSha256) throw new Error("Terrain checksum mismatch");
    const coordinates = new Float32Array(bytes, 0, metadata.vertices * 3);
    const indices = new Uint32Array(bytes, metadata.vertices * 12, metadata.triangles * 3);
    for (let i = 0; i < coordinates.length; i += 3) {
      const [lon, lat, elevation] = coordinates.subarray(i, i + 3);
      if (![lon, lat, elevation].every(Number.isFinite) || lon < 45 || lon > 105 ||
          lat < 5 || lat > 30 || elevation < 0 || elevation > 9000)
        throw new Error("Invalid terrain coordinate");
    }
    if (indices.some(i => i >= metadata.vertices)) throw new Error("Invalid terrain index");
    return { metadata, coordinates, indices };
  })();
}

const smoothed = new WeakMap<TerrainData, Float32Array>();
/** One gentle adjacency pass on display heights. Keep the zero coastline fixed
 * and never connect across a water hole. Source DEM and horizontal positions
 * remain unchanged. This softens sampling spikes without inventing terrain.
 */
export function terrainDisplayHeights(data: TerrainData) {
  const cached = smoothed.get(data);
  if (cached) return cached;
  const heights = data.coordinates.filter((_, i) => i % 3 === 2);
  const sums = new Float64Array(heights.length);
  const counts = new Uint32Array(heights.length);
  for (let t = 0; t < data.indices.length; t += 3) {
    const a = data.indices[t], b = data.indices[t + 1], c = data.indices[t + 2];
    sums[a] += heights[b] + heights[c]; counts[a] += 2;
    sums[b] += heights[a] + heights[c]; counts[b] += 2;
    sums[c] += heights[a] + heights[b]; counts[c] += 2;
  }
  const result = heights.map((h, i) => h === 0 || counts[i] === 0 ? h :
    0.75 * h + 0.25 * sums[i] / counts[i]);
  smoothed.set(data, result);
  return result;
}

export function terrainGeometry(data: TerrainData, exaggeration: number) {
  const points = new Float32Array(data.coordinates.length);
  const heights = terrainDisplayHeights(data);
  for (let i = 0; i < points.length; i += 3) {
    const [lon, lat] = data.coordinates.subarray(i, i + 3);
    // Same horizontal mapping as OceanEmbed; independent positive DEM height.
    const [x, , z] = position(lon, lat, 0, 1);
    points.set([x, heights[i / 3] / 111000 * exaggeration, z], i);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(points, 3));
  geometry.setIndex(new THREE.BufferAttribute(data.indices, 1));
  geometry.computeVertexNormals();
  return geometry;
}
