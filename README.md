\# Stock Analysis MVP



A stock analysis platform prototype for U.S. stocks.



\## Features



\- Daily price ingestion

\- Technical indicators (MA20, MA60, RSI14, VOL20)

\- Structured score snapshots

\- AI explanation

\- Streaming AI strategy assistant



\## Project Structure



\- `backend/`: FastAPI backend, analytics, refresh jobs, database logic

\- `frontend/`: HTML + JavaScript frontend



\## Tech Stack



\- Python

\- FastAPI

\- SQLite

\- ECharts

\- OpenAI API



\## Architecture



provider -> analytics -> refresh -> database -> API -> frontend

