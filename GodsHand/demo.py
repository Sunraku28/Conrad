import threading
import sys
import os
import requests
import subprocess
import re
import shutil
from pathlib import Path

# Append Conrad repo root so GodsHand can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from GodsHand.src.sandbox import WorkerSandbox
from GodsHand.src.interceptor import DeliveryGateInterceptor
from GodsHand.utils.state import Blackboard

MAX_TRIES = 1 

blackboard = Blackboard()
interceptor = DeliveryGateInterceptor()

# The Rigged Test Scenarios
TEST_TASKS = [
    {
        "agent": "simple-tester",
        # Agent 1: Extremely simple task with ironclad formatting instructions.
        "prompt": "Say exactly 'System Check OK', and then on the very next line, output the string '[PASS]'. Do not wrap it in code blocks or add any other text."
    },
    {
        "agent": "complex-cpp-backend",
        # Agent 2: Complex task, omitting the [PASS] instruction entirely so Qwen forgets it.
        "prompt": "Write a highly optimized C++ implementation of Linked List. Wrap the code in a standard ```cpp markdown block. End your response with the exact string '[PASS]' on a new line."
    },
    {
        "agent": "complex-k8s-architect",
        # Agent 3: Complex task, explicitly forcing the [FAIL] tag to trip the interceptor.
        "prompt": "Design a complete Kubernetes Helm chart for a microservices cluster. End your response with the exact string '[FAIL]'."
    }
]

def execute_rigged_test(task_data):
    sandbox = WorkerSandbox(agent_id=task_data["agent"])
    print(f"[SPAWN] {sandbox.agent_id} isolated in branch: {sandbox.branch_name}")
    
    sandbox.setup_worktree()
    print(f"[{sandbox.agent_id}] Spawning Podman Container via WorkerSandbox...")
    
    # The interceptor calls sandbox.run_task() which spins up the isolated Podman container
    is_success, output_md = interceptor.execute_with_gate(sandbox, task_data["prompt"])
    raw_output = output_md.markup if hasattr(output_md, 'markup') else str(output_md)
    
    print(f"\n[{sandbox.agent_id}] RAW OUTPUT SNIPPET:\n{raw_output[-100:]}\n")

    if is_success:
        print(f"[{sandbox.agent_id}] VERIFIED: 38 Rules Enforced. Code is clean.")
        status = "Complete"

        # Preserve the complete model response for review in this task's
        # isolated worktree, then materialize any fenced source artifacts.
        worktree_path = sandbox.worktree_dir
        (worktree_path / "raw_response.md").write_text(raw_output, encoding="utf-8")

        extension_map = {
            "cpp": "cpp", "c++": "cpp", "c": "c",
            "python": "py", "py": "py",
            "bash": "sh", "sh": "sh", "shell": "sh",
            "javascript": "js", "js": "js",
            "json": "json", "yaml": "yaml", "yml": "yml",
        }
        stem_map = {
            "cpp": "main", "c++": "main", "c": "main",
            "python": "main", "py": "main",
            "bash": "script", "sh": "script", "shell": "script",
        }
        used_names = {}
        code_blocks = re.findall(
            r"```(?P<language>[A-Za-z0-9_+.-]*)\s*\n(?P<code>.*?)```",
            raw_output,
            flags=re.DOTALL,
        )

        for index, (language, code) in enumerate(code_blocks, start=1):
            language = language.strip().lower()
            extension = extension_map.get(language, "txt")
            stem = stem_map.get(language, f"artifact_{index}")
            used_names[stem] = used_names.get(stem, 0) + 1
            suffix = "" if used_names[stem] == 1 else f"_{used_names[stem]}"

            clean_code = re.sub(
                r"^\s*\[(?:PASS|FAIL)\]\s*$",
                "",
                code,
                flags=re.IGNORECASE | re.MULTILINE,
            ).strip()
            artifact_path = worktree_path / f"{stem}{suffix}.{extension}"
            artifact_path.write_text(clean_code + "\n", encoding="utf-8")

        subprocess.run(["git", "add", "."], cwd=worktree_path, check=True)
        subprocess.run(
            ["git", "commit", "-m", f"Auto-generated artifacts for {sandbox.task_id}"],
            cwd=worktree_path,
            check=True,
        )
    else:
        print(f"[{sandbox.agent_id}] BLOCKED: Interceptor caught rule violation.")
        status = "Failed (Rule Violation)"

        # The failed worktree is deleted below, so retain its model output in
        # the main repository first for debugging and audit purposes.
        failed_task_dir = Path(sandbox.repo_root) / "failed_outputs" / sandbox.task_id
        failed_task_dir.mkdir(parents=True, exist_ok=True)
        (failed_task_dir / "raw_response.md").write_text(raw_output, encoding="utf-8")

        generated_output = sandbox.worktree_dir / "graph.cpp"
        if generated_output.is_file():
            shutil.copy2(generated_output, failed_task_dir / generated_output.name)

    # Lock & Save to Blackboard
    blackboard_entry = {
        "agent": sandbox.agent_id,
        "task": sandbox.task_id,
        "branch": sandbox.branch_name,
        "status": status
    }
    blackboard.append_task(task_name=sandbox.task_id, result=blackboard_entry, status=status)
    print(f"[{sandbox.agent_id}] LOGGED STATUS: {status}")

    # Circuit Breaker Annihilation for Failed Tasks
    if status != "Complete":
        print(f"[{sandbox.agent_id}] CIRCUIT BREAKER: Annihilating sandbox {sandbox.branch_name}.")
        sandbox.teardown_worktree(delete_branch=True)

# Execute the rigged demo concurrently
threads = []
for test in TEST_TASKS:
    t = threading.Thread(target=execute_rigged_test, args=(test,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print("\n[ORCHESTRATOR] Rigged demo complete. Check monitor for states.")
