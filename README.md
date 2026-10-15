# Loan Strategy Agent

An AI-driven banking advisor that analyzes personal loan requirements, compares offers across bank catalogs, and enforces financial grounding guardrails to prevent hallucinations.

## Key Features

- **Smart Loan Advisory** – Conversational, slot-filling engine that collects loan type, amount, tenure, income, and Islamic/conventional preference, then ranks matching bank policies.
- **Strict Grounding** – Every reply is checked against the MCP tool output; EMI figures, profit rates, and bank names that do not match tool data are rejected and replaced.
- **Scope Guardrails** – Out-of-scope queries are flagged via a dedicated `flag_out_of_scope` tool and declined without running the loan pipeline.
- **Context Persistence** – Chat transcripts and slot state are stored in MongoDB Atlas; a session restores its loan context server-side even if the client drops it.
- **PDF Export** – Loan comparison reports generated with ReportLab.

## Tech Stack

| Layer    | Technologies                                              |
| -------- | --------------------------------------------------------- |
| Backend  | Python, Django, Django REST Framework, MCP (FastMCP), Groq |
| Database | MongoDB Atlas (chat history), PostgreSQL / SQLite (users, banks, policies, loan requests) |
| Frontend | React, Vite, Tailwind CSS                                 |

## System Architecture

```
React (Vite)        Django API           MCP Server          Groq LLM         MongoDB Atlas
     |                  |                     |                   |                  |
     |-- POST /api/chat/ ->                   |                   |                  |
     |                  |-- load session history ---------------------------------->|
     |                  |<-- prior turns + slot state ------------------------------|
     |                  |-- prompt + tool schemas ------------------>|               |
     |                  |<-- tool calls -----------------------------|               |
     |                  |-- call_tool() ----->|                   |                  |
     |                  |   (search_loans,    |-- query policies (SQL DB)            |
     |                  |    eligibility,     |                   |                  |
     |                  |    bank details)    |                   |                  |
     |                  |<-- tool results ----|                   |                  |
     |                  |-- tool results ---------------------------->|              |
     |                  |<-- draft reply -----------------------------|              |
     |                  |-- grounding check (numbers vs. tool data)   |              |
     |                  |-- save user + assistant turns ---------------------------->|
     |<-- reply, state, report                |                   |                  |
     |                  |                     |                   |                  |
     |-- GET /api/reports/export-pdf/ ->      |                   |                  |
     |<-- PDF (ReportLab)                     |                   |                  |
```

The MCP server runs in-process with Django: `mcp_server/agent.py` invokes tools defined in `mcp_server/server.py` through the standard `FastMCP.call_tool` API.

## Project Structure

```
backend/
  config/        Django settings, URLs, MongoDB client
  mcp_server/    Chat agent, MCP tools, grounding, chat history
  banks/         Bank and LoanPolicy models
  scrapers/      Bank policy scrapers (run_scrapers command)
  services/      LLM provider, financial calculator, reports, PDF export
  users/         Auth (JWT), profiles, loan requests
frontend/        React + Vite client
requirements.txt
```

## Local Setup

**Prerequisites:** Python 3.12+, Node.js 20.19+, a Groq API key, and a MongoDB URI (Atlas or local). PostgreSQL is optional; without `DB_*` variables the backend falls back to SQLite.

### Backend

```bash
git clone <repo-url>
cd Loan-Strategy-Agent

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp backend/.env.example backend/.env   # set DJANGO_SECRET_KEY, GROQ_API_KEY, MONGO_URI, DB_*

cd backend
python manage.py migrate
python manage.py run_scrapers          # populate bank loan policies
python manage.py runserver             # http://localhost:8000
```

Run the test suite:

```bash
cd backend
python manage.py test
```

### Frontend

In a separate terminal:

```bash
cd frontend
cp .env.example .env                   # VITE_API_BASE_URL=http://localhost:8000/api
npm install
npm run dev                            # http://localhost:5173
```

## Author

Abdullah Haroon Khan
