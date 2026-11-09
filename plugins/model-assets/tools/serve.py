#!/usr/bin/env python3
"""Serve one explicit GLB bundle and the local inspection viewer on loopback."""
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

THREE = Path(__file__).resolve().parents[1] / "three"
MODULES = {
    "build/three.module.js": "build/three.module.js",
    "build/three.core.js": "build/three.core.js",
    "addons/loaders/GLTFLoader.js": "examples/jsm/loaders/GLTFLoader.js",
    "addons/libs/meshopt_decoder.module.js": "examples/jsm/libs/meshopt_decoder.module.js",
    "addons/utils/BufferGeometryUtils.js": "examples/jsm/utils/BufferGeometryUtils.js",
    "addons/utils/SkeletonUtils.js": "examples/jsm/utils/SkeletonUtils.js",
}


def routes(bundle):
    model = (bundle / "model.web.glb").resolve(strict=True)
    receipt = (bundle / "model.web.glb.webstage.json").resolve(strict=True)
    if model.parent != bundle or receipt.parent != bundle:
        raise ValueError("Bundle files must be regular files inside the explicit bundle")
    data = json.loads(receipt.read_text())
    if (receipt.parent / data["output"]["path"]).resolve() != model:
        raise ValueError("Receipt output.path does not match bundle model")
    result = {"/": THREE / "viewer.html", "/viewer.mjs": THREE / "viewer.mjs", "/loader.mjs": THREE / "loader.mjs",
              "/model.web.glb": model, "/model.web.glb.webstage.json": receipt}
    result.update({"/three/" + route: THREE / "node_modules/three" / path for route, path in MODULES.items()})
    for path in result.values():
        if not path.is_file():
            raise ValueError(f"Missing viewer dependency: {path.name}")
    return result


def handler_for(allowed):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Host") not in {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"}:
                self.send_error(403)
                return
            path = allowed.get(urlsplit(self.path).path)
            if path is None:
                self.send_error(404)
                return
            try:
                body = path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            mime = {".html": "text/html; charset=utf-8", ".mjs": "text/javascript", ".js": "text/javascript", ".json": "application/json", ".glb": "model/gltf-binary"}[path.suffix]
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'; style-src 'unsafe-inline'; connect-src 'self' blob:; img-src blob:; base-uri 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    allowed = routes(args.bundle.resolve(strict=True))
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler_for(allowed))
    print(f"http://127.0.0.1:{server.server_port}/", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
