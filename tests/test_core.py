import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from voiceflow import cloud, system


class TestDictation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.calls = []
        self.responses = []
        calls, responses = self.calls, self.responses
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def respond(self):
                calls.append((self.path, self.headers, self.rfile.read(int(self.headers.get("Content-Length", 0)))))
                code, body = responses.pop(0)
                self.send_response(code)
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())
            do_GET = do_POST = respond
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.base = "http://127.0.0.1:" + str(server.server_port)
        self.cfg = system.DEFAULTS | {"custom_url": self.base}
        self.audio = Path(self.tmp.name) / "speech.m4a"

    def test_capture_upload_and_refine(self):
        levels = []
        proc = system.record(self.audio, "sine=frequency=330", True, meter=levels.append)
        deadline = time.monotonic() + 8
        while not levels and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(.05)
        system.finish(proc)
        self.assertGreater(max(levels), .05)
        streams = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", self.audio]))
        self.assertEqual(("aac","16000",1), tuple(streams["streams"][0][k] for k in ("codec_name","sample_rate","channels")))
        self.cfg.update(speech_provider="Custom", text_provider="Custom")
        self.responses.extend([(200, {"text":"मुझे नॉलेज है"}), (200, {"choices":[{"message":{"content":"Mujhe knowledge hai."}}]})])
        raw = cloud.transcribe(self.cfg, self.audio, "demo")
        result, _ = cloud.refine(self.cfg, raw, "demo")
        self.assertEqual(result,"Mujhe knowledge hai.")
        self.assertEqual([c[0] for c in self.calls], ["/audio/transcriptions", "/chat/completions"])
        self.assertIn(self.audio.read_bytes(), self.calls[0][2])
        self.assertEqual(json.loads(self.calls[1][2])["messages"][1]["content"], raw)
        self.assertEqual(self.calls[0][1]["Authorization"], "Bearer demo")

    def test_groq_fallback_only_on_429(self):
        with patch.dict(cloud.PROVIDERS, Groq=(self.base, [], [])):
            self.responses.extend([(429, {}), (429, {}), (200, {"choices":[{"message":{"content":"done"}}]})])
            self.assertEqual(cloud.refine(self.cfg, "original", "demo"), ("done", "llama-3.3-70b-versatile"))
            self.assertEqual([json.loads(c[2])["model"] for c in self.calls], ["llama-3.1-8b-instant", "openai/gpt-oss-20b", "llama-3.3-70b-versatile"])
            self.responses.append((401, {}))
            with self.assertRaises(cloud.ApiError):
                cloud.refine(self.cfg,"original","wrong")
            self.assertEqual(len(self.calls),4)

    def test_groq_connection_denied(self):
        with patch.dict(cloud.PROVIDERS, Groq=(self.base + "/openai/v1", [], [])):
            self.responses.append((403, {"error": {"message": "Denied for supplied-key"}}))
            with self.assertRaisesRegex(cloud.ApiError, r"403 .*Denied for \[redacted\]"):
                cloud.fetch_models("Groq", self.cfg, "supplied-key")
            path, headers, _ = self.calls[0]
            self.assertEqual(path, "/openai/v1/models")
            self.assertEqual(headers["Authorization"], "Bearer supplied-key")
            self.assertIn("VoiceFlowAI", headers["User-Agent"])

    def test_groq_check_uses_configured_operations_without_catalog_access(self):
        with patch.dict(cloud.PROVIDERS, Groq=(self.base, [], [])):
            self.responses.extend([(200, {"text": "Voice flow connection test."}),
                                   (200, {"choices": [{"message": {"content": "VoiceFlow connection test."}}]})])
            result = cloud.check_connection("Custom", self.cfg, "Bearer example")
            self.assertIn(self.cfg["speech_model"], result)
            self.assertIn(self.cfg["text_model"], result)
            self.assertEqual([path for path, *_ in self.calls], ["/audio/transcriptions", "/chat/completions"])
            self.assertIn(b"ftyp", self.calls[0][2])
            self.assertTrue(all(h["Authorization"] == "Bearer example" for _, h, _ in self.calls))

    def test_real_operation_denied_stops_at_transcription(self):
        with patch.dict(cloud.PROVIDERS, Groq=(self.base, [], [])):
            self.responses.append((403, {}))
            with self.assertRaisesRegex(cloud.ApiError, r"403 .*audio/transcriptions"):
                cloud.check_connection("Groq", self.cfg, "test")
            self.assertEqual(len(self.calls), 1)

    def test_gemini_audio_and_listing(self):
        self.cfg.update(speech_provider="Gemini",speech_model="gemini-test")
        self.audio.write_bytes(b"example")
        with patch.dict(cloud.PROVIDERS, Gemini=(self.base, [], [])):
            self.responses.extend([(200, {"models":[{"name":"models/gemini-test","supportedGenerationMethods":["generateContent"]}]}),
                (200, {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]})])
            self.assertEqual(cloud.fetch_models("Gemini",self.cfg,"key"),["gemini-test"])
            self.assertEqual(cloud.transcribe(self.cfg,self.audio,"key"),"hello")
            self.assertEqual(self.calls[-1][1]["x-goog-api-key"], "key")
            self.assertIn(b"audio/flac",self.calls[-1][2])

    def test_scope_secrets_and_wayland(self):
        with patch.dict(os.environ, XDG_CONFIG_HOME=self.tmp.name, WAYLAND_DISPLAY="wayland-0"):
            system.save(self.cfg | {"api_key":"private"})
            self.assertNotIn("private",system.config_path().read_text())
            self.assertEqual(system.load(),self.cfg)
            self.assertIsNone(system.x11_target())
            self.assertFalse(system.paste(None))
        with self.assertRaises(ValueError):
            cloud.endpoint("Custom", {"custom_url":"http://example.com/v1"})

    def test_truncated_or_blank_refinement(self):
        self.cfg.update(text_provider="Custom")
        for choice in ({"finish_reason":"length","message":{"content":"cut"}},{"message":{"content":" "}}):
            self.responses.append((200,{"choices":[choice]}))
            with self.assertRaises(ValueError):
                cloud.refine(self.cfg, "original", "demo")
