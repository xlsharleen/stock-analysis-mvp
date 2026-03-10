# AI Stock Analysis Platform

A prototype platform for analyzing U.S. stocks with technical indicators and AI-assisted insights.

This project demonstrates a modular data pipeline, reproducible decision snapshots, and AI-driven explanations.

---

## Features

- Daily stock price ingestion
- Technical indicators (MA20, MA60, RSI14, VOL20)
- Structured score snapshots for reproducible analysis
- AI explanation of trading signals
- AI trading strategy assistant (streaming response)
- Interactive dashboard with price charts

---

## System Architecture

The system separates data ingestion, analytics, and serving layers.

Data Provider
↓
Technical Indicators (analytics.py)
↓
Daily Refresh Pipeline (refresh.py)
↓
Database (SQLite)
↓
FastAPI Backend (app.py)
↓
Frontend Dashboard
↓
AI Explanation & Strategy



This architecture ensures:

- deterministic scoring
- reproducible historical analysis
- stable API performance

---

## Project Structure

backend/
app.py FastAPI API service
refresh.py Offline data refresh pipeline
analytics.py Technical indicator computation
data_provider.py Stock data ingestion
db.py Database access layer
requirements.txt Python dependencies

frontend/
index.html Dashboard UI

---

## Tech Stack

Backend

- Python
- FastAPI
- SQLite

Frontend

- HTML
- JavaScript
- ECharts

AI

- OpenAI API

---

## Run Locally

### 1. Install dependencies
pip install -r backend/requirements.txt
### 2. Run the refresh pipeline
python backend/refresh.py

This step downloads price data and computes indicators.

### 3. Start the backend
uvicorn backend.app:app --host 0.0.0.0 --port 8000



### 4. Open the dashboard

Open:
frontend/index.html



in your browser.

---

## Future Improvements

- Add backtesting module
- Support portfolio tracking
- Add Redis caching
- Deploy backend to cloud (AWS / Render)
- Support news sentiment analysis

---

## Author

GitHub: https://github.com/xlsharleen