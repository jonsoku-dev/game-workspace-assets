// Use the already-required local Blender decoder; no browser shims or placeholder pixels.
import { execFileSync } from 'node:child_process';
import { mkdtemp, writeFile, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createHash } from 'node:crypto';
import { THREE } from './loader.mjs';

export function localImages(parser) {
  parser.loadImageSource = async index => {
    const image = parser.json.images[index];
    const bytes = await parser.getDependency('bufferView', image.bufferView);
    const directory = await mkdtemp(join(tmpdir(), 'model-image-'));
    try {
      const input = join(directory, image.mimeType === 'image/png' ? 'image.png' : 'image.jpg');
      const output = join(directory, 'decoded.rgba');
      await writeFile(input, Buffer.from(bytes));
      execFileSync('blender', ['--background', '--factory-startup', '--offline-mode', '--disable-autoexec',
        '--python-exit-code', '1', '--python', fileURLToPath(new URL('../tools/decode_image.py', import.meta.url)),
        '--', input, output], { stdio: 'pipe', timeout: 120000 });
      const { width, height } = JSON.parse(await readFile(join(directory, 'decoded.json'), 'utf8'));
      const pixels = new Uint8Array(await readFile(output));
      if (pixels.length !== width * height * 4) throw new Error('Invalid decoded RGBA size');
      const texture = new THREE.DataTexture(pixels, width, height);
      texture.needsUpdate = true;
      texture.userData.decoded = { width, height, rgba_sha256: createHash('sha256').update(pixels).digest('hex'),
        unique_rgba: new Set(Array.from({ length: width * height }, (_, i) => pixels.slice(i * 4, i * 4 + 4).join(','))).size,
        decoder: 'Blender local PNG/JPEG' };
      return texture;
    } finally { await rm(directory, { recursive: true, force: true }); }
  };
  return { name: 'LOCAL_DECODED_IMAGES' };
}
