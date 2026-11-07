# AI_USE.md - HW9

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code mainly as a tutor and debugging assistant. I asked it to explain concepts related to Redis, semantic caching, stale-answer invalidation, threshold selection, cost modeling, and the Answering and Evaluator agents. I also used it when I was unsure how to begin, encountered an error, or needed help understanding why something was not working.

I wrote and implemented the code myself. I ran the tests and measurement scripts on my own machine, reviewed the output and results, took the required screenshots, decided which results to include in the report, and made the Git commits myself.

## 2. One mistake, how it was caught, and how it was fixed

The first version of my lesson-validation step used the Evaluator's repair loop while testing the validation questions. Since the repair loop corrected every wrong first answer, all of the validation questions became correct both before and after loading the lesson. This meant that the validation step could not measure whether the lesson actually improved the model's first answer.

## 3. How did you detect the problem or verify the result?

I ran the complete pipeline with the real model before the reported run. The dry run showed zero failures before and after applying both candidate lessons, even though the training run had failed twice. This showed that the validation results were not meaningful because the repair loop was hiding the lesson's actual effect.

## 4. What did you change, and why does it work now?

I changed the validation process so that each question is answered only once without the repair loop, while still loading the candidate lesson. This measures the lesson's effect on the model's initial answer. After the change, the real lesson was kept because it fixed `val_04` and `val_12` without causing regressions. The deliberately harmful lesson was rejected because it caused `val_02` to fail.