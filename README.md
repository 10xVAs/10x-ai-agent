# 10x AI Agent

Claude-powered AI assistant for 10xVAs clients. v1 is a single-tenant Telegram bot; v1.1+ will support multi-tenant access via the existing Telegram Mini App.

## Architecture
- **Backend:** FastAPI on Railway
- **Database:** Supabase (Postgres)
- **AI:** Anthropic Claude Sonnet 4.5 with tool use
- **Frontend (v1):** Telegram Bot
- **Frontend (v1.1+):** Telegram Mini App "My AI" tab

## Status
- [x] Phase 1: Echo bot (infra sanity check)
- [ ] Phase 2: Claude integration (conversational, no tools)
- [ ] Phase 3: GHL tools
- [ ] Phase 4: Google Workspace tools (OAuth)
- [ ] Phase 5: Web tools + polish

## Local development
```bash
py -3.12 -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Fill in .env with real values, then:
uvicorn app.main:app --reload
```