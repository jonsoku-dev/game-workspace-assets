import concurrent.futures
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch


MODULE = importlib.util.spec_from_file_location('model_build', Path(__file__).resolve().parents[1] / 'tools/build.py')
build = importlib.util.module_from_spec(MODULE)
MODULE.loader.exec_module(build)


class BuildTests(unittest.TestCase):
    def test_relative_source_and_rejected_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.blend'
            source.touch()
            request = root / 'request.json'
            request.write_text(json.dumps({'schema_version': 1, 'name': 'Source', 'source_blend': 'source.blend'}))
            self.assertEqual(build.read_request(request)['source_blend'], str(source.resolve()))
            for invalid in (
                {'schema_version': True, 'name': 'X', 'preset': 'lantern'},
                {'schema_version': 1, 'name': 'X', 'preset': 'unknown'},
                {'schema_version': 1, 'name': 'X', 'preset': 'lantern', 'height_m': float('nan')},
                {'schema_version': 1, 'name': 'X', 'source_blend': str(source)},
                {'schema_version': 1, 'name': 'X', 'source_blend': 'source.blend', 'height_m': 1},
                {'schema_version': 1, 'name': 'X', 'preset': 'lantern', 'extra': True},
                {'schema_version': 1, 'name': 'X', 'preset': 'lantern', 'seed': 23},
                {'schema_version': 1, 'name': 'X', 'source_blend': 'source.blend', 'seed': 23},
                {'schema_version': 1, 'name': 'X', 'preset': 'embers', 'height_m': .3},
            ):
                request.write_text(json.dumps(invalid))
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    build.read_request(request)

    def test_ember_seed_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            request = Path(directory) / 'request.json'
            spec = {'schema_version': 1, 'name': 'Embers', 'preset': 'embers'}
            request.write_text(json.dumps(spec))
            self.assertEqual(build.read_request(request), spec)
            for seed in (0, 23, 4294967295):
                request.write_text(json.dumps({**spec, 'seed': seed}))
                self.assertEqual(build.read_request(request)['seed'], seed)
            for seed in (True, -1, 4294967296, 23.0, '23', None):
                request.write_text(json.dumps({**spec, 'seed': seed}))
                with self.subTest(seed=seed), self.assertRaises(ValueError):
                    build.read_request(request)

    def test_compiled_comparison_allows_simplification_but_checks_axes(self):
        metadata = {'original': {'triangles': 100, 'bounds_min': [-1, -2, 0],
                                'bounds_max': [1, 2, 3], 'dimensions_m': [2, 4, 3]}}
        validation = {'passed': True, 'triangle_count': 50,
                      'bounds': {'min': [-1, 0, -2], 'max': [1, 3, 2], 'size': [2, 3, 4]}}
        result = build.compare_compiled(metadata, validation)
        self.assertEqual(result['triangle_retention_ratio'], .5)
        for bad in (0, 101):
            with self.subTest(triangles=bad), self.assertRaises(ValueError):
                build.compare_compiled(metadata, {**validation, 'triangle_count': bad})
        validation['bounds']['size'] = [2, 4, 3]
        with self.assertRaises(ValueError):
            build.compare_compiled(metadata, validation)

    def test_publication_race_has_one_winner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stages = [root / 'a', root / 'b']
            for stage in stages:
                stage.mkdir()
                (stage / 'identity').write_text(stage.name)
            output = root / 'published'
            barrier = threading.Barrier(2)

            def compete(stage):
                barrier.wait()
                try:
                    build.publish(stage, output)
                    return stage.name
                except FileExistsError:
                    return None

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(compete, stages))
            winners = [value for value in results if value]
            self.assertEqual(len(winners), 1)
            self.assertEqual((output / 'identity').read_text(), winners[0])
            self.assertTrue(next(stage for stage in stages if stage.name != winners[0]).is_dir())

    def test_existing_empty_directory_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stage, output = root / 'stage', root / 'output'
            stage.mkdir()
            output.mkdir()
            with self.assertRaises(FileExistsError):
                build.publish(stage, output)
            self.assertTrue(stage.is_dir())

    def test_inspection_failure_never_publishes_and_cleans_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, output = root / 'request.json', root / 'output'
            request.write_text(json.dumps({'schema_version': 1, 'name': 'X', 'preset': 'lantern'}))

            def run(command):
                if command[0] == 'blender':
                    stage = Path(command[-1])
                    stage.mkdir()
                    (stage / 'model.glb').write_bytes(b'partial')
                if command[0] == 'node':
                    raise RuntimeError('inspection failed')

            with patch.object(build.shutil, 'which', side_effect=lambda name: name), patch.object(build, 'run', side_effect=run):
                with self.assertRaisesRegex(RuntimeError, 'inspection failed'):
                    build.build(request, output)
            self.assertFalse(output.exists())
            self.assertEqual(sorted(path.name for path in root.iterdir()), ['request.json'])


if __name__ == '__main__':
    unittest.main()
