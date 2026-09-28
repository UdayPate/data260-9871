# AI_USE.md - HW4

## 1. What did you use an AI assistant for, and what did you do yourself?

I used an AI assistant mainly as a tutor and debugging resource throughout the assignment. I asked it to explain concepts related to React, FastAPI, MySQL, N+1 queries, query-counting middleware, cookies, and RAG systems. I also used it for help understanding error messages, debugging problems, and downloading or locating files and resources needed for the assignment.

I wrote the code myself, including the React components, the FastAPI/MySQL backend, the N+1 measurement code, the query-counting middleware, and `rag.py`. I ran all commands and tests myself on my own computer using my own MySQL database and Ollama setup. I also made the implementation decisions myself, including reusing the HW3 corpus, choosing the index target, selecting the `min_score` cutoff, and designing the sweep questions.

## 2. One AI-produced output that was wrong or unsuitable, or one thing I independently verified

One issue occurred in the automatic scoring check for Q3. The initial check was supposed to determine whether a RAG answer identified the conflict involving AYSO team size. However, it incorrectly gave credit to an answer that contained the text `"6 5"` from a table column, even though the answer never actually stated the team-size conflict.

There were also problems with the first two versions of the SQL query counter. The first version used a `contextvar`, but it did not work correctly across FastAPI's thread boundary. The second version used a per-connection counter, but the counter continued accumulating across requests instead of resetting.

Another issue occurred in `measure_n1.py`. The script returned 401 errors because the `requests` library did not handle the `Secure` cookie for `localhost` in the same way that a browser does.

## 3. How did you detect the problem or verify the result?

For the Q3 scoring issue, I read the model's saved answer and compared it with the verdict produced by the automatic checker. I noticed that the answer did not mention the actual conflict, even though the checker had marked it as correct.

For the query-counter problems, I ran the measurement against the real FastAPI application and checked the returned query counts. The results did not match what the code should have produced. One version returned a count of zero, while another produced counts that continued increasing across separate runs.

I detected the cookie issue when `measure_n1.py` returned 401 errors even though the application worked correctly in a browser. I compared how the browser and the `requests` library were sending the authentication cookie and traced the problem to the `Secure` cookie behavior for `localhost`.

## 4. What did you change, and why does it work now?

For the Q3 scoring bug, I changed the pattern so that it looks for a meaningful statement such as `"5-a-side"` or `"5 players"` instead of accepting a bare digit. I then reran the scoring process with `rescore.py` and kept both the original and corrected scores so they could be compared.

For the query counter, I moved the counter from a `contextvar` to `Connection.info`. I explicitly reset the counter to zero at the beginning of each request and passed the final count through `request.state`. This works because the connection information is available to the database connection, while `request.state` allows the middleware and endpoint to share the count without depending on thread-local context.

For the cookie problem, I changed `measure_n1.py` so that it sends the authentication token explicitly using `cookies=` with each request. This avoids relying on the `requests` cookie jar to handle the `Secure` cookie in the same way as a browser.

Overall, I wrote and tested the implementation myself. I used the AI assistant to explain concepts, help me understand debugging errors, and assist with downloading or locating needed resources. I verified the suggested changes by running the code and checking the actual results in my own environment.