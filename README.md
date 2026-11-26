# Claims Assist

Claims Assist is a healthcare insurance claim review prototype. It extracts details from hospital documents, searches an uploaded policy, checks waiting periods, and calculates an estimated reimbursement using reviewed bill amounts.

## Screenshots

The screenshots show a synthetic example claim.

### Claim dashboard

![Claim dashboard showing patient, policy, documents, and net bill](docs/screenshots/claim-dashboard.png)

### Bill summary

![Bill summary with itemized hospital charges](docs/screenshots/bill-summary.png)

### Estimate and deductions

![Estimated reimbursement and deductions](docs/screenshots/estimate.png)

## Features

- Customer sign-up and login with separate claims for each patient.
- Upload policies and hospital PDFs, and reuse a saved policy for another family member's claim.
- Review extracted patient details, diagnosis, ICD-10 suggestions, and itemized bills.
- Search policy and hospital document passages and ask questions in the claim assistant.
- Check supported waiting periods against policy start and admission dates.
- Review remaining cover, co-payment, and deductions before calculating an estimate.
- Consult bundled IRDAI references and compare identified waiting periods with the displayed regulatory limit.

## Technology stack

| Component | Technology |
| --- | --- |
| Frontend | React, Vite, CSS |
| Backend | Python, FastAPI |
| Customer data | PostgreSQL with row-level security |
| Documents | PyMuPDF and Tesseract OCR |
| AI and search | Ollama, Qwen, embeddinggemma, Chroma |
| Reference data | WHO ICD-10 2019 and IRDAI documents |

## How it works

1. A customer uploads a policy and hospital documents to a claim.
2. The backend extracts PDF text and identifies claim details. Tesseract supports scanned pages when installed.
3. The app splits policy text into searchable passages. Ollama creates embeddings, and Chroma stores the policy index for reuse.
4. Chat retrieves relevant policy or hospital passages for the local language model. Answers can include source pages.
5. Python calculates waiting-period dates and reimbursement estimates using the available policy and reviewed bill values.

## Retrieval-augmented generation (RAG)

RAG helps the assistant answer questions using relevant text from the customer's documents. The application first retrieves passages that may answer a question, then sends those passages to the local language model as context.

### Preparing a policy

The backend extracts text from the uploaded policy PDF and divides it into passages with page references. Ollama's `embeddinggemma` model converts the passages into embeddings, which are numerical representations of their meaning. Chroma stores those embeddings in a customer-scoped policy index. Once prepared, the same index can be reused for that customer's claims using the same policy.

### Answering a question

1. The app searches the policy passages by keywords. When the semantic index is available, it also embeds the question and searches Chroma for passages with similar meanings.
2. The app combines the retrieved policy results. It can also retrieve relevant text from the selected hospital bill and matching discharge summary using keyword search.
3. The retrieved passages are supplied to the local Ollama language model, `qwen3:1.7b` by default. The model is asked to answer using the supplied evidence and cite supporting passages.
4. The app checks the returned citations and applies additional checks to some answers before displaying them. If it cannot verify an answer, it can say so.

For example, a customer can ask about a waiting period using a term different from the wording in the policy. Semantic search may retrieve the related clause, and the assistant can use its text and page reference in the response.

The policy is indexed for semantic search. Hospital passages are searched by keywords in the current chat flow. Extracted bill totals and saved estimates have dedicated handling, while Python calculates waiting-period dates and reimbursement amounts. Retrieval and model responses can still miss context or interpret wording incorrectly, so the user should review the cited documents.

## Run locally on Windows

Install Python 3.11, Node.js with npm, PostgreSQL, and Ollama. Install Tesseract for scanned PDFs. From the project directory in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
ollama pull qwen3:1.7b
ollama pull embeddinggemma
.\database\Initialize-ClaimsDatabase.ps1 -SetAppPassword
```

Configure the PostgreSQL connection using the [database setup guide](database/README.md), ensure Ollama and PostgreSQL are running, and then start the app:

```powershell
.\Start-ClaimsAssist.ps1
```

Open [Claims Assist](http://127.0.0.1:8000), create an account, and start a claim. Use a policy PDF and a synthetic hospital bill or discharge summary you can share. Review the extracted details and policy conditions before calculating an estimate.

### Optional Google sign-in

Create a Google Cloud project and configure its OAuth consent screen. Create a Web application OAuth client and add `http://localhost` and `http://localhost:8000` as authorized JavaScript origins. In the PowerShell session used to start the app, set:

```powershell
$env:GOOGLE_CLIENT_ID = "YOUR_CLIENT_ID.apps.googleusercontent.com"
.\Start-ClaimsAssist.ps1
```

Open `http://localhost:8000` to use the Google button. Google accounts and email/password accounts are separate, including when they have the same email. Existing accounts are not automatically linked.

The database setup script defaults to PostgreSQL 18 at `C:\Program Files\PostgreSQL\18\bin\psql.exe`. If PostgreSQL is installed elsewhere, pass the correct path:

```powershell
.\database\Initialize-ClaimsDatabase.ps1 -Psql 'C:\path\to\psql.exe' -SetAppPassword
```

The script asks for the PostgreSQL administrator password and sets a separate password for the `claims_app` role. Create `.streamlit/secrets.toml` with that application role's credentials:

```toml
[database]
url = "postgresql://claims_app:YOUR_PASSWORD@127.0.0.1:5432/healthcare_claims"
```

Percent-encode special characters in the password when using a connection URL. The secrets file is ignored by Git. You can use `CLAIMS_DATABASE_URL` instead.

## Try a claim

Sample policy wordings are in `healthcare/policy_fixtures/`. Fictional hospital bills and discharge summaries are in `healthcare/synthetic_indian_hospital_documents/` and `healthcare/synthetic_hospital_test_set_H01_H06/`. For a first walkthrough, use `Policy_SuperStar.pdf` with `H01_final_bill.pdf` and `H01_discharge_summary.pdf`.

1. Create a claim and upload a policy PDF.
2. Upload a synthetic hospital bill and discharge summary for the same patient.
3. Review the extracted details and bill amounts. Enter the policy start date to check a supported waiting period.
4. Ask a question in the claim assistant and inspect the cited pages.
5. Review remaining cover, co-payment, and deductions before calculating an estimate.

## Architecture

- `frontend/src/` contains the React interface. FastAPI serves the built frontend and API from the same host.
- `backend/api/react_api.py` and `backend/api/react_claims.py` handle authentication, claim workflows, and document processing.
- `database/` contains the PostgreSQL setup script and schema. Row-level security scopes claim data to the signed-in customer.
- Ollama handles chat and embeddings locally. Chroma stores the policy search index. New PDFs are stored in a private local folder, with references in PostgreSQL.

## Data and configuration

PostgreSQL stores customer accounts, claim records, reviews, and chat history. New PDFs are stored in `.claims-data/documents`, with generated file keys and checksums in PostgreSQL. Existing database-stored PDFs remain readable. Chroma indexes are stored in `.claims-data/policy_vectors`.

Set `CLAIMS_DOCUMENT_DIR` to change the PDF folder, or `CLAIMS_DATA_DIR` to change the base local-data folder. `CLAIMS_AI_MODEL` and `CLAIMS_EMBEDDING_MODEL` select locally installed Ollama models. On Windows, `TESSERACT_CMD` can point to a Tesseract executable in a different location.

Back up PostgreSQL and the PDF folder together. The browser stores the light or dark theme preference locally.

## Scope and limitations

This prototype is intended for reviewing synthetic documents. Extracted diagnoses, policy clauses, AI answers, and waiting-period suggestions require review. The reimbursement figure is an estimate based on the available inputs and does not represent an insurer's claim decision. Extraction and policy interpretation may be incomplete for unfamiliar document formats.
