# Resume Tailor

## Local setup

1. Copy `.env.example` to `.env.local`
2. Set `OPENAI_API_KEY`, `APP_PASSWORD`, and `SESSION_SECRET` in `.env.local`
3. Run `npm install`
4. Run `npm run dev`
5. Open `http://localhost:3000`

## Production check

1. Run `npm run build`
2. Run `npm start`

## Vercel environment variables

Set these in the Vercel project settings:

- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `APP_PASSWORD`
- `SESSION_SECRET`

`APP_PASSWORD` protects the whole site behind a login screen. `SESSION_SECRET` signs the session cookie.

## Security notes

- Rotate any OpenAI key that was ever pasted into a tracked file or shared in chat.
- `.env*` files are ignored now, except for `.env.example`.
- The app now uses password protection, signed cookies, same-origin checks, rate limiting, and production security headers.
