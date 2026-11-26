# Run the app with PostgreSQL and customer sign-in

For the schema, table relationships, and examples of when records are created, see [Database design](DATABASE_DESIGN.md).

From the project root in PowerShell:

```powershell
.\database\Initialize-ClaimsDatabase.ps1
```

The script can rerun on the existing empty PostgreSQL database. Use the local administrator password when PostgreSQL prompts for it and choose a separate password for the `claims_app` role.

Save the database connection once in `.streamlit/secrets.toml`. Use the existing `claims_app` password and percent-encode reserved URL characters in it. Git ignores this file.

```toml
[database]
url = "postgresql://claims_app:PASSWORD@127.0.0.1:5432/healthcare_claims"
```

```powershell
.\Start-ClaimsAssist.ps1
```

Select **Create account** to register with an email and password, then select **Sign in**. Refreshing or reopening the app may require signing in again.

## PDF file storage

The setup script applies `001_initial.sql` to fresh and existing databases. Run it before starting this version. New claim PDFs go into `.claims-data/documents` by default when using the React API. PostgreSQL keeps each document's owner, generated relative file key, original filename, and SHA-256 checksum. Older documents with embedded PDF bytes remain readable.

Set `CLAIMS_DOCUMENT_DIR` to a private, writable folder to use a different location. To move the folder later, stop the app, copy the PDFs to the new folder with the same filenames, and start the app with the updated setting. Back up the PDF folder with PostgreSQL so a restore keeps both the records and the files.
