# Python backend

The backend is split by responsibility:

- `api/`: FastAPI endpoints and claim document orchestration.
- `auth/`: customer registration and sign-in.
- `documents/`: hospital PDF extraction, bill parsing and review.
- `claims/`: diagnosis mapping and reimbursement estimate calculations.
- `policies/`: policy room limits and waiting-period rules.
- `ai/`: Ollama requests, policy retrieval, chat and Chroma embeddings.
- `storage/`: PostgreSQL access and saved claim/review storage.
- `reference/`: ICD-10 and IRDAI reference data access.

Run the application from the project root with `Start-ClaimsAssist.ps1`. Python imports use the `backend` package; project data and configuration stay in their existing root directories.
