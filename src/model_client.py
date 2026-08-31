"""
DATA-260 Homework 1 - Part 4: Model Client and Token Accounting
A reusable model-adapter module. All model calls in this project should go
through complete(messages, tools=None) rather than calling the underlying
LangChain/Ollama client directly - this keeps one stable interface, and lets
us track token usage and conversation history in a single place.
"""

import json

from langchain_ollama import ChatOllama


class ModelClient:
    """Wraps a local Ollama model behind a stable complete() interface,
    tracking conversation history and cumulative token usage."""

    def __init__(self, model="qwen3:8b", temperature=0.7):
        self._llm = ChatOllama(model=model, temperature=temperature)
        self.history = []  # list of {"role": ..., "content": ...} dicts

        self.turn_count = 0
        self.cumulative_input_tokens = 0
        self.cumulative_output_tokens = 0

    def complete(self, messages, tools=None):
        """Send `messages` (a list of {"role", "content"} dicts) to the model
        and return the assistant's reply as a string. `tools` is accepted for
        interface stability but is not used by this simple adapter yet.

        This also appends both the outgoing user message(s) and the model's
        reply to self.history, and updates token/turn counters.
        """
        # LangChain's ChatOllama accepts a list of (role, content) tuples
        # or plain dicts; we normalize to tuples here.
        lc_messages = [(m["role"], m["content"]) for m in messages]

        response = self._llm.invoke(lc_messages)

        # Record the new messages (anything not already in history) plus the reply
        for m in messages:
            if m not in self.history:
                self.history.append(m)
        self.history.append({"role": "assistant", "content": response.content})

        # Token accounting - Ollama/LangChain exposes this via usage_metadata
        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        total_tokens = usage.get("total_tokens", input_tokens + output_tokens)

        self.turn_count += 1
        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens

        print(f"[turn {self.turn_count}] input_tokens={input_tokens} "
              f"output_tokens={output_tokens} total_tokens={total_tokens}")

        return response.content

    def stats(self):
        """Return a dict of current stats: turn count, cumulative token
        counts, and serialized conversation-history length. Does NOT alter
        self.history."""
        history_json = json.dumps(self.history)
        return {
            "turn_count": self.turn_count,
            "cumulative_input_tokens": self.cumulative_input_tokens,
            "cumulative_output_tokens": self.cumulative_output_tokens,
            "cumulative_total_tokens": (
                self.cumulative_input_tokens + self.cumulative_output_tokens
            ),
            "history_length_chars": len(history_json),
        }

    def print_final_summary(self):
        """Print cumulative totals - intended to be called on exit."""
        print("\n=== Final Summary ===")
        print(f"Total turns: {self.turn_count}")
        print(f"Cumulative input tokens: {self.cumulative_input_tokens}")
        print(f"Cumulative output tokens: {self.cumulative_output_tokens}")
        print(f"Cumulative total tokens: "
              f"{self.cumulative_input_tokens + self.cumulative_output_tokens}")