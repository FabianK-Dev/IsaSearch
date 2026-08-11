"""
stub_openai_server.py: A minimal OpenAI compatible server for the offline tests.

It answers /v1/models, /v1/chat/completions and /v1/embeddings and records every request it
received, so that the tests can assert on what the client actually sent (e.g. the Authorization
header or the batch sizes). Failures can be injected to exercise the retry handling.

The embeddings it returns are not meaningful vectors: the first component is the number of
characters of the embedded text, which lets the tests verify truncation and ordering.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Model name that makes the server answer with a permanent client error, as llama.cpp does for an
# input that does not fit into its physical batch.
REJECTING_MODEL = "reject-me"


class StubOpenAIServer:
    def __init__(self):
        self.requests = []
        # Number of upcoming embedding requests that answer with a retryable error.
        self.transient_failures = 0
        self.http_server = HTTPServer(("127.0.0.1", 0), self.build_handler())
        self.thread = threading.Thread(
            target=self.http_server.serve_forever, daemon=True
        )

    @property
    def base_url(self):
        return "http://127.0.0.1:" + str(self.http_server.server_address[1]) + "/v1"

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.http_server.shutdown()
        self.http_server.server_close()

    def requests_to(self, path):
        return [request for request in self.requests if request["path"] == path]

    def build_handler(stub):
        class Handler(BaseHTTPRequestHandler):
            # The tests assert on the recorded requests instead of on the server log.
            def log_message(self, *args):
                pass

            def respond(self, status, payload):
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def record(self, body=None):
                stub.requests.append(
                    {
                        "path": self.path,
                        "authorization": self.headers.get("Authorization"),
                        "body": body,
                    }
                )

            def do_GET(self):
                self.record()

                if self.path == "/v1/models":
                    self.respond(200, {"data": [{"id": "beaker_gemma4"}]})
                else:
                    self.respond(404, {"error": "not found"})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                self.record(body)

                if self.path == "/v1/chat/completions":
                    self.chat_completion(body)
                elif self.path == "/v1/embeddings":
                    self.embeddings(body)
                else:
                    self.respond(404, {"error": "not found"})

            def chat_completion(self, body):
                if body.get("model") == REJECTING_MODEL:
                    self.respond(400, {"error": {"message": "context size exceeded"}})
                    return

                self.respond(
                    200,
                    {
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "<BEGIN>answer<END>",
                                }
                            }
                        ]
                    },
                )

            def embeddings(self, body):
                if body.get("model") == REJECTING_MODEL:
                    self.respond(
                        400, {"error": {"message": "input is too large to process"}}
                    )
                    return

                if stub.transient_failures > 0:
                    stub.transient_failures -= 1
                    self.respond(503, {"error": "model is loading"})
                    return

                data = [
                    {"index": i, "embedding": [float(len(text)), float(i)]}
                    for i, text in enumerate(body["input"])
                ]
                # Deliberately reversed, because the OpenAI API does not guarantee the order of the
                # returned embeddings and the client has to sort them by their index.
                self.respond(200, {"data": list(reversed(data))})

        return Handler
