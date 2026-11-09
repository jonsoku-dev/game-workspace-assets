import { readFile, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { localImages } from './decode.mjs';
import { loadModel, validateReceipt } from './loader.mjs';

try {
  const args = process.argv.slice(2);
  const animated = args.includes('--animated');
  const [input, output, raw, ...extra] = args.filter(a => a !== '--animated');
  if (!input || !output || extra.length) throw new Error('Usage: node inspect.mjs model.web.glb output.json [raw.glb] [--animated]');
  const bytes = await readFile(input);
  const receipt = JSON.parse(await readFile(`${input}.webstage.json`, 'utf8'));
  validateReceipt(receipt, bytes.byteLength);
  if (resolve(dirname(resolve(`${input}.webstage.json`)), receipt.output.path) !== resolve(input)) throw new Error('Receipt output.path does not match input GLB');
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const { metrics, uvSamples } = await loadModel(buffer, { textures: true, animated, imagePlugin: localImages });
  let textureComparison;
  if (raw) {
    const original = await readFile(raw);
    const { metrics: before, uvSamples: beforeUV } = await loadModel(original.buffer.slice(original.byteOffset, original.byteOffset + original.byteLength), { textures: true, animated, imagePlugin: localImages });
    // Compilers deduplicate identical materials/textures, so compare the sets of decoded images and colors.
    const fingerprints = m => [...new Set(m.decoded_textures.map(t => [t.width, t.height, t.rgba_sha256, t.color_space].join(':')))].sort();
    const colors = m => [...new Set(m.material_colors.map(c => JSON.stringify(c)))].sort();
    textureComparison = { uv_position_samples_match: JSON.stringify(beforeUV) === JSON.stringify(uvSamples),
      uv_position_tolerance: 'rounded to 0.0001 in meters/UV units', decoded_pixels_match: JSON.stringify(fingerprints(before)) === JSON.stringify(fingerprints(metrics)),
      material_colors_match: !before.texture_count || JSON.stringify(colors(before)) === JSON.stringify(colors(metrics)),
      textured_meshes_present: !before.textured_mesh_count || metrics.textured_mesh_count > 0,
      scope: 'decoded RGBA, sRGB material factors, UV/world-position sample sets at 0.0001 precision; visual appearance needs browser review' };
    if (!textureComparison.uv_position_samples_match || !textureComparison.decoded_pixels_match || !textureComparison.material_colors_match || !textureComparison.textured_meshes_present) throw new Error('Compiled texture/color mismatch: ' + JSON.stringify(textureComparison));
  }
  const result = { ...metrics, texture_comparison: textureComparison, receipt: { contract: receipt.contract, ok: receipt.ok, budget: receipt.budget } };
  await writeFile(output, JSON.stringify(result, null, 2) + '\n');
  console.log(JSON.stringify(result));
} catch (error) {
  console.error(JSON.stringify({ passed: false, error: error.message }));
  process.exitCode = 1;
}
