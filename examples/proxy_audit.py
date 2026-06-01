#!/usr/bin/env python3
"""
Lightweight proxy for auditing agent-to-model requests.

Intercepts /v1/chat/completions requests, logs request metadata
and prefix hashes, then forwards to the real endpoint.

Usage:
    python proxy_audit.py --listen 8090 --target http://192.168.1.100:8089/v1

Then point your agent's base_url to http://localhost:8090/v1

Logs to proxy_audit.jsonl with one JSON object per request.

⚠️ This is a diagnostic tool, not a production proxy.
   Do not expose it to untrusted networks.
   Do not commit the log file (contains request content).
"""

import argparse
import hashlib
import json
import sys
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.request import Request, urlopen
from urllib.error import URLError


def hash_prefix(text, n=500):
    """Hash first N characters for prefix comparison."""
    return hashlib.md5(text[:n].encode("utf-8")).hexdigest()[:8]


class ProxyHandler(BaseHTTPRequestHandler):
    target_base = None
    log_file = None

    def do_POST(self):
        if self.path not in ("/v1/chat/completions", "/v1/chat/completions/"):
            self.send_error(404)
            return

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length else b"{}"

        # Parse for logging
        try:
            req_data = json.loads(body)
        except json.JSONDecodeError:
            req_data = {}

        messages = req_data.get("messages", [])
        system_msg = next(
            (m["content"] for m in messages if m.get("role") == "system"), ""
        )
        tools = req_data.get("tools", [])

        # Build log entry
        log_entry = {
            "request_id": str(uuid.uuid4())[:8],
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "messages_count": len(messages),
            "system_chars": len(system_msg),
            "first_500_hash": hash_prefix(system_msg, 500),
            "first_2000_hash": hash_prefix(system_msg, 2000),
            "first_8000_hash": hash_prefix(system_msg, 8000),
            "tools_hash": hashlib.md5(
                json.dumps(tools, sort_keys=True).encode()
            ).hexdigest()[:8],
            "total_chars": len(json.dumps(req_data)),
            "model": req_data.get("model", "unknown"),
        }

        # Forward to target
        target_url = f"{self.target_base}/chat/completions"
        fwd_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() in ("content-type", "authorization", "x-api-key")
        }

        start = time.time()
        try:
            fwd_req = Request(target_url, data=body, headers=fwd_headers)
            with urlopen(fwd_req, timeout=120) as resp:
                response_body = resp.read()
                status = resp.status
        except URLError as e:
            log_entry["error"] = str(e)
            log_entry["latency_ms"] = int((time.time() - start) * 1000)
            self._write_log(log_entry)
            self.send_error(502, str(e))
            return

        latency_ms = int((time.time() - start) * 1000)
        log_entry["latency_ms"] = latency_ms
        log_entry["status"] = status
        log_entry["target"] = target_url

        self._write_log(log_entry)

        # Return response
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(response_body)

    def _write_log(self, entry):
        line = json.dumps(entry, ensure_ascii=False) + "\n"
        if self.log_file:
            with open(self.log_file, "a") as f:
                f.write(line)
        # Also print to stderr for real-time observation
        summary = (
            f"[{entry['request_id']}] {entry['messages_count']}msgs "
            f"sys={entry['system_chars']}ch "
            f"h500={entry['first_500_hash']} "
            f"h2000={entry['first_2000_hash']} "
            f"h8000={entry['first_8000_hash']} "
            f"lat={entry.get('latency_ms', '?')}ms"
        )
        if entry.get("error"):
            summary += f" ERR={entry['error']}"
        print(summary, file=sys.stderr)

    def log_message(self, format, *args):
        """Suppress default access log noise."""
        pass


def main():
    parser = argparse.ArgumentParser(
        description="Hermes agent request audit proxy"
    )
    parser.add_argument(
        "--listen", type=int, default=8090, help="Proxy listen port"
    )
    parser.add_argument(
        "--target",
        required=True,
        help="Target endpoint base URL (e.g., http://192.168.1.100:8089/v1)",
    )
    parser.add_argument(
        "--log", default="proxy_audit.jsonl", help="Log file path"
    )
    args = parser.parse_args()

    # Strip trailing slash from target
    target = args.target.rstrip("/")

    ProxyHandler.target_base = target
    ProxyHandler.log_file = args.log

    print(f"Proxy: localhost:{args.listen} → {target}", file=sys.stderr)
    print(f"Log:   {args.log}", file=sys.stderr)
    print("", file=sys.stderr)

    server = HTTPServer(("127.0.0.1", args.listen), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", file=sys.stderr)
        server.shutdown()


if __name__ == "__main__":
    main()
