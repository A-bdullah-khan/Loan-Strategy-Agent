# Loan Strategy Agent — Autonomous AI Financial & Banking Advisor

A conversational loan advisor for borrowers in Pakistan. It gathers a borrower's requirements in natural language (English, Urdu, or Roman Urdu), checks eligibility against the State Bank of Pakistan's 50% debt-to-income rule, ranks real bank loan policies, and explains the result like a human advisor would — while a grounding layer makes sure every bank name, installment, and profit rate it quotes came from the underlying data.

## Features

- **Conversational AI advisor** — powered by a Groq-hosted LLM, orchestrated through LangChain tool calling over an in-process MCP (Model Context Protocol) tool server. The agent fills five loan parameters conversationally, then calls eligibility and policy-search tools on the borrower's behalf.
- **Multi-turn state restoration and context persistence** — every turn is stored in MongoDB (Atlas or local). Conversation history and the active loan request are restored server-side on each request, so follow-ups such as "it is too much" or "show me a lower price" are answered in context, and adjustments (longer tenure, smaller amount, lowest-rate bank) are recalculated and saved as a new report.
- **Anti-hallucination grounding engine** — the model writes its replies from a compact, structured tool payload. Before a reply is sent, every percentage and rupee amount in it is verified against the tool outputs; a reply that quotes an ungrounded figure is replaced with a deterministic summary.
- **Boundary enforcement guardrail** — the agent is strictly a loan, banking, and financial planning advisor. Off-topic queries (general knowledge, politics, coding) are routed through a dedicated out-of-scope intent and politely declined in the model's own words.
- **PDF report engine** — built on ReportLab, with a two-pass multi-page canvas ("Page X of Y" headers and footers), auto-wrapping table cells, and HTML entity escaping of all dynamic text.
- **Live bank policy catalog** — scrapers and an LLM extraction agent sync loan policies from bank websites into PostgreSQL.
- **JWT-secured API** — registration, login, and per-user scoping of chat sessions and reports.

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, Django, Django REST Framework, SimpleJWT |
| AI orchestration | Groq LLM, LangChain (`langchain-groq`), MCP (`FastMCP`), LangGraph |
| Data | PostgreSQL (users, banks, policies, loan requests), MongoDB Atlas (chat history) |
| Reports | ReportLab |
| Frontend | React, Vite, Tailwind CSS |

## Project Structure

```
backend/
  config/        Django settings, URLs, MongoDB client
  mcp_server/    Chat agent loop, MCP tools, chat API, history persistence
  services/      Loan scoring, report data, PDF export, LLM provider
  agents/        LLM policy extraction agent
  scrapers/      Bank website scrapers and sync command
  banks/         Bank and loan policy models
  users/         Auth, chat sessions, loan requests
frontend/        React + Vite single-page app
requirements.txt Python dependencies
```

## Installation & Setup

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL
- MongoDB (an Atlas cluster or a local instance)
- A [Groq API key](https://console.groq.com/)

### 1. Clone and create a virtual environment

```bash
git clone <your-repo-url>
cd Loan-Strategy-Agent

python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

Edit `backend/.env`:

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django secret key; also signs JWTs |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | Groq model id (defaults to `openai/gpt-oss-120b`) |
| `MONGO_URI` | MongoDB connection string, including the database name |

`frontend/.env` holds `VITE_API_BASE_URL` (defaults to `http://localhost:8000/api`).

### 3. Create the database and run migrations

Create the PostgreSQL database named in `DB_NAME`, then:

```bash
cd backend
python manage.py migrate
```

Optionally load the bank policy catalog from the live scrapers:

```bash
python manage.py run_scrapers
```

### 4. Run the tests

```bash
python manage.py test
```

### 5. Start the development servers

```bash
# Terminal 1 — backend (http://localhost:8000)
cd backend
python manage.py runserver

# Terminal 2 — frontend (http://localhost:5173)
cd frontend
npm install
npm run dev
```

## Testing

The backend ships with 68 unit and integration tests, run with `python manage.py test`:

- **Agent loop** — follow-up and adjustment flows, ambiguous confirmations, context restoration from stored history, and the out-of-scope guardrail, run against the real tool server with a scripted model.
- **Grounding checks** — fabricated installments, profit rates, and bank names are rejected in favour of the deterministic summary.
- **Report services** — structured report building, the reports API, and per-session report scoping and cascade deletion.
- **Auth and scrapers** — registration, login, per-user chat scoping, and policy parsing and persistence.

## API Overview

All endpoints except registration and login require `Authorization: Bearer <access token>`.

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/auth/register/` | Create an account |
| `POST` | `/api/auth/login/` | Obtain access and refresh tokens |
| `POST` | `/api/auth/token/refresh/` | Refresh an access token |
| `POST` | `/api/chat/` | Run one turn of the advisor |
| `GET` | `/api/chat/history/?session_id=` | Reload a conversation |
| `DELETE` | `/api/chat/history/<session_id>/` | Delete a conversation and its reports |
| `GET` | `/api/reports/?chat_id=` | List reports for a chat session |
| `GET` | `/api/reports/<id>/` | Fetch one report |
| `GET` | `/api/reports/export-pdf/?loan_request_id=` | Export a report as PDF |

## Disclaimer

This project is an advisory and comparison tool. It does not submit loan applications, and its output is not financial advice; confirm all rates and terms with the bank before making a decision.
