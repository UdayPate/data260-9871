# AI_USE.md - HW7

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code mainly as a tutor and debugging assistant. I asked it to explain concepts related to React, FastAPI, MySQL, Redux Toolkit, MCP servers, retry and timeout policies, and Ollama agent loops. I also used it when I was unsure how to begin, encountered an error, or needed help locating or downloading a tool or resource.

I wrote and implemented the code, ran the commands and tests on my own machine, reviewed the results, took the Postman and lint screenshots, and decided what to include in the report. I also made the scope decisions for the assignment and committed my work myself.

## 2. One AI mistake, how it was caught, and how it was fixed

While I was improving the Part 4 agent, Claude suggested adding an example value, 29, to the prompt. The model incorrectly copied that number into its SQL as a per-minute rate instead of using it as the monthly membership price. This caused the membership residual to be calculated as $551,504, and the membership scenario's accuracy dropped from 8 of 8 fully correct runs to 2 of 8.

## 3. How did you detect the problem or verify the result?

Each agent run is compared with an independent recomputation from the CSV using `costs.py`, which the agent does not see. After rerunning the 16-run measurement, I noticed the accuracy had decreased. I then reviewed the failed run's SQL and found that the `29.00` from the prompt had been incorrectly used as the per-minute rate.

## 4. What did you change, and why does it work now?

I removed the example number from the prompt and changed the wording to say that the agent should use the price of one month from the policy text. I then repeated the measurement. The final version, which also includes a repeat-call guard and a hard model-call deadline, correctly identifies the decision in 6 of 8 membership runs and 8 of 8 pay-per-use runs. The independent verification remains in the results because some individual calculated values can still be incorrect.