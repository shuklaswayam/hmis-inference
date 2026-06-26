import axios from 'axios';

// Read the backend's base URL from the Vite env at build time.
// Override by setting VITE_API_BASE_URL in frontend/.env (see frontend/.env.example).
// Trailing slashes are stripped so paths like '/api/v1/foo' concatenate cleanly.
const rawBase = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').trim();
const baseURL = rawBase.replace(/\/+$/, '');

// Optional shared secret — when DEPLOY's API_KEY is set on the backend, this
// header is added to every request so the SPA can talk to the gated API.
// Build-time only: pass `VITE_API_KEY=…` to `npm run build`.
const apiKey = (import.meta.env.VITE_API_KEY || '').trim();

const client = axios.create({
  baseURL,
  // Generous timeout — backend Groq synthesis can be slow on long contexts
  // (httpx read timeout is 600s in synthesizer.py).
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
    ...(apiKey && { 'X-API-Key': apiKey }),
  },
});

export default client;
