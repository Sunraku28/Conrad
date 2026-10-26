# Conrad / GodsHand: Architectural & Technical Context

## 1. Project Overview

**Conrad** (part of the **GodsHand** multi-agent framework) is an autonomous, sandboxed AI software engineering and code compliance orchestration engine.

In typical AI coding setups, autonomous agents modify the developer's working tree directly, hallucinate unwanted files, or output generic, low-quality "AI slop" without strict quality gates. **Conrad** solves this by enforcing:

1. **Complete Sandbox Isolation**: Workers execute inside rootless Podman containers on detached Git worktrees. They never touch the main repository branch until explicitly verified.
2. **Actor-Critic Quality Gate**: The output of worker agents is intercepted in-memory and evaluated against non-negotiable delivery contracts (`[PASS]` / `[FAIL]`) and 38 mandatory Anti-Slop code/UI compliance rules.
3. **Circuit Breaker Self-Defense**: Tasks that fail verification trigger an automatic Circuit Breaker that immediately annihilates the agent's temporary Git branch and container, preventing tainted code from persisting.
4. **Thread-Safe Blackboard Architecture**: A high-throughput, OS-locked append-only state store (`state.jsonl`) enabling dozens of agents to run and log concurrently without race conditions.

---

## 2. Technology Stack

| Layer | Technologies & Tools | Description |
| :--- | :--- | :--- |
| **Core Runtime** | **Python 3.11+ / 3.14** | Core execution runtime for orchestrators, agents, and middleware. |
| **Container Sandbox** | **Podman (v5.8+)** | Rootless, daemonless ephemeral containers (`--rm`, `--network host`, `--userns=keep-id`, `-v worktree:/workspace:Z`). |
| **Base Images** | **`docker.io/library/python:3.11-slim`** | Lightweight, reproducible isolated runtime for worker agents. |
| **Local LLM Engine** | **Ollama (`qwen2.5-coder:7b`)** | Local, offline inference via HTTP REST API (`localhost:11434/api/generate`). Zero external API leakage. |
| **Version Control Isolation** | **Git (`git worktree`)** | Dynamic branching (`<agent>/<task-id>`) and detached worktree workspaces (`/tmp/godshand_worktrees/<task-id>`). |
| **Concurrency & State** | **`filelock` + JSONL (`state.jsonl`)** | OS-level kernel file locking (`fcntl`) ensuring atomic concurrent writes to the shared Blackboard. |
| **Interactive CLI** | **`prompt_toolkit` + `rich`** | Interactive REPL session (`conrad.py`) and terminal Markdown rendering (`rich.console`). |
| **Live Telemetry** | **Bash, `jq`, `column`** | Real-time monitoring dashboard (`monitor.sh`) displaying active worktrees, containers, and state. |

---

## 3. System Architecture & File Layout

```text
Conrad/
├── .gitignore                       # Ignores runtime states, lock files, and failed output dumps
├── state.jsonl                      # Central Blackboard tracking task progress & results
├── state.jsonl.lock                 # OS-level file mutex handle for concurrent multi-agent writes
├── context.md                       # Architectural documentation (this document)
│
└── GodsHand/
    ├── __init__.py
    ├── demo.py                      # Multi-agent concurrent test orchestrator
    ├── run_test_5.py                # Standalone delivery-gate validation script
    ├── test_concurrency.py          # High-load filelock concurrency stress test
    │
    ├── src/                         # Core agent logic and sandbox runtime
    │   ├── __init__.py
    │   ├── conrad.py                # Interactive Conrad REPL session
    │   ├── sandbox.py               # WorkerSandbox: Git worktrees & Podman runner
    │   ├── interceptor.py           # DeliveryGateInterceptor & Critic audit engine
    │   ├── compiler.py              # SystemPromptCompiler: Context & rule assembly
    │   ├── merger.py                # BatchMerger: Cleanly merges verified branches to main
    │   └── monitor.sh               # 1-second interval live terminal monitor
    │
    ├── utils/
    │   ├── __init__.py
    │   ├── state.py                 # Thread-safe Blackboard implementation via FileLock
    │   └── parser.py                # Regex extraction engine for R-XX rule blocks
    │
    └── rules/
        └── SKILL.md                 # 38 Mandatory Anti-Slop Rules (R-01 through R-38)
```

---

## 4. Key Architectural Mechanisms

### A. Ephemeral Worker Sandbox (`src/sandbox.py`)
- For every incoming task, a unique `task_id` is minted (e.g. `task-2e15ce4a`).
- A detached Git branch is branched off `main`: `<agent_id>/<task_id>`.
- A temporary worktree is attached at `/tmp/godshand_worktrees/<task_id>`.
- Podman spawns an isolated container named `godshand-<agent>-<task>` mounting the worktree at `/workspace:Z`.
- Inside the container, the worker agent executes tasks, writes artifacts (e.g. `graph.cpp`), and commits changes solely within its private branch.

### B. Delivery Gate & Critic Interceptor (`src/interceptor.py`)
- **Stage 1 (Container Execution)**: The raw response from the worker is captured in memory.
- **Stage 2 (Gate Verification)**:
  - If output contains an explicit `[FAIL]` tag, it is rejected immediately.
  - If output satisfies the contract `[PASS]`, it is verified as `Complete`.
  - If contract tags are absent, the **Critic LLM** evaluates the code against the 38 Anti-Slop rules in `rules/SKILL.md`.
- If an agent fails verification, the **Circuit Breaker** fires:
  - The failed branch and worktree are forcefully deleted (`sandbox.teardown_worktree(delete_branch=True)`).
  - The audit response is dumped to `failed_outputs/<task-id>/raw_response.md` for developer inspection.

### C. OS-Locked Blackboard (`utils/state.py`)
- When agents finish, they write their result object to `state.jsonl`.
- To prevent interleaved writes when 20+ threads finish at the exact same millisecond, `Blackboard.append_task` acquires an exclusive OS lock (`state.jsonl.lock`) before appending.

### D. Safe Batch Merger (`src/merger.py`)
- Once the orchestrator finishes, `merger.py` reads all `Complete` tasks from `state.jsonl`.
- It performs clean, non-fast-forward (`--no-ff`) git merges of the verified branches into the main branch and deletes the task branch after a clean merge.

---

## 5. Lifecycle of a Task

```
User Prompt / Orchestrator
           │
           ▼
[1] WorkerSandbox Setup ──► Spawns detached Git Branch & /tmp worktree
           │
           ▼
[2] Podman Container Run ──► Mounts worktree at /workspace:Z
           │                  Calls Ollama (qwen2.5-coder:7b)
           ▼
[3] DeliveryGateInterceptor ──► Checks [PASS] / [FAIL] & Anti-Slop Rules
      ├── PASS ──► Commit artifacts to worktree & branch
      │             Log "Complete" to state.jsonl
      │
      └── FAIL ──► Dump logs to failed_outputs/<task_id>/
                    Circuit Breaker: Annihilate worktree & branch
                    Log "Failed" to state.jsonl
           │
           ▼
[4] Batch Merger ──────────► Cleanly merge verified "Complete" branches into main
```

---

## 6. Running and Monitoring

```bash
# 1. Start the Live Telemetry Dashboard (Terminal 1)
./GodsHand/src/monitor.sh

# 2. Run the Multi-Agent Concurrent Test (Terminal 2)
python3 GodsHand/demo.py

# 3. Run the Interactive Conrad REPL
python3 GodsHand/src/conrad.py
```
