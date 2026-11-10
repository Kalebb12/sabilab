"""Send a tiny request through the configured LLM provider."""

import json
import time
from app.pipeline.llm import call_llm_json

started = time.monotonic()
result = call_llm_json(
    "Return the requested JSON object.",
    'Return exactly this JSON object: {"ok": true}',
)
print(json.dumps(result, indent=2))
print(f"Elapsed: {time.monotonic() - started:.2f}s")