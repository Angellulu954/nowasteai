# NoWaste AI

Turn leftovers into meals — a Python (Flask) + HTML/CSS + SQLite web app that suggests recipes from what you already have, helping reduce food waste.

## Features
- Ingredient input (guest) or pantry saved to your account
- Recipe suggestions with "have" vs "missing" ingredients
- Approximate nutrition info
- Save favorites
- Simple API endpoint: `POST /api/nutrition` with `{"ingredients": "rice,tomato"}`

## Tech Stack
- Backend: Flask (Python)
- Frontend: HTML + CSS (vanilla)
- Database: SQLite (file: `database.db`)
- Data: `data/recipes.json`
- Auth: hashed passwords (PBKDF2)

## Run Locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export FLASK_APP=app.py
flask run  # http://127.0.0.1:5000
```

## Deploy (Render/Heroku/VPS)
- Set `FLASK_SECRET_KEY` env var.
- Use `gunicorn` if your platform requires it and add a `Procfile` with: `web: gunicorn app:app`
- Persist `database.db` or use a managed SQLite/Postgres.

## Notes
This demo uses a small offline recipe dataset for judging convenience. You can expand `data/recipes.json` or connect a larger dataset/API.
