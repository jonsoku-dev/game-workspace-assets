import { spawnSync } from 'node:child_process';
import { constants } from 'node:fs';
import { copyFile, lstat, mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const artifacts = {
  sprite: 'asset.png',
  preview: 'preview.png',
  metadata: 'metadata.json',
  validation: 'validation.json',
  source: 'draft.png',
};
const pngSignature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

async function main() {
  const [request, destination, draft, ...extra] = process.argv.slice(2);
  if (!request || !destination || !draft || extra.length) {
    throw new Error('Usage: node import.mjs REQUEST GAME_ASSET.png DRAFT.png|--codex');
  }
  const output = resolve(destination);
  const command = process.env.PIXEL_ASSET_CLI || 'pixel-asset';
  const executable = command.includes('/') || command.includes('\\') ? resolve(command) : command;
  const temporary = await mkdtemp(join(tmpdir(), 'mock-game-plugin-'));
  try {
    const bundle = join(temporary, 'bundle');
    const args = ['build', '--request', resolve(request), '--out', bundle];
    if (draft === '--codex') args.push('--codex');
    else args.push('--draft', resolve(draft));
    const result = spawnSync(executable, args, {
      cwd: temporary,
      encoding: 'utf8',
      maxBuffer: 1024 * 1024,
      timeout: 660_000,
    });
    if (result.error) throw result.error;
    if (result.status !== 0) {
      throw new Error(`Asset build failed: ${result.stderr.trim() || `exit ${result.status}`}`);
    }
    const lines = result.stdout.trim().split(/\r?\n/);
    if (lines.length !== 1) throw new Error('Expected one JSON build result');
    const manifest = JSON.parse(lines[0]);
    if (manifest?.schema_version !== 1 || manifest.status !== 'ready') {
      throw new Error('Unsupported or rejected build result');
    }
    let placement;
    for (const [name, filename] of Object.entries(artifacts)) {
      if (manifest.files?.[name] !== filename) throw new Error(`Invalid ${name} artifact path`);
      const path = join(bundle, filename);
      const stat = await lstat(path);
      if (!stat.isFile() || stat.size === 0) throw new Error(`Invalid ${name} artifact`);
      const bytes = await readFile(path);
      if (filename.endsWith('.png')) {
        if (!bytes.subarray(0, 8).equals(pngSignature)) throw new Error(`Invalid ${name} PNG`);
      } else {
        const document = JSON.parse(bytes.toString('utf8'));
        if (!document || typeof document !== 'object' || Array.isArray(document)) {
          throw new Error(`Invalid ${name} JSON`);
        }
        if (name === 'metadata') {
          const pivot = document.import?.pivot_px_from_top_left;
          if (document.schema_version !== 1 || document.import?.filter !== 'nearest' ||
              !Array.isArray(pivot) || pivot.length !== 2 || !pivot.every(Number.isFinite)) {
            throw new Error('Invalid import metadata');
          }
          placement = document.import;
        }
        if (name === 'validation' && document.passed !== true) {
          throw new Error('Asset validation did not pass');
        }
      }
    }
    await copyFile(join(bundle, artifacts.sprite), output, constants.COPYFILE_EXCL);
    process.stdout.write(`${JSON.stringify({ status: 'imported', asset: output, import: placement })}\n`);
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

main().catch((error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
