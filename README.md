# data260-9871

DATA-260 (Agentic AI & Distributed Systems) coursework repository.
This repo is extended across all homeworks this semester - see
`reports/hw01/`, `reports/hw02/`, etc. for per-assignment deliverables.

## Personal Configuration (fixed for the semester)

| Value | |
|---|---|
| SID4 | 9871 |
| PORT_BASE | 8871 |
| PREFIX | s9871 |
| SEED | 9871 |
| VERIFY_SEED | 269871 |
| DOMAIN_ID | 7 - Community sports league fixtures |

Hardware: Lenovo Legion Slim 5 16" (Ryzen 5 7640HS, 16GB RAM, NVIDIA
RTX 4060 8GB, 512GB SSD)
Local model: qwen3:8b, served via Ollama

## Repository layout

```
data260-9871/
├── code/                          - shared application code (extended each HW)
│   ├── web_application/
│   │   ├── main.py                - FastAPI backend (HW2 Part 2)
│   │   ├── templates/
│   │   │   └── index.html         - Jinja2 template (HW1 Part 1, HW2 Parts 1-2)
│   │   └── static/
│   │       ├── app.js
│   │       └── style.css          - vintage newspaper theme (HW2 Part 1)
│   ├── Dockerfile
│   ├── agents_demo.py             - HW1 Part 2 (sequential Planner/Reviewer)
│   ├── agent_graph.py             - HW2 Part 3 (stateful LangGraph version)
│   ├── loop_safety_experiments.py - HW2 Part 4 experiments
│   ├── measure_nondeterminism.py  - HW1 Part 3
│   ├── hw1_client.py              - HW1 Part 4
│   ├── verify_hw01.py             - HW1 self-check
│   ├── verify_hw02.py             - HW2 self-check
│   └── venv/                      - Python 3.12 virtual environment (gitignored)
├── src/
│   └── model_client.py            - reusable model adapter (HW1 Part 4, reused in HW2 Part 3)
├── reports/
│   ├── hw01/                      - HW1 deliverables
│   └── hw02/                      - HW2 deliverables (report, metrics, logs, raw data, cases)
├── AGENT.md                       - system prompt for hw1_client.py's code-review agent
├── DOMAIN_SCHEMA.md               - domain entity schema
└── README.md
```

## Prerequisites

- Python 3.12 (NOT 3.13 - langchain has a numpy compatibility issue on 3.13)
- [Ollama](https://ollama.com/download) installed and running, with `qwen3:8b` pulled
- Docker Desktop (for HW1 Part 1 deployment)
- An AWS account with the AWS CLI configured (for HW1 Part 1 ECS deployment)
- Git

## Setup

```powershell
git clone https://github.com/UdayPate/data260-9871.git
cd data260-9871

cd code
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1

pip install -r requirements.txt

ollama pull qwen3:8b
```

---

# HW1

## Part 1 - Web application (HTML/JS + Docker + AWS ECS)

```powershell
cd code
docker build -t data260-9871-app .
docker run -p 8871:8871 data260-9871-app
```
Then visit http://localhost:8871

AWS ECS deployment (summary - see reports/hw01/RUN_LOG.txt for the full
session): image was pushed to Amazon ECR, then run as a single Fargate
task in an ECS service with a security group allowing inbound TCP on
port 8871.

## Part 2 - Agentic AI pipeline

```powershell
cd code
python agents_demo.py
```

## Part 3 - Non-determinism measurement

```powershell
cd code
python measure_nondeterminism.py
```
See `reports/hw01/METRICS.md` for results.

## Part 4 - Model client and token accounting

```powershell
cd code
python hw1_client.py
```
Interactive CLI using `src/model_client.py`'s adapter. Commands:
`/stats`, `/exit`.

## HW1 Verification

```powershell
cd code
python verify_hw01.py
```

---

# HW2

HW2 extends the same codebase in place (no separate copy), per the
assignment's instructions.

## Part 1 - Responsive CSS + loading/empty/error states

No separate command - this is the same web application, now styled
with a vintage newspaper/box-score theme and usable down to 375px
width. Visible loading, empty, and error states are shown by the
Fixture Board list, driven by `static/app.js`.

## Part 2 - FastAPI backend

```powershell
cd code\web_application
python main.py
```
Starts the FastAPI app on PORT_BASE (8871). Visit http://localhost:8871

- **Create**: fill out and submit the form - redirects to the home
  view showing the updated Fixture Board.
- **Update Record #1**: one-click button that updates the record with
  ID 1 to fixed, domain-appropriate values.
- **Delete Highest ID**: one-click button that removes the
  highest-ID record.
- **Search**: type in the search box and click Search (or press
  Enter) to filter by fixture name or teams/players, without a full
  page reload.

Data is stored in-memory and resets when the server restarts - an
intentional, documented simplification.

## Part 3 - Stateful agent graph (LangGraph)

```powershell
cd code
python agent_graph.py
```
Runs the LangGraph Planner/Reviewer/Supervisor graph once, streaming
each node's output, and prints the final merged state plus token
stats. All LLM calls route through `src/model_client.py`.

## Part 4 - Schema validation and loop-safety experiments

```powershell
cd code
python loop_safety_experiments.py
```
Runs three experiments against `agent_graph.py`: a 30-run
classification, a turn-ceiling comparison (2 vs. 10, 20 runs each),
and a 5-run adversarial-input test. Raw results go to
`reports/hw02/raw/`; summary tables and the deployment recommendation
are in `reports/hw02/METRICS.md`.

Note: long-running (75 total graph runs) - expect roughly 1-3+ hours.

## HW2 Verification

```powershell
cd code
python verify_hw02.py
```
Confirms required files exist, actually starts FastAPI as a subprocess
and checks it responds on PORT_BASE, and actually runs the LangGraph
pipeline with a wall-clock timeout to confirm it terminates rather
than hanging. Writes to `reports/hw02/verification.json`.


---

# HW3

HW3 extends the same codebase in place, per the assignment's instructions.

## Part 1 - FastAPI Authentication

```powershell
cd code\web_application
python main.py
```
Starts the app on PORT_BASE (8871). Visit http://localhost:8871

- **Home (`/`)**: shows a welcome message, with a Login link if logged
  out, or Dashboard/Logout links if logged in.
- **Login (`/login`)**: username `league_admin`, password `GoLions2026!`.
  Shows a Bootstrap alert on invalid credentials.
- **Dashboard (`/dashboard`)**: protected - redirects to `/login` if not
  authenticated. Links to `/fixtures` (the HW2 board) and Logout.
- **Logout (`/logout`)**: revokes the session server-side (not just the
  client cookie - see `ACTIVE_SESSIONS` in `auth.py`) and redirects home.

Session cookies are signed (via Starlette's `SessionMiddleware`) and set
with `httponly`, `secure`, and `samesite=lax`. An idle timeout of 30
seconds is enforced independently of logout, via a server-side session
store rather than relying solely on the signed cookie's own expiry.

## Part 2 - Chunking Technique Comparison (Retrieval-Only RAG)

### Build the domain corpus (run once)

```powershell
pip install requests pypdf
python build_corpus.py
```
Downloads 6 real public community-sports-league documents (one per sport
in `DOMAIN_SCHEMA.md`, plus a general multi-sport policy document),
extracts their text, and writes `reports/hw03/corpus/*.txt`,
`reports/hw03/CORPUS_MANIFEST.json`, and `reports/hw03/SOURCES.md` with
real SHA-256 hashes and byte sizes. Total corpus: ~227KB (exceeds the
200KB requirement).

### Domain questions

`reports/hw03/questions.yaml` contains 5 domain questions with expected
answers and expected source files, committed before any retrieval was
run.

### Run the chunking comparison

```powershell
pip install llama-index llama-index-embeddings-huggingface sentence-transformers faiss-cpu numpy pandas pyyaml
python rag_chunking_comparison.py
```
Builds three separate in-memory vector indexes (Token, Semantic,
Sentence-window chunking) over the corpus using
`sentence-transformers/all-MiniLM-L6-v2` embeddings, then runs a
retrieval-only comparison against all 5 questions for each technique
(15 total retrievals). Prints and saves query embeddings, store scores,
cosine similarities, chunk lengths, and previews to
`reports/hw03/raw/chunking_comparison_raw.json` and `.csv`.

Note: Semantic chunking embeds during chunking itself and is noticeably
slower to build than the other two techniques.

### Recompute the summary table

```powershell
python summarize_chunking_comparison.py
```
Reads the saved raw results and computes the final comparison table
(chunks, avg chunk length, top-1 cosine, mean@k cosine, recall@k, mean
latency) per technique. See `reports/hw03/METRICS.md` for the results
and written analysis, including a specific confidently-scored retrieval
that missed its expected source document.

## HW3 Verification

```powershell
python verify_hw03.py
```
Confirms required files exist, actually starts the FastAPI app and
confirms both the home page responds and unauthenticated `/dashboard`
access is correctly blocked, and recomputes SHA-256 hashes for every
corpus file to confirm they still match `CORPUS_MANIFEST.json`. Writes
to `reports/hw03/verification.json`.