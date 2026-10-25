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

    def __init__(self, model="qwen3:8b", temperature=0.7, reasoning=None, seed=None):
        # HW6: `reasoning=False` turns off qwen3's hidden thinking phase
        # (Ollama think=False). Default None keeps the earlier homeworks'
        # behaviour unchanged.
        extra = {} if reasoning is None else {"reasoning": reasoning}
        if seed is not None:  # HW6 Part 3: reproducible runs (SEED from CLAUDE.md)
            extra["seed"] = seed
        self._llm = ChatOllama(model=model, temperature=temperature, **extra)
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

    def chat(self, messages, tools=None):
        """HW7 Part 2: ONE model turn with optional native tool calling.

        `messages` are dicts with role system | user | assistant | tool.
          - an assistant dict may carry "tool_calls": [{"id", "name", "args"}]
          - a tool dict carries "tool_call_id" and "name" (the tool that produced "content")
        `tools` is a list of OpenAI-style function definitions
        ({"type": "function", "function": {"name", "description", "parameters"}}).

        Returns {"content", "tool_calls": [{"id", "name", "args"}],
                 "invalid_tool_calls": [{"id", "name", "args", "error"}],   # model output that was not valid JSON
                 "usage": {"input_tokens", "output_tokens"}, "latency_ms"}.

        Unlike complete() this prints nothing and does not touch self.history; it does keep the
        cumulative token counters up to date. complete() is unchanged, so HW1-HW6 behave as before.
        """
        import time

        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

        lc = []
        for m in messages:
            role = m["role"]
            if role == "system":
                lc.append(SystemMessage(content=m["content"]))
            elif role == "user":
                lc.append(HumanMessage(content=m["content"]))
            elif role == "assistant":
                calls = [{"name": c["name"], "args": c["args"] if isinstance(c["args"], dict) else {},
                          "id": c["id"]} for c in m.get("tool_calls", [])]
                lc.append(AIMessage(content=m.get("content") or "", tool_calls=calls))
            elif role == "tool":
                lc.append(ToolMessage(content=m["content"], tool_call_id=m["tool_call_id"],
                                      name=m.get("name")))
            else:
                raise ValueError(f"unknown message role: {role!r}")

        llm = self._llm.bind_tools(tools) if tools else self._llm
        started = time.perf_counter()
        response = llm.invoke(lc)
        latency_ms = (time.perf_counter() - started) * 1000

        usage = getattr(response, "usage_metadata", None) or {}
        input_tokens = usage.get("input_tokens", 0)
        output_tokens = usage.get("output_tokens", 0)
        self.turn_count += 1
        self.cumulative_input_tokens += input_tokens
        self.cumulative_output_tokens += output_tokens

        return {
            "content": response.content or "",
            "tool_calls": [{"id": c.get("id"), "name": c["name"], "args": c["args"]}
                           for c in response.tool_calls],
            "invalid_tool_calls": [{"id": c.get("id"), "name": c.get("name"), "args": c.get("args"),
                                    "error": c.get("error")}
                                   for c in getattr(response, "invalid_tool_calls", [])],
            "usage": {"input_tokens": input_tokens, "output_tokens": output_tokens},
            "latency_ms": round(latency_ms, 1),
        }

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