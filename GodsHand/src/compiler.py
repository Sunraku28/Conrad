import os


CORE_DIRECTIVES = """## CORE DIRECTIVES
1. Output ONLY raw, compile-ready code wrapped in a markdown block.
2. Absolutely NO conversational filler, greetings, or explanations before or after the code.
3. Prioritize memory safety and strict algorithmic complexity constraints."""

class SystemPromptCompiler:
    def __init__(self):
        self.liveliness_toolkit = ""

    def compile_prompt(self):
        prompt_parts = []
        
        # Give the Worker a concise, high-priority instruction set.
        prompt_parts.append(CORE_DIRECTIVES)
        
        # Inject the Liveliness Toolkit
        if self.liveliness_toolkit:
            prompt_parts.append("\n## Liveliness Toolkit\n")
            prompt_parts.append(self.liveliness_toolkit)
            
        # Append DESIGN.md if exists
        design_path = "DESIGN.md"
        if os.path.exists(design_path):
            prompt_parts.append("\n## Project Design\n")
            with open(design_path, "r", encoding="utf-8") as f:
                prompt_parts.append(f.read())
        else:
            prompt_parts.append("\n**WARNING**: Draft without direction. (DESIGN.md not found)\n")
            
        return "\n".join(prompt_parts)
