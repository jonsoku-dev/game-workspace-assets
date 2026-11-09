"""Build a local static model bundle; publish only after all validation passes."""
import argparse
import ctypes
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import assembly  # noqa: E402  (schema-version-2 validation without Blender)

FILES = {
    'model': 'model.web.glb', 'metadata': 'model.json',
    'validation': 'three-validation.json', 'source': 'source.blend',
    'raw': 'model.glb', 'preview': 'preview.png', 'review': 'review.png',
    'receipt': 'model.web.glb.webstage.json',
}


def read_request(path):
    spec = json.loads(path.read_text())
    if isinstance(spec, dict) and type(spec.get('schema_version')) is int and spec['schema_version'] == 2:
        return assembly.validate(spec)
    if not isinstance(spec, dict) or type(spec.get('schema_version')) is not int or spec['schema_version'] != 1:
        raise ValueError('Expected schema_version 1 object')
    if set(spec) - {'schema_version', 'name', 'preset', 'source_blend', 'height_m', 'seed'}:
        raise ValueError('Unknown input keys')
    if not isinstance(spec.get('name'), str) or not spec['name'].strip():
        raise ValueError('Name required')
    if ('preset' in spec) == ('source_blend' in spec):
        raise ValueError('Choose preset or source_blend')
    if 'seed' in spec and spec.get('preset') != 'embers':
        raise ValueError('seed applies to embers only')
    if 'source_blend' in spec:
        source = spec['source_blend']
        if not isinstance(source, str) or not source or Path(source).is_absolute():
            raise ValueError('source_blend must be a local path relative to the request')
        source = (path.parent / source).resolve()
        if source.suffix.lower() != '.blend' or not source.is_file():
            raise ValueError('source_blend must name an existing .blend file')
        if 'height_m' in spec:
            raise ValueError('height_m applies to lantern only')
        spec['source_blend'] = str(source)
    elif spec['preset'] == 'embers':
        if 'height_m' in spec:
            raise ValueError('height_m applies to lantern only')
        seed = spec.get('seed', 23)
        if type(seed) is not int or not 0 <= seed <= 4294967295:
            raise ValueError('seed must be an integer from 0 to 4294967295')
    else:
        if spec['preset'] != 'lantern':
            raise ValueError('Unknown preset')
        height = spec.get('height_m', .30)
        if type(height) not in (int, float) or not math.isfinite(height) or not .01 <= height <= 10:
            raise ValueError('height_m must be a finite number from .01 to 10')
    return spec


def publish(stage, output):
    """Atomic no-replace rename, including when another writer wins the race."""
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == 'darwin':
        rename = libc.renameatx_np
        flag = 0x4  # RENAME_EXCL
    elif sys.platform.startswith('linux'):
        rename = libc.renameat2
        flag = 1  # RENAME_NOREPLACE
    else:
        raise RuntimeError('Atomic publication requires macOS or Linux')
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    # Absolute paths make the platform-specific AT_FDCWD value unnecessary.
    if rename(-1, os.fsencode(stage), -1, os.fsencode(output), flag):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(output))


def compare_compiled(metadata, validation):
    original = metadata['original']
    low, high = original['bounds_min'], original['bounds_max']
    expected = {
        'min': [low[0], low[2], -high[1]],
        'max': [high[0], high[2], -low[1]],
        'size': [original['dimensions_m'][i] for i in (0, 2, 1)],
    }
    tolerance = max(1e-6, max(original['dimensions_m']) * .001)
    bounds_match = all(
        len(validation['bounds'][key]) == 3 and
        all(math.isfinite(actual) and abs(actual - wanted) <= tolerance
            for actual, wanted in zip(validation['bounds'][key], values))
        for key, values in expected.items()
    )
    triangles = validation['triangle_count']
    checks = {
        'drawable': validation.get('passed') is True,
        'y_up_bounds_and_dimensions_match': bounds_match,
        'triangles_positive_and_not_increased': type(triangles) is int and 0 < triangles <= original['triangles'],
    }
    if not all(checks.values()):
        raise ValueError('Compiled model mismatch: ' + json.dumps(checks))
    return {
        'checks': checks, 'bounds_tolerance_m': tolerance,
        'expected_y_up_bounds': expected,
        'source_triangles': original['triangles'], 'compiled_triangles': triangles,
        'triangle_retention_ratio': triangles / original['triangles'],
        'scope': 'Webstage may simplify triangles and merge meshes; topology/material equivalence is not asserted',
    }


def run(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        print(result.stdout, file=sys.stderr, end='' if result.stdout.endswith('\n') else '\n')
    if result.returncode:
        raise RuntimeError(f'{Path(command[0]).name} failed with exit code {result.returncode}')


def compile_and_inspect(executables, stage, raw, model, validation, animated, compare_raw=True):
    run([executables['webstage'], 'compile', str(stage / raw), '-b', 'hero', '-o', str(stage / model)])
    command = [executables['node'], str(ROOT / 'three/inspect.mjs'), str(stage / model), str(stage / validation)]
    if compare_raw:
        command.append(str(stage / raw))
    if animated:
        command.append('--animated')
    run(command)
    return json.loads((stage / validation).read_text())


def check_assembly(metadata, validation):
    expected = sorted(a['name'] for a in metadata['animations'])
    actual = sorted(a['name'] for a in validation.get('animations', []))
    names = set(n for n in validation.get('node_names', []) if n)
    targets = {a['target'] for a in metadata['animations']}
    checks = {
        'animations_preserved': actual == expected,
        'animation_targets_named': targets <= names,
        'every_animation_moves': all(a['max_matrix_delta'] > 0 for a in validation.get('animations', [])),
        # Compilers merge identical materials; every surviving material must still carry its maps.
        'pbr_maps_on_every_material': (validation.get('pbr_maps', {}).get('normal') == validation['material_count']
                                       == validation.get('pbr_maps', {}).get('metallic_roughness')),
    }
    if not all(checks.values()):
        raise ValueError('Compiled assembly mismatch: ' + json.dumps(checks))
    return checks


def build_assembly(spec, output, executables):
    files = dict(FILES, review='review.png')
    for index, _ in enumerate(spec['lod_ratios'], 1):
        files[f'lod{index}'] = f'model.lod{index}.web.glb'
        files[f'lod{index}_validation'] = f'lod{index}-validation.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.model-build-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        stage = temporary / 'bundle'
        spec_path = temporary / 'request.json'
        spec_path.write_text(json.dumps(spec, allow_nan=False))
        run([executables['blender'], '--background', '--factory-startup', '--offline-mode',
             '--disable-autoexec', '--python-exit-code', '1',
             '--python', str(ROOT / 'tools/assembly_worker.py'), '--', str(spec_path), str(stage)])
        metadata = json.loads((stage / FILES['metadata']).read_text())
        animated = bool(metadata['animations'])
        validation = compile_and_inspect(executables, stage, FILES['raw'], FILES['model'], FILES['validation'], animated)
        validation['compiled_comparison'] = compare_compiled(metadata, validation)
        validation['assembly_checks'] = check_assembly(metadata, validation)
        lods = []
        for index, lod in enumerate(metadata['lods'], 1):
            lod_validation = compile_and_inspect(executables, stage, lod['file'], files[f'lod{index}'],
                                                 files[f'lod{index}_validation'], animated, compare_raw=False)
            if not 0 < lod_validation['triangle_count'] < validation['triangle_count']:
                raise ValueError(f'LOD{index} must have fewer triangles than LOD0')
            if sorted(a['name'] for a in lod_validation.get('animations', [])) != sorted(a['name'] for a in metadata['animations']):
                raise ValueError(f'LOD{index} lost animations')
            (stage / lod['file']).unlink()
            receipt = stage / (files[f'lod{index}'] + '.webstage.json')
            data = json.loads(receipt.read_text())
            data['input']['path'] = lod['file']
            data['output']['path'] = files[f'lod{index}']
            receipt.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
            files[f'lod{index}_receipt'] = receipt.name
            lods.append({'file': files[f'lod{index}'], 'ratio': lod['ratio'],
                         'triangles': lod_validation['triangle_count']})
        validation['lods'] = lods
        validation['schema_version'] = 2
        (stage / FILES['validation']).write_text(json.dumps(validation, indent=2, allow_nan=False) + '\n')
        receipt_path = stage / FILES['receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['input']['path'] = FILES['raw']
        receipt['output']['path'] = FILES['model']
        receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
        for name in files.values():
            if not (stage / name).is_file() or not (stage / name).stat().st_size:
                raise ValueError(f'Missing or empty artifact: {name}')
        publish(stage, output)
    return {'schema_version': 2, 'status': 'ready', 'files': files}


def build(request, output):
    spec = read_request(request)
    files = FILES.copy()
    if spec.get('preset') == 'embers':
        files['effect'] = 'effect.json'
    if os.path.lexists(output):
        raise FileExistsError(f'Output must be a new directory: {output}')
    executables = {}
    for name in ('blender', 'webstage', 'node'):
        executables[name] = shutil.which(name)
        if not executables[name]:
            raise RuntimeError(f'Required local executable missing: {name}')
    if spec.get('schema_version') == 2:
        return build_assembly(spec, output, executables)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.model-build-', dir=output.parent) as temporary:
        temporary = Path(temporary)
        stage = temporary / 'bundle'
        spec_path = temporary / 'request.json'
        spec_path.write_text(json.dumps(spec, allow_nan=False))
        run([executables['blender'], '--background', '--factory-startup', '--offline-mode',
             '--disable-autoexec', '--python-exit-code', '1',
             '--python', str(ROOT / 'tools/blender_worker.py'), '--', str(spec_path), str(stage)])
        model = stage / FILES['model']
        run([executables['webstage'], 'compile', str(stage / FILES['raw']), '-b', 'hero', '-o', str(model)])
        run([executables['node'], str(ROOT / 'three/inspect.mjs'), str(model), str(stage / FILES['validation']), str(stage / FILES['raw'])])
        metadata = json.loads((stage / FILES['metadata']).read_text())
        validation = json.loads((stage / FILES['validation']).read_text())
        validation['compiled_comparison'] = compare_compiled(metadata, validation)
        validation['schema_version'] = 1
        (stage / FILES['validation']).write_text(json.dumps(validation, indent=2, allow_nan=False) + '\n')
        # The inspector checks absolute paths before this portable receipt rewrite.
        receipt_path = stage / FILES['receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt['input']['path'] = FILES['raw']
        receipt['output']['path'] = FILES['model']
        receipt_path.write_text(json.dumps(receipt, indent=2, allow_nan=False) + '\n')
        for name in files.values():
            if not (stage / name).is_file() or not (stage / name).stat().st_size:
                raise ValueError(f'Missing or empty artifact: {name}')
        publish(stage, output)
    return {'schema_version': 1, 'status': 'ready', 'files': files}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        # Keep the leaf unresolved so an existing symlink is never followed/overwritten.
        output = args.out.absolute()
        output = output.parent.resolve() / output.name
        result = build(args.request.resolve(), output)
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(json.dumps({'schema_version': 1, 'status': 'error', 'error': str(error)}), file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
