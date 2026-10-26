# MiroFish usability product

## Source and current state

Upstream: https://github.com/666ghj/MiroFish
Baseline commit: 7657031ac01184afe2cb220f5ee3545573b5e843
Working branch: feat/usability-foundation
Licence: retain upstream AGPL-3.0 and attribution.

This is an extension of MiroFish, not a replacement stack. Inspection confirms
a Vue 3/Vite frontend, Flask/Python backend, CAMEL/OASIS social simulation,
Zep graph memory, persistent simulation processes, interviews, and report tools.
Existing memory updates do not establish autonomous model training or validated
human usability prediction.

## Reuse and extension boundaries

| Existing source | Reuse | Required extension |
| --- | --- | --- |
| oasis_profile_generator.py | Participant identities and personas | Task knowledge and behaviour constraints |
| simulation_manager.py | Project preparation and state patterns | Browser environment preparation; do not pretend it is Twitter/Reddit |
| simulation_runner.py | Run lifecycle and action event patterns | Browser worker lifecycle and evidence events |
| simulation_ipc.py and run_parallel_simulation.py | Interview command patterns | Evidence-grounded browser-session interviews |
| zep_graph_memory_updater.py | Memory infrastructure | Private session memory and reviewed shared lessons |
| report_agent.py | Report tool architecture | Browser evidence retrieval and finding validation |

## Execution design

Keep Vue, Flask, and Python. Add Python Playwright as an optional browser
dependency, with isolated worker processes. Do not migrate to Next.js or add a
second language backend. First establish a browser environment adapter; inspect
OASIS/CAMEL extension APIs before selecting its precise agent integration.

Separate independent task attempts, deliberate stress tests, and post-run agent
discussion. Discussion proposes findings; it does not validate them. The first
adapter preserves MiroFish profile identity while keeping success criteria out
of participant context. It is not yet wired into the application.

## Milestones and acceptance gates

1. Browser vertical slice: fixture URL, existing profile, one task, bounded
   action loop, screenshots, explicit evaluator success check. No API key in code.
2. Engine integration: MiroFish lifecycle starts and stops the worker; UI can
   display its state and evidence. Test cancellation and worker failure.
3. Interviews and reports: each session claim cites that participant's evidence;
   a validator checks support, not merely whether a citation identifier exists.
4. Multi-user review: independent runs finish before discussion. Preserve each
   original session; discussion cannot overwrite evidence.
5. Learning: record human-confirmed findings and rejected claims. Propose prompt
   or policy versions; evaluate on held-out cases before promotion. No claim of
   weight training unless training is implemented and measured.
6. Product expansion: working preview URLs first; Figma prototype adapter and
   third-party issue export next. Report unsupported interactions as untestable.

## Robustness requirements

Use known-broken and corrected fixture pairs. Measure confirmed finding rate,
known issue recall, repeatability, real-user overlap, false completion, cost,
and duration. Distinguish browser errors, unfinished prototypes, and usability
hypotheses. Freeze benchmark cases outside shared learning memory.

For external sites, implement URL/network scope enforcement, private network
blocking, action permissions, test accounts, payment submission blocking,
secret redaction, and hard time/step/cost limits before general access. Website
content is untrusted input, not an instruction source. Text matching alone
cannot guarantee payment blocking. Start controlled fixtures first.

## Access sequence

- GitHub connection: create a user-owned working repo/fork and publish the branch.
- Model provider and Zep: secure environment configuration when cloud integration
  is ready; never request secrets in chat.
- Figma and third-party services: request only when implementing those adapters.

## Validation so far

The foundation is in `backend/usability/`. Its domain and browser modules import
without Flask startup or cloud dependencies. Twenty-one tests pass, including
real Chromium and real CAMEL ChatAgent integration with an offline stub model.
They cover profile mapping, session isolation, evaluator
context separation, bounded evidence, citation ownership, working and broken
flows, final-action completion, invalid targets, and policy timeout.

Browser baseline tests use a scripted policy. The CAMEL bridge uses MiroFish's
pinned camel-ai 0.2.78 ChatAgent, vision messages, private chat memory, and strict
action parsing. It reads MiroFish's existing JSON profile export without
recreating personas. A real ChatAgent drives Chromium in an integration test
using an offline StubModel; this makes no paid provider calls.

The adapter is not yet connected to the MiroFish simulation manager, Zep memory,
or Vue UI. No real provider run has been performed. Passing tests
does not establish semantic citation support, human realism, autonomous
learning, or production security. External URLs are deliberately unsupported.

Local browser verification used Playwright 1.51.0 and its matching headless
Chromium on offline fixtures after the newer browser download failed. This is
not the production browser choice; select and verify a maintained version
before enabling external URLs.

### Run the baseline

From the repository root, with the browser extra installed and Chromium set up:

```sh
uv pip install --python .venv/bin/python 'playwright>=1.50,<2'
.venv/bin/python -m playwright install chromium --only-shell
.venv/bin/python -m unittest discover -s tests -p 'test_usability*.py' -v
.venv/bin/python backend/scripts/run_usability_fixture.py
.venv/bin/python backend/scripts/run_usability_fixture.py --broken
.venv/bin/python backend/scripts/run_usability_benchmark.py --repeats 3
```

Outputs go to ignored `backend/uploads/usability/` directories: screenshots,
`trace.zip`, and a structured `result.json`. The browser runner refuses an
existing output directory. No model keys or paid API calls are needed.

The benchmark repeats working and broken cases with fresh sessions and policies.
Its six-run scripted baseline had no failed runs, unexpected completions, or
missed completions. Its outcome agreement rate was 1.0. This is a fixture engine
check, not a usability score or evidence of learning. Case definition hashes
identify changes to fixtures, tasks, or evaluator criteria between versions.
Infrastructure failures remain in the agreement denominator.

### Run a model-driven fixture

Install the existing backend dependencies plus the browser extra. Configure
`LLM_API_KEY`, `LLM_BASE_URL`, and `LLM_MODEL_NAME` in the process environment;
do not commit credentials or paste them into chat. The new command intentionally
does not read arbitrary dotenv files. Use the existing `reddit_profiles.json`
export from a prepared MiroFish simulation:

```sh
.venv/bin/python backend/scripts/run_usability_agent.py --profiles /path/to/reddit_profiles.json --agent-id 1
```

This command makes real provider calls and may incur charges. It still uses
only the controlled offline fixture. The provider must support image input.
The current run has a three-step action budget and a 30-second task timeout;
provider usage is not yet a monetary cost cap.

### Compatibility finding

An unconstrained installation of CAMEL 0.2.78 resolved MCP 2.x and failed at
`from mcp.server import FastMCP`. Constrain `mcp>=1.3,<2` in both backend
dependency entry points. CAMEL integration tests passed with MCP 1.30.0.
