## 1. What did you use an AI assistant for, and what did you do yourself?

I asked Claude to tutor me throughout the assignment. It explained unfamiliar concepts, guided me through each part, and helped me understand and troubleshoot errors whenever I encountered them. It also suggested code and possible fixes, but I ran all commands, tested the code, reviewed the results, and decided which changes to use myself.

## 2. Describe one AI-produced output that was wrong or unsuitable, or one result you independently verified.

When I first ran hw1_client.py for Part 4, the model’s first response was garbled. Instead of returning a clean, bullet-point code review, it claimed that the submitted code contained a syntax error caused by a /think fragment. This was incorrect because the code I submitted did not contain such a fragment or syntax error.



## 3. How did you detect the problem or verify the result?

I detected the problem by running the program and carefully reading its actual output. The reference to /think was an obvious warning sign because it was unrelated to the submitted code.

I had previously observed that qwen3:8b emits an internal <think>...</think> reasoning block before its final response. Comparing the relevant files showed that agents_demo.py already removed these blocks through its extract_json() logic, while the newer src/model_client.py did not. Instead, it passed response.content directly to the terminal and stored the unfiltered response in the conversation history.

## 4. What did you change, and why does it work now?

I added a strip_thinking() helper to src/model_client.py, using the same regular-expression approach already used in agents_demo.py. I then applied it to every model response before returning the response or storing it in the conversation history.

This prevents the model’s internal <think> block from appearing in the displayed answer or contaminating later prompts through the stored history. After making the change, subsequent runs produced clean, bullet-only responses without the garbled text. The model also correctly remembered earlier turns—for example, it accurately described the divide() function from turn 1 when asked about it in turn 3. These results confirmed that the filtering worked and that the conversation history was being maintained correctly.