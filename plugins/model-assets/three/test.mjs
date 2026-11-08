import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { localImages } from './decode.mjs';
import { inspectContainer, loadModel } from './loader.mjs';

function fixture(modify = () => {}) {
  const json = { asset: { version: '2.0' }, scene: 0, scenes: [{ nodes: [0] }], nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 } }] }], buffers: [{ byteLength: 36 }],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: 36 }],
    accessors: [{ bufferView: 0, componentType: 5126, count: 3, type: 'VEC3', min: [0, 0, 0], max: [1, 1, 0] }] };
  modify(json);
  let text = JSON.stringify(json);
  text += ' '.repeat((4 - text.length % 4) % 4);
  const bytes = Buffer.alloc(20 + text.length + 8 + 36);
  bytes.writeUInt32LE(0x46546c67, 0); bytes.writeUInt32LE(2, 4); bytes.writeUInt32LE(bytes.length, 8);
  bytes.writeUInt32LE(text.length, 12); bytes.writeUInt32LE(0x4e4f534a, 16); bytes.write(text, 20);
  bytes.writeUInt32LE(36, 20 + text.length); bytes.writeUInt32LE(0x004e4942, 24 + text.length);
  new Float32Array(bytes.buffer, bytes.byteOffset + 28 + text.length, 9).set([0, 0, 0, 1, 0, 0, 0, 1, 0]);
  return bytes;
}
const bytes = fixture();
const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.length);
assert.equal((await loadModel(buffer)).metrics.triangle_count, 1);
for (const change of [j => j.buffers[0].uri = 'https://example.com/model.bin', j => j.meshes[0].primitives[0].mode = 1, j => j.animations = [{}], j => j.meshes[0].primitives[0].targets = [{}]]) {
  const invalid = fixture(change);
  assert.throws(() => inspectContainer(invalid.buffer.slice(invalid.byteOffset, invalid.byteOffset + invalid.length)));
}
const dir = await mkdtemp(join(tmpdir(), 'three-inspection-'));
try {
  const input = join(dir, 'model.web.glb');
  await writeFile(input, bytes);
  for (const path of ['model.web.glb', input]) {
    await writeFile(`${input}.webstage.json`, JSON.stringify({ contract: { id: 'webstage-asset', version: '1.0' }, ok: true, kind: 'gltf', output: { path, bytes: bytes.length }, violations: [] }));
    const result = JSON.parse(execFileSync(process.execPath, [new URL('./inspect.mjs', import.meta.url).pathname, input, join(dir, 'result.json')], { encoding: 'utf8', cwd: '/' }));
    assert.equal(result.triangle_count, 1);
  }
} finally { await rm(dir, { recursive: true }); }
console.log('PASS: static mesh, external/unsupported rejection, portable and absolute receipt paths');

const corruptTexture = fixture(j => {
  j.images = [{ bufferView: 0, mimeType: 'image/png' }];
  j.textures = [{ source: 0 }];
  j.materials = [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }];
  j.meshes[0].primitives[0].material = 0;
});
await assert.rejects(loadModel(corruptTexture.buffer.slice(corruptTexture.byteOffset, corruptTexture.byteOffset + corruptTexture.length),
  { textures: true, imagePlugin: localImages }), /failed to decode all base color textures/);
console.log('PASS: invalid embedded PNG cannot become a white placeholder success');
