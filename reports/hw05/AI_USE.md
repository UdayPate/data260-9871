AI_USE.md - HW5
1. What did you use an AI assistant for, and what did you do yourself?

I used Claude Code mainly as a tutor and debugging assistant. I asked it to explain concepts related to React, FastAPI, MySQL, Redux Toolkit, MCP servers, retry and timeout policies, and Ollama agent loops. I also used it when I was unsure how to begin, when I encountered an error, or when I needed help locating or downloading a tool or resource.

I wrote the code myself, including the teams table and migration, the FastAPI endpoints, the Redux Toolkit changes, the MCP servers, the retry and timeout logic, execute_tool, and the Ollama agent loop. I ran the commands and tests myself on my own computer and checked the results from my own MySQL database and Ollama setup. I also made the project decisions myself and took the screenshots used in the assignment.

2. One AI-produced output that was wrong or unsuitable

One problem happened when Claude gave me a PowerShell command for launching the MCP Inspector with the domain server. The command used a backslash in the file path:

mcp dev code\meals_server.py


When I ran it, the Inspector showed an error saying that it could not find a file with a mangled name such as codemeals_server.py. This made it appear that there was a problem with my server file, even though the issue was actually with how the path was being interpreted.

3. How did you detect the problem or verify the result?

I detected the problem by running the command myself and looking at the actual terminal output. I noticed that the filename in the error did not contain the expected path separator. I shared that exact error with Claude and used it to investigate the cause.

I also verified the solution myself by running the corrected command and checking that the MCP Inspector connected to the server successfully.

4. What did you change, and why does it work now?

I changed the command to use forward slashes instead of backslashes:

mcp dev code/meals_server.py --with typer


The forward slash works correctly on Windows and is not removed or treated as an escape character by the MCP Inspector. After making this change, the Inspector connected to the server normally, and the later MCP screenshots were taken using the corrected command.

Overall, I wrote and tested the code myself. I used Claude Code to learn the concepts, get help when I was stuck, understand error messages, and debug problems. I verified the suggested changes by running the code and checking the results in my own environment.