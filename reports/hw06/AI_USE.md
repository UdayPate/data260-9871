# AI_USE.md - HW6  (DRAFT OPTIONS - NOT FINAL)

---

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code as a tutoring and debugging assistant while completing HW6. I wrote and implemented the code myself, including the MongoDB fixtures API, chat and memory endpoints, cost and probe scripts, file-based memory and consolidation features, tests, and verification script. Whenever I got stuck, I asked Claude Code to explain concepts, help me understand errors, or suggest possible approaches. I made the final implementation decisions and reviewed and modified the code myself.

I also started Docker and MongoDB, ran the tests and verification scripts, took the Postman and MongoDB Compass screenshots, checked the results, and made the Git commits myself. I was responsible for confirming that the final system worked correctly and that the submitted code and screenshots were accurate.

---

## 2. One AI mistake, how it was caught, and how it was fixed

I asked Claude to check whether a generated function followed the rules in AGENT.md. At first, it reported that all 5 out of 5 runs followed every rule. However, when I looked at the code myself, I noticed that the docstring was written across three lines even though AGENT.md required a one-line docstring. The problem was that the check used ast.get_docstring(), which removes the original whitespace and made the check too lenient.

## 3. How did you detect the problem or verify the result?

 I found the issue by reading the generated code instead of relying only on the reported pass count. Looking directly at the source showed that the docstring was actually split across three lines.

## 4. What did you change, and why does it work now?

 I changed the verification check so that it requires the opening and closing quotation marks of the docstring to be on the same source line. After this change, the code guided by AGENT.md initially scored 0 out of 5, which showed that the wording of the rule was not specific enough. I updated rule 3 to clearly state that the docstring must be on one line and included an example. After running the test again, all 5 runs passed. I also ran a control test without AGENT.md, and all 5 runs failed the type-hint and docstring requirements. This confirmed that AGENT.md was actually influencing the generated code.

