.PHONY: setup db db-reset api agent web test chat chat-local sim sim-local

setup:            ## install everything
	cd backend && uv sync
	cd frontend && pnpm install
	cd backend && uv run python -m voisai.agent.worker download-files

db:               ## start Postgres + pgvector and create the schema
	docker compose up -d --wait db
	cd backend && uv run python -m voisai.db

api:              ## token + data API on :8000
	cd backend && uv run uvicorn voisai.api.main:app --reload --port 8000

agent:            ## voice agent worker (connects to LiveKit)
	cd backend && uv run python -m voisai.agent.worker dev

web:              ## Next.js on :3000
	cd frontend && pnpm dev

test:
	cd backend && uv run pytest -q && uv run ruff check .
	cd frontend && pnpm lint && pnpm exec tsc --noEmit

db-reset:         ## drop and recreate the schema (prototype has no migrations yet)
	docker compose exec -T db psql -U voisai -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
	cd backend && uv run python -m voisai.db

chat:             ## text chat with Maya in the terminal (same pipeline, no audio)
	cd backend && uv run python -m voisai.agent.textchat

sim:              ## simulated learners + random-planner control (cloud keys from .env)
	cd backend && uv run python -m sim.run --sessions 6 --turns 5 --tag main
	cd backend && uv run python -m sim.run --personas sim-rahul --sessions 6 --turns 5 --planner random --tag control

LOCAL = set -a; . ./.env.local-llm; set +a;

sim-local:        ## same, fully offline on local Ollama (qwen3.5:9b)
	cd backend && $(LOCAL) uv run python -m sim.run --sessions 6 --turns 5 --tag main
	cd backend && $(LOCAL) uv run python -m sim.run --personas sim-rahul --sessions 6 --turns 5 --planner random --tag control

chat-local:       ## terminal chat with Maya on local Ollama
	cd backend && $(LOCAL) uv run python -m voisai.agent.textchat
