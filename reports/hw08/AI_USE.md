# AI_USE.md - HW8

## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code mainly as a tutor and debugging assistant. I asked it to explain concepts related to Kafka, Docker Compose, FastAPI, Kafka consumer groups, message ordering, retries, dead-letter queues, and the multi-agent pipeline. I also used it when I was unsure how to begin, encountered an error, or needed help locating or downloading a tool or resource.

I wrote and implemented the code, ran the commands and tests on my own machine, reviewed the logs and results, took the screenshots, and decided what to include in the report. I also made the project decisions and completed the Git commits myself.

## 2. One AI mistake, how it was caught, and how it was fixed

The first version of the worker did not handle `SIGTERM`, so it did not immediately leave its Kafka consumer group when it was stopped. After I rebuilt and restarted the worker container, the old worker remained in the group until its session timed out. Because of this, the new worker did not receive the partition for about 40 seconds. The first three API requests I sent returned a 504 timeout.

## 3. How did you detect the problem or verify the result?

I tested the API with real `curl` requests after restarting the worker instead of only checking whether the code looked correct. The worker log showed that the partition was assigned about 40 seconds after the container restarted. The three requests were then processed together, which showed that they had not been lost; they had only been delayed.

## 4. What did you change, and why does it work now?

I added a `SIGTERM` handler that calls `consumer.close()` so the worker leaves the Kafka consumer group immediately. I also changed `session.timeout.ms` to 10 seconds, so a process that is unexpectedly killed is detected more quickly. After restarting the worker again, it was assigned its partition in under one second. This also made the Part 3 worker-kill test run much faster.
