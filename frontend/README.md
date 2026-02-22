# Frontend

## Run

1. Start backend:
   - `python main.py`
2. Install frontend deps:
   - `cd frontend`
   - `npm install`
3. Start frontend:
   - `npm run dev`

Vite runs on `http://localhost:5173` and proxies API calls to `http://127.0.0.1:8000`.

## Optional API base override

If you want direct API calls without proxy, set:

- `VITE_API_BASE_URL=http://127.0.0.1:8000`
