# Local Qwen vision model

The usability extension can run **Qwen3-VL-2B-Instruct** locally. It needs no
OpenAI account, provider API key, or paid inference service. It still needs
hardware to run; this does not make hosted production compute free.

The original model is Apache-2.0 licensed. The pinned Unsloth GGUF conversion
uses Q4_K_M text weights and an F16 vision projector, about 1.93 GB combined.
The repository stores a revision, sizes, and SHA-256 checksums in
`backend/usability/local-model.json`. Large weights stay outside git.

Sources:

- https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct
- https://huggingface.co/unsloth/Qwen3-VL-2B-Instruct-GGUF
- https://github.com/ggml-org/llama.cpp/blob/master/docs/multimodal.md

## Setup

Install a llama.cpp release with Qwen3-VL support. The Linux CPU binary used
during development was release **b11910**, build commit **63b4b303b**:

https://github.com/ggml-org/llama.cpp/releases/tag/b11910

The Ubuntu x64 archive checksum was
`811603cdb8e76df28fa8e0a7f179b3b6161e3ee205e1063711e60e49428be0d0`.
Use the platform-specific release for Windows or macOS. Those platforms have
not been tested here.

From the repository root, using an environment with the backend dependencies
and browser extra installed:

```sh
python backend/scripts/download_local_usability_model.py
python backend/scripts/run_local_usability_demo.py --server /path/to/llama-server
```

If `llama-server` is on PATH, omit `--server`. Install Playwright Chromium first
with `python -m playwright install chromium --only-shell`.

The demo starts a loopback-only model server on an available port, runs a real
CAMEL participant through the controlled booking fixture, then interviews the
recorded session. It stops the child server on exit. It uses a manually authored
demo persona in MiroFish's export format, not a claim of a research-validated
participant. It does not call Zep or any paid model provider.

For the broken fixture:

```sh
python backend/scripts/run_local_usability_demo.py --server /path/to/llama-server --broken
```

The model may stop, repeat actions until the step limit, or return an invalid
answer. These outcomes must be measured, not hidden by changing the evaluator.

## Evidence and limits

Outputs go to ignored `backend/uploads/local-usability/<run-id>/`:

- `session/session.json`, screenshots, and a browser trace.
- `model-server.log` for runtime diagnosis.
- `interview.json` and `summary.json` after a valid interview.

A browser success is checked from actual fixture state, not the model's claim.
Interview observations must quote recorded text. At most one corrective retry
is enabled for the local demo; rejection reasons remain in the result. Each
attempt starts from the original record, without the rejected prose.

This is a small local integration test. It does not establish human behaviour,
general website reliability, or self-learning. CPU vision inference can be slow.
The launcher uses an 8192-token context, 1024 image tokens, and a 512-token output
cap. It gives local requests a 120-second timeout. Local text tokenization comes
from llama.cpp; chat and image token allowances are estimates, and the server
enforces the actual context limit.

## Existing model-driven commands

For a separately managed local server, set `LLM_PROVIDER=local`. Defaults are
`http://127.0.0.1:8080/v1` and model alias `qwen3-vl-2b-local`. The existing
profile-driven runner and interview command then use that server without a key.

Local mode rejects non-loopback URLs, ignores configured cloud keys, and sends
no authorization header. The local transport ignores proxy environment
variables. Cloud mode remains explicit and still requires its configured key.

CAMEL 0.2.78 normally interprets `max_tokens` as its input context budget. The
local backend overrides that behaviour so the output cap cannot silently remove
screenshots or most of the interview record.

## Observed results

All 36 automated tests passed. Actual local inference was also checked on two
controlled flows, separately from the StubModel tests:

| Case | Browser outcome | Interview outcome |
| --- | --- | --- |
| Working booking | One click reached the real confirmation state | Valid exact quote on the first attempt |
| Broken booking | Stopped at the step limit; no false completion | Rejected after two attempts |

The broken-flow interview failed the citation requirements. Earlier working-flow
interviews also failed before prompt/context fixes. These are development
checks, not an unbiased estimate of reliability. The current model is a local
baseline, not a validated replacement for human participants. Machine-readable
results are in `backend/usability/validation/local-qwen-smoke.json`.
