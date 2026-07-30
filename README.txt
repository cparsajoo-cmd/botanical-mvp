Replace these three files in the repository root:
- rate_limit_guard.py (new file)
- openalex_connector.py
- semantic_scholar_connector.py

Optional Streamlit secrets (recommended):
OPENALEX_CONTACT_EMAIL = "your-email@example.com"
SEMANTIC_SCHOLAR_API_KEY = "your-free-api-key"

The connectors still allow the rest of Step 2 to continue when a source is rate-limited. After repeated HTTP 429 responses, a process-local cooldown prevents every plant from immediately retrying the same limited service.
