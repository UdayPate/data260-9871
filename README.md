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
├── code/                    - shared application code (extended each HW)
│   ├── web_application/     - index.html, app.js (HW1 Part 1)
│   ├── Dockerfile
│   ├── agents_demo.py       - HW1 Part 2
│   ├── measure_nondeterminism.py  - HW1 Part 3
│   ├── hw1_client.py        - HW1 Part 4
│   ├── verify_hw01.py       - self-check script
│   └── venv/                - Python 3.12 virtual environment (gitignored)
├── src/
│   └── model_client.py      - reusable model adapter (HW1 Part 4)
├── reports/
│   └── hw01/                - HW1 deliverables (report, metrics, logs, raw data)
├── AGENT.md                 - system prompt for hw1_client.py's code-review agent
├── DOMAIN_SCHEMA.md          - HW1 domain entity schema
└── README.md
```

## Prerequisites

- Python 3.12 (NOT 3.13 - langchain has a numpy compatibility issue on 3.13)
- [Ollama](https://ollama.com/download) installed and running, with `qwen3:8b` pulled
- Docker Desktop (for Part 1 deployment)
- An AWS account with the AWS CLI configured (for Part 1 ECS deployment)
- Git

## Setup

```powershell
# Clone the repo
git clone https://github.com/UdayPate/data260-9871.git
cd data260-9871

# Create and activate a Python 3.12 virtual environment
cd code
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1

# Install Python dependencies
pip install -r requirements.txt

# Pull the local model (if not already pulled)
ollama pull qwen3:8b
```

## Part 1 - Web application (HTML/JS + Docker + AWS ECS)

Run locally (no Docker):
Just open `code/web_application/index.html` directly in a browser.

Run in Docker:
```powershell
cd code
docker build -t data260-9871-app .
docker run -p 8871:8871 data260-9871-app
```
Then visit http://localhost:8871

AWS ECS deployment (summary - see reports/hw01/RUN_LOG.txt for the full
session): image was pushed to Amazon ECR, then run as a single Fargate
task in an ECS service with a security group allowing inbound TCP on
port 8871. The service was torn down after verification to avoid
ongoing AWS charges; it is not expected to be running at grading time.

## Part 2 - Agentic AI pipeline

```powershell
cd code
python agents_demo.py
```
Runs the Planner -> Reviewer -> Finalizer pipeline once on a fixed
sample fixture and prints all three stages plus the final JSON.

## Part 3 - Non-determinism measurement

```powershell
cd code
python measure_nondeterminism.py
```
Runs the same pipeline 20 times at temperature 0.7 and 20 times at
temperature 0.0 against the fixed input in
`reports/hw01/cases/nondeterminism_input.json`. Raw per-run results are
saved to `reports/hw01/raw/`; summary statistics are printed and also
saved to `reports/hw01/raw/nondeterminism_summary.json`. See
`reports/hw01/METRICS.md` for the filled-in results tables.

Note: this takes a while (40 total pipeline runs, each with 2 LLM
calls) - expect anywhere from ~10 minutes to over an hour depending on
hardware.

## Part 4 - Model client and token accounting

```powershell
cd code
python hw1_client.py
```
Starts an interactive chat loop using the reusable adapter in
`src/model_client.py`. The system prompt is loaded from `AGENT.md`
(instructs the model to act as a strict, bullet-only code reviewer).
Commands:
- Type any message to chat normally.
- `/stats` - shows turn count, cumulative token counts, and serialized
  conversation-history length, without altering the history.
- `/exit` - prints a final cumulative token summary and quits.

## Verification

```powershell
cd code
python verify_hw01.py
```
Runs a self-check confirming required files are present, the model
adapter imports correctly, and the full agent pipeline runs end-to-end
producing valid JSON. Writes results to `reports/hw01/verification.json`.