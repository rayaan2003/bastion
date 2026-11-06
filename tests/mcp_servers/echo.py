"""A dependency-free stdio MCP-ish server for the proxy tests.

Answers every request with what it received, so a test can see exactly
what reached the server. `test/received` returns every message so far,
parsed and as the raw lines.
"""

import json
import sys

received = []
lines = []
for line in sys.stdin:
    message = json.loads(line)
    received.append(message)
    lines.append(line)
    if "id" not in message or "method" not in message:
        continue
    method, params = message["method"], message.get("params") or {}
    if method == "test/received":
        result = {"messages": received[:-1], "lines": lines[:-1]}
    elif method == "tools/call" and params.get("name") == "fail":
        result = {
            "content": [{"type": "text", "text": "card 4111111111111111 declined"}],
            "isError": True,
        }
    elif method == "tools/call" and params.get("name") == "needs_input":
        result = {"resultType": "input_required", "requestState": "s1", "inputRequests": {}}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": json.dumps(params["arguments"])}]}
    else:
        result = {"method": method}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}) + "\n")
    sys.stdout.flush()
