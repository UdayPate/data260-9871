# AI_USE.md - HW10
## 1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code primarily as a tutor and debugging assistant throughout HW10. I asked it to explain concepts I was unfamiliar with, help me understand how different parts of the system worked, and guide me through troubleshooting problems when I ran into errors. Rather than relying on it for answers, I used its explanations to better understand the code, identify potential issues, and figure out how to fix them. I did the hands-on work of reviewing the results, manually labeling the 20 Writer drafts based on helpfulness, running my Git commands and commits, and making decisions about the project as I went along.

## 2. One mistake, how it was caught, and how it was fixed

One issue I encountered was with the GEval judge. Initially, its scores and explanations seemed reasonable, but I realized that I needed to verify whether its evaluations actually agreed with human judgment. Just because an AI judge provides a convincing explanation does not necessarily mean its score is accurate.

## 3. How did you detect the problem or verify the result?

I manually labeled 20 Writer drafts based on their helpfulness before comparing them with the judge's evaluations. I then ran the judge three times and compared its scores against my own labels. The Spearman correlation was only 0.15 (p = 0.54), with a mean absolute difference of 1.4 points. I also noticed that it gave high scores to answers containing invented information while sometimes giving low scores to correct answers that appropriately stated information was unavailable.

## 4. What did you change, and why does it work now?

Instead of changing the judge to make its results look better, I kept the results and documented its limitations in my report. I concluded that although the judge was consistent across multiple runs, it was not necessarily accurate or aligned with human judgment. I also identified improvements that would be needed before trusting it, such as collecting more human-labeled examples, improving the evaluation criteria, and performing additional robustness testing. This experience taught me the importance of independently verifying AI-generated results instead of assuming they are correct.
