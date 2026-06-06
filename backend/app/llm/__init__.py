"""LLM generation client — Component B (T054). [C-IV]"""

from app.llm.generate import LlmError, build_prompt, generate

__all__ = ["LlmError", "build_prompt", "generate"]
