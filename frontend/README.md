# React customer workspace

React and Vite render the customer interface. FastAPI serves the built application and the same-origin API. PostgreSQL uses the existing account and claim tables, while the Python services still handle PDF reading, OCR, Ollama, Chroma, and reimbursement calculations.

## Build and run

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
.\Start-ClaimsAssist.ps1
```

Open http://127.0.0.1:8000. On later launches, run only the start script. Rebuild after editing the frontend. Use `-Port 8001` on the start script if port 8000 is in use.

The API reads the existing PostgreSQL URL from `.streamlit/secrets.toml` or `CLAIMS_DATABASE_URL`. Existing customers sign in with their current passwords. Existing claims remain in the same database. Ollama must run locally for AI answers and embeddings. Scanned bills require Tesseract.

React stores Chroma indexes in the Git-ignored `.claims-data/policy_vectors` directory by default. To change it, set `CLAIMS_DATA_DIR` to a writable directory before starting the API. If you were using an older cache location, rebuild the index from your saved policy when prompted.

## Where the code lives

- `src/main.jsx` renders account screens, uploads, claim selection, policy chat, PDF previews, reviews and estimates.
- `src/styles.css` controls the responsive layout.
- `../backend/api/react_api.py` provides API routes and ties each request to the authenticated customer.
- `../backend/api/react_claims.py` prepares document groups and reviewed values for the API.

The prototype uses an HTTP-only session cookie with a server-side session that expires in eight hours. Restarting the Python server requires signing in again. Saved claims retain chat questions, answers and citations in PostgreSQL. The workspace loads the latest 100 turns for the selected claim.

For an existing database, run `.\database\Initialize-ClaimsDatabase.ps1` to apply the schema updates. Then rebuild the frontend and restart the server.
