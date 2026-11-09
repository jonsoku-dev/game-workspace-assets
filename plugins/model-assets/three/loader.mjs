import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';

export { THREE };

export function validateReceipt(receipt, byteLength) {
  if (receipt?.contract?.id !== 'webstage-asset' || receipt.contract.version !== '1.0' ||
      receipt.ok !== true || receipt.kind !== 'gltf' || receipt.output?.bytes !== byteLength || typeof receipt.output.path !== 'string' || !receipt.output.path ||
      !Array.isArray(receipt.violations) || receipt.violations.length !== 0) {
    throw new Error('Expected successful webstage-asset/1.0 gltf receipt matching GLB byte length');
  }
}

export function inspectContainer(buffer, { textures = false, animated = false } = {}) {
  const view = new DataView(buffer);
  if (buffer.byteLength < 20 || view.getUint32(0, true) !== 0x46546c67 ||
      view.getUint32(4, true) !== 2 || view.getUint32(8, true) !== buffer.byteLength ||
      view.getUint32(16, true) !== 0x4e4f534a) throw new Error('Expected GLB version 2');
  const length = view.getUint32(12, true);
  if (20 + length > buffer.byteLength) throw new Error('Truncated GLB JSON');
  const json = JSON.parse(new TextDecoder().decode(new Uint8Array(buffer, 20, length)));
  if (!Number.isInteger(json.scene) || !json.scenes?.[json.scene]) throw new Error('Expected an explicit default scene');
  for (const entry of [...(json.buffers ?? []), ...(json.images ?? [])]) {
    if (entry.uri !== undefined) throw new Error('External or URI resources are forbidden; embed all resources in GLB');
  }
  if ((json.extensionsUsed ?? []).some(name => ['KHR_draco_mesh_compression', 'KHR_texture_basisu'].includes(name))) {
    throw new Error('Draco and KTX2 require unsupported external decoders');
  }
  if (json.images?.length && !textures) throw new Error('Node inspection supports untextured GLBs only; use browser verification for embedded PNG/JPEG');
  for (const image of json.images ?? []) {
    if (!Number.isInteger(image.bufferView) || !['image/png', 'image/jpeg'].includes(image.mimeType)) {
      throw new Error('Only embedded PNG/JPEG textures are supported');
    }
  }
  if (json.skins?.length) throw new Error('Skinned meshes are unsupported; use rigid part hierarchies');
  if (json.animations?.length && !animated) throw new Error('Only static meshes are supported');
  const paths = new Set(['translation', 'rotation', 'scale']);
  for (const animation of json.animations ?? []) {
    if (typeof animation.name !== 'string' || !animation.name) throw new Error('Animations must be named');
    for (const channel of animation.channels ?? []) {
      const node = json.nodes?.[channel.target?.node];
      if (!Number.isInteger(channel.target?.node) || !node || typeof node.name !== 'string' || !node.name) {
        throw new Error(`Animation ${animation.name} targets a missing or unnamed node`);
      }
      if (!paths.has(channel.target.path)) throw new Error('Only rigid translation/rotation/scale animation is supported');
      const sampler = animation.samplers?.[channel.sampler];
      if (!sampler || !['LINEAR', 'STEP', 'CUBICSPLINE', undefined].includes(sampler.interpolation)) {
        throw new Error(`Animation ${animation.name} has an invalid sampler`);
      }
    }
  }
  for (const mesh of json.meshes ?? []) {
    for (const primitive of mesh.primitives ?? []) {
      if ((primitive.mode ?? 4) !== 4 || primitive.targets?.length) throw new Error('Only static triangle primitives are supported');
    }
  }
  return json;
}

export async function loadModel(buffer, options) {
  const source = inspectContainer(buffer, options);
  const manager = new THREE.LoadingManager();
  manager.setURLModifier(url => {
    if (url.startsWith('blob:')) return url;
    throw new Error('Network and external resources are forbidden');
  });
  const loader = new GLTFLoader(manager).setMeshoptDecoder(MeshoptDecoder);
  if (options?.imagePlugin) loader.register(options.imagePlugin);
  const gltf = await loader.parseAsync(buffer, '');
  const scene = gltf.scene;
  if (!scene || !gltf.scenes.length) throw new Error('GLB has no default scene');
  scene.updateMatrixWorld(true);
  let meshCount = 0, vertexCount = 0, triangleCount = 0;
  const materials = new Set();
  let texturedMeshCount = 0;
  const uvSamples = new Set();
  scene.traverse(object => {
    if (object.isLine || object.isPoints) throw new Error('Only triangle meshes are supported');
    if (!object.isMesh) return;
    if (object.isSkinnedMesh) throw new Error('Skinned meshes are outside the static model scope');
    const geometry = object.geometry;
    const position = geometry.getAttribute('position');
    if (!position?.count) throw new Error('Mesh has no vertices');
    for (let i = 0; i < position.count; i++) {
      if (![position.getX(i), position.getY(i), position.getZ(i)].every(Number.isFinite)) throw new Error('Nonfinite mesh vertex');
    }
    const count = geometry.index?.count ?? position.count;
    if (geometry.index) {
      for (let i = 0; i < count; i++) {
        const index = geometry.index.getX(i);
        if (!Number.isInteger(index) || index < 0 || index >= position.count) throw new Error('Mesh index is outside vertex range');
      }
    }
    if (count === 0 || count % 3) throw new Error('Expected nonempty triangle mesh');
    if (!object.visible || !(Array.isArray(object.material) ? object.material : [object.material]).some(m => m?.visible)) {
      throw new Error('Invisible mesh cannot establish drawable acceptance');
    }
    const meshMaterials = Array.isArray(object.material) ? object.material : [object.material];
    if (meshMaterials.some(m => m.map)) {
      texturedMeshCount++;
      for (const material of meshMaterials.filter(m => m.map)) {
        const uv = geometry.getAttribute(material.map.channel ? `uv${material.map.channel}` : 'uv');
        if (!uv || uv.count !== position.count) throw new Error('Textured mesh is missing matching UV coordinates');
        for (let i = 0; i < uv.count; i++) {
          if (![uv.getX(i), uv.getY(i)].every(Number.isFinite)) throw new Error('Nonfinite UV coordinate');
          const point = new THREE.Vector3().fromBufferAttribute(position, i).applyMatrix4(object.matrixWorld);
          uvSamples.add([material.map.userData.decoded?.rgba_sha256 ?? '', ...material.color.toArray(), ...point, uv.getX(i), uv.getY(i)].map(value => typeof value === 'number' ? Math.round(value * 10000) : value).join(','));
        }
        if (!(material.map.image?.width > 0 && material.map.image?.height > 0)) throw new Error('Texture image did not decode');
        if (material.map.colorSpace !== THREE.SRGBColorSpace) throw new Error('Base color texture is not sRGB');
      }
    }
    meshCount++;
    vertexCount += position.count;
    triangleCount += count / 3;
    for (const material of Array.isArray(object.material) ? object.material : [object.material]) materials.add(material);
  });
  const bounds = new THREE.Box3().setFromObject(scene, true);
  const size = bounds.getSize(new THREE.Vector3());
  const animations = [];
  if (options?.animated) {
    for (const clip of gltf.animations) {
      const mixer = new THREE.AnimationMixer(scene);
      const action = mixer.clipAction(clip);
      action.play();
      const targets = [...new Set(clip.tracks.map(track => track.name.split('.')[0]))];
      const snapshot = () => targets.map(name => {
        const object = scene.getObjectByName(name);
        if (!object) throw new Error(`Animation ${clip.name} target ${name} is missing after load`);
        object.updateWorldMatrix(true, true);
        return object.matrixWorld.elements.slice();
      });
      mixer.setTime(0);
      const start = snapshot();
      let moved = 0;
      for (const fraction of [0.13, 0.37, 0.61, 0.89]) {
        mixer.setTime(clip.duration * fraction);
        const sample = snapshot();
        if (!sample.flat().every(Number.isFinite)) throw new Error(`Animation ${clip.name} produces nonfinite transforms`);
        moved = Math.max(moved, ...sample.flat().map((value, i) => Math.abs(value - start.flat()[i])));
      }
      action.stop();
      mixer.uncacheRoot(scene);
      if (moved < 1e-5) throw new Error(`Animation ${clip.name} does not move its targets`);
      animations.push({ name: clip.name, duration_s: Number(clip.duration.toFixed(4)), targets, max_matrix_delta: Number(moved.toFixed(5)) });
    }
  }
  const pbrMaps = { normal: 0, metallic_roughness: 0 };
  for (const material of materials) {
    if (material.normalMap) {
      pbrMaps.normal++;
      if (material.normalMap.colorSpace === THREE.SRGBColorSpace) throw new Error('Normal map must not be sRGB');
    }
    if (material.roughnessMap || material.metalnessMap) pbrMaps.metallic_roughness++;
  }
  const expectedNormals = (source.materials ?? []).filter(m => m.normalTexture).length;
  if (expectedNormals && pbrMaps.normal !== expectedNormals) throw new Error('GLTFLoader failed to decode all normal maps');
  if (!meshCount || bounds.isEmpty() || ![...bounds.min, ...bounds.max, ...size].every(Number.isFinite) || size.length() === 0) {
    throw new Error('Expected nonempty finite drawable mesh bounds');
  }
  const expectedMaps = (source.materials ?? []).filter(m => m.pbrMetallicRoughness?.baseColorTexture).length;
  if (expectedMaps && [...materials].filter(m => m.map).length !== expectedMaps) throw new Error('GLTFLoader failed to decode all base color textures');
  const decodedTextures = [...materials].filter(m => m.map).map(m => ({
    width: m.map.image.width, height: m.map.image.height, color_space: m.map.colorSpace,
    ...(m.map.userData.decoded ?? { decoder: 'browser image decode' })
  }));
  return { gltf, uvSamples: [...uvSamples].sort(), metrics: {
    passed: true, default_scene_index: source.scene, three_version: `0.${THREE.REVISION}.0`, scene_count: gltf.scenes.length,
    mesh_count: meshCount, vertex_count: vertexCount, triangle_count: triangleCount,
    material_count: materials.size, texture_count: source.textures?.length ?? 0,
    textured_mesh_count: texturedMeshCount, decoded_textures: decodedTextures,
    material_colors: [...materials].map(m => [...m.color.toArray(), m.opacity]).sort(),
    texture_scope: options?.textures ? 'embedded-png-jpeg' : 'untextured-only',
    pbr_maps: pbrMaps, animations, node_names: (source.nodes ?? []).map(n => n.name ?? null),
    bounds: { min: bounds.min.toArray(), max: bounds.max.toArray(), size: size.toArray() }
  } };
}
