# AI_USE.md - HW2

## 1. What did you use an AI assistant for, and what did you do yourself?

I mainly used Claude as a tutor throughout the assignment. Whenever I got stuck or did not understand a concept, I asked Claude to explain it to me and help me understand how it worked. For example, I used Claude to learn about LangGraph, the POST/Redirect/GET pattern, Pydantic validation, and to help me understand errors when I was debugging.

I wrote the code for the assignment myself and ran and tested everything on my own computer. When I ran into errors, I used Claude to help me understand what was going wrong, and then I made the changes and tested the code again myself. I also ran all of the LangGraph experiments using my own Ollama/qwen3:8b setup and recorded the results from those runs.

## 2. One AI-produced output that was wrong/unsuitable, or one thing you independently verified

One issue came up when I was first testing the FastAPI backend for Part 2. When I tried to open the home page with `GET /`, I got an "Internal Server Error" instead of the page rendering.

The initial version of `main.py` used:

`templates.TemplateResponse("index.html", {"request": request})`

This looked correct based on examples I had seen, but it did not work with the version of Starlette installed on my machine.

## 3. How did you detect the problem or verify the result?

I found the problem by actually running the FastAPI server and testing the page with curl. The traceback showed:

`TypeError: unhashable type: 'dict'`

The error was coming from Jinja2's template lookup, so at first it was not very clear what was causing it. I used Claude as a debugger here by giving it the error and discussing possible causes, but I verified the problem myself by checking my installed Starlette version and testing the suggested change locally.

I also ran the page again after making the change and confirmed that it returned a 200 status and rendered correctly.

## 4. What did you change, and why does it work now?

After checking the installed Starlette version, which was 1.6.0, I found that the `TemplateResponse` calling convention was different from the older examples I was using. I changed the call to:

`templates.TemplateResponse(request, "index.html", {})`

After making this change and restarting the server, the home page returned a 200 status and rendered correctly.

I ran into another bug later while working on the Part 3 LangGraph pipeline. When the Reviewer found a problem, the graph correctly sent the task back to the Planner. The Planner would create a new proposal, but the old `reviewer_feedback` was still stored in the state.

Because of that, the router kept seeing the old feedback and sending the graph back to the Planner without allowing the Reviewer to review the new proposal. This caused the graph to keep looping until it reached the turn limit instead of ending because the Reviewer approved something.

I found this while testing the graph with a fake scripted LLM client so that I could control the responses and see exactly which nodes were being called. I noticed that the Reviewer was only being called once even though the Planner was running multiple times.

To fix it, I changed `planner_node` so that it clears `reviewer_feedback` by setting it back to `{}` whenever a new proposal is created. This tells the router that the new proposal has not been reviewed yet. I ran the same test again after the change and confirmed that the Reviewer was now called after every new Planner attempt.

Overall, I used Claude mostly when I needed an explanation, wanted help getting started, or got stuck debugging something. I still ran and tested the code myself and used the actual results from my own environment for the assignment.
