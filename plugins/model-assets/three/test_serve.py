import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

spec = importlib.util.spec_from_file_location("serve", Path(__file__).resolve().parents[1] / "tools/serve.py")
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class ServerTest(unittest.TestCase):
    def test_allowlist_and_host(self):
        with tempfile.TemporaryDirectory() as directory:
            bundle = Path(directory).resolve()
            (bundle / "model.web.glb").write_bytes(b"fixture")
            (bundle / "model.web.glb.webstage.json").write_text(json.dumps({"output": {"path": "model.web.glb"}}))
            server = serve.ThreadingHTTPServer(("127.0.0.1", 0), serve.handler_for(serve.routes(bundle)))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_port}"
                for route in ["/", "/viewer.mjs", "/loader.mjs", "/model.web.glb", "/model.web.glb.webstage.json", *["/three/" + p for p in serve.MODULES]]:
                    with urlopen(base + route) as response:
                        self.assertEqual(response.status, 200)
                        self.assertTrue(response.read())
                        self.assertIsNone(response.headers.get("Access-Control-Allow-Origin"))
                        self.assertIn("connect-src 'self'", response.headers["Content-Security-Policy"])
                for route in ["/../serve.py", "/%2e%2e/serve.py", "/three/package.json", "/unknown"]:
                    with self.assertRaises(HTTPError) as error:
                        urlopen(base + route)
                    self.assertEqual(error.exception.code, 404)
                with self.assertRaises(HTTPError) as error:
                    urlopen(Request(base + "/", headers={"Host": "example.com"}))
                self.assertEqual(error.exception.code, 403)
            finally:
                server.shutdown()
                server.server_close()
                thread.join()


if __name__ == "__main__":
    unittest.main()
