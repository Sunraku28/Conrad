import os
import re
from pathlib import Path
import requests
from rich.markdown import Markdown
from rich.console import Console

console = Console()

class DeliveryGateInterceptor:
    def __init__(self, max_retries=1):
        self.max_retries = max_retries
        self.full_rules = self._load_critic_rules()

    def _load_critic_rules(self):
        """Loads the rules from rules/SKILL.md or ANTISLOP.md for the auditor."""
        candidates = [
            Path(__file__).parent.parent / "rules" / "SKILL.md",
            Path(__file__).parent.parent.parent / "ANTISLOP.md",
            Path("ANTISLOP.md"),
        ]
        for p in candidates:
            if p.exists():
                try:
                    return p.read_text(encoding="utf-8")
                except Exception:
                    pass
        return "WARNING: ANTISLOP rules not found. Defaulting to strict code review."

    def has_pass_fail_gate(self, response):
        """
        Check if [PASS] is present and [FAIL] is not in the response.
        """
        if not response:
            return False
        has_pass = bool(re.search(r"\[PASS\]", response, re.IGNORECASE))
        has_fail = bool(re.search(r"\[FAIL\]", response, re.IGNORECASE))
        return has_pass and not has_fail

    def execute_critic_audit(self, worker_output):
        """
        The Critic Agent: Runs completely outside the Podman sandbox.
        It reads the Worker's code and grades it against the 38 rules.
        """
        prompt = f"""You are a ruthless compliance auditor for a production codebase.
Review the following generated code against our 38 strictly enforced rules.

## THE 38 RULES:
{self.full_rules[:3000]}

## CODE TO AUDIT:
{worker_output}

Did the code follow all rules? 
1. Point out any violations briefly.
2. If it is flawless, end your response with exactly [PASS] on a new line.
3. If it violates ANY rule, end your response with exactly [FAIL] on a new line.
"""
        payload = {
            "model": "qwen2.5-coder:7b",
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0
            }
        }
        
        try:
            response = requests.post("http://localhost:11434/api/generate", json=payload, timeout=60).json()
            return response.get("response", "[FAIL] API Error during audit.")
        except Exception as e:
            return f"[FAIL] Network error contacting Critic LLM: {e}"

    def execute_with_gate(self, sandbox, prompt):
        """
        Executes the two-stage Actor-Critic pipeline.
        Returns a tuple: (is_success, worker_output_string).
        """
        attempt = 1
        worker_response = ""
        error_feedback = None
        
        while attempt <= self.max_retries:
            # Stage 1: The Worker generates the code inside the Podman sandbox
            print(f"[{sandbox.agent_id}] Stage 1: Worker executing in container...")
            worker_response = sandbox.run_task(prompt, error_feedback=error_feedback)
            
            # Fast check: If task explicitly forced [FAIL] tag
            if re.search(r"\[FAIL\]", worker_response, re.IGNORECASE):
                print(f"[{sandbox.agent_id}] [FAIL] delivery tag detected.")
                return False, Markdown(worker_response)
                
            # If the task completed with explicit [PASS] delivery gate
            if self.has_pass_fail_gate(worker_response):
                print(f"[{sandbox.agent_id}] [PASS] delivery gate verified.")
                return True, Markdown(worker_response)

            # Stage 2: The Critic audits the code against the rules
            print(f"[{sandbox.agent_id}] Stage 2: Critic auditing output against rules...")
            critic_evaluation = self.execute_critic_audit(worker_response)
            
            print(f"\n--- Critic Evaluation ({sandbox.agent_id}) ---\n{critic_evaluation}\n-------------------------")
            
            if re.search(r"\[PASS\]", critic_evaluation, re.IGNORECASE) and not re.search(r"\[FAIL\]", critic_evaluation, re.IGNORECASE):
                return True, Markdown(worker_response)
            
            error_feedback = f"Attempt {attempt} failed the audit. Critic notes:\n{critic_evaluation}\nFix the code and try again."
            attempt += 1

        warning_md = Markdown(f"**WARNING: Code failed audit after {self.max_retries} attempts. Returning raw output.**\n\n" + worker_response)
        return False, warning_md

    def render(self, response_markdown):
        console.print(response_markdown)
