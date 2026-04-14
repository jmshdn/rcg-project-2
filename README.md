# Resume Tailor

## Local setup

1. Copy `.env.example` to `.env`
2. Set `OPENAI_API_KEY`, `APP_PASSWORD`, and `SESSION_SECRET` in `.env`
3. Create and activate a virtual environment
4. Run `pip install -r requirements.txt`
5. Run `python -m playwright install chromium`
6. Run `python -m uvicorn main:app`
7. Open `http://127.0.0.1:8000`

On Windows, do not use `--reload` with this app. Playwright needs a subprocess-capable event loop to launch Chromium for PDF generation, and `uvicorn --reload` switches to a loop mode that breaks that.

## Production check

1. Install the dependencies from `requirements.txt`
2. Install Chromium with `python -m playwright install chromium`
3. Run `python -m uvicorn main:app --host 0.0.0.0 --port 8000`

## Vercel environment variables

Set these in the Vercel project settings:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `APP_PASSWORD`
- `SESSION_SECRET`

`APP_PASSWORD` protects the whole site behind a login screen. `SESSION_SECRET` signs the session cookie.

## Vercel deploy notes

- The project is now a FastAPI app with a top-level `index.py` entrypoint for Vercel.
- Vercel detects the Python app from `requirements.txt` and `index.py`.
- `pyproject.toml` runs `python -m playwright install chromium` during build so PDF generation has a browser available.

## Security notes

- Rotate any OpenAI key that was ever pasted into a tracked file or shared in chat.
- `.env*` files are ignored now, except for `.env.example`.
- The app now uses password protection, signed cookies, same-origin checks, rate limiting, and production security headers.
