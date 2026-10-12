# Loan Strategy Agent

An AI-driven banking advisor that analyzes personal loan requirements, compares offers across bank catalogs, and enforces financial grounding guardrails to prevent hallucinations.

## Key Features
- **Smart Loan Advisory:** Dynamic conversational engine for loan recommendations.
- **Strict Grounding:** Verification layer ensuring EMI and profit rates match tool data.
- **Scope Guardrails:** Out-of-Scope query filter to keep interactions strictly financial.
- **Context Persistence:** Session state restoration via MongoDB Atlas.
- **PDF Export:** Production-grade report generation powered by ReportLab.

## Tech Stack
- **Backend:** Django, Python, MCP Server, Groq LLM
- **Database:** MongoDB Atlas
- **Frontend:** React, Vite, Tailwind CSS
