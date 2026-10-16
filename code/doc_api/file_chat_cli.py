"""
DATA-260 Homework 6 - Part 4: tiny interactive CLI for the file-based memory
(same functions as POST /api/file-chat). Type /help for commands, empty line or Ctrl-D to quit.
"""

import file_memory
import llm

if __name__ == "__main__":
    print("File-memory chat. /memory /compact /dream /help")
    while True:
        try:
            line = input("you> ").strip()
        except EOFError:
            break
        if not line:
            break
        try:
            out = file_memory.chat_turn(line)
        except llm.LLMError as exc:
            print("error:", exc)
            continue
        print(out.get("output") or out.get("reply"))
