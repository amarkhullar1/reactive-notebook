# Reactive Notebook - Makefile
# Useful commands for development and deployment

.PHONY: help install install-backend install-frontend \
        dev dev-backend dev-frontend \
        start stop restart \
        build prod \
        test test-backend test-watch \
        clean lint

# Colors for terminal output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

# Default target
help:
	@echo "$(CYAN)Reactive Notebook - Available Commands$(RESET)"
	@echo ""
	@echo "$(GREEN)Installation:$(RESET)"
	@echo "  make install          Install all dependencies (backend + frontend)"
	@echo "  make install-backend  Install Python dependencies"
	@echo "  make install-frontend Install Node.js dependencies"
	@echo ""
	@echo "$(GREEN)Development:$(RESET)"
	@echo "  make dev              Start both backend and frontend in dev mode"
	@echo "  make dev-backend      Start backend only (with hot reload)"
	@echo "  make dev-frontend     Start frontend only (Vite dev server)"
	@echo ""
	@echo "$(GREEN)Production:$(RESET)"
	@echo "  make build            Build frontend for production"
	@echo "  make prod             Build and start in production mode"
	@echo "  make start            Start backend server (serves built frontend)"
	@echo "  make stop             Stop all running servers"
	@echo "  make restart          Restart the application"
	@echo ""
	@echo "$(GREEN)Testing:$(RESET)"
	@echo "  make test             Run all backend tests"
	@echo "  make test-watch       Run tests in watch mode"
	@echo ""
	@echo "$(GREEN)Maintenance:$(RESET)"
	@echo "  make clean            Remove build artifacts and cache"
	@echo "  make lint             Check code for linting errors"

# ============================================================
# Installation
# ============================================================

install: install-backend install-frontend
	@echo "$(GREEN)✓ All dependencies installed$(RESET)"

install-backend:
	@echo "$(CYAN)Installing backend dependencies...$(RESET)"
	@cd backend && python3 -m venv ../venv 2>/dev/null || true
	@. venv/bin/activate && pip install -r requirements.txt
	@. venv/bin/activate && pip install pytest pytest-watch
	@echo "$(GREEN)✓ Backend dependencies installed$(RESET)"

install-frontend:
	@echo "$(CYAN)Installing frontend dependencies...$(RESET)"
	@cd frontend && npm install
	@echo "$(GREEN)✓ Frontend dependencies installed$(RESET)"

# ============================================================
# Development
# ============================================================

dev:
	@echo "$(CYAN)Starting development servers...$(RESET)"
	@echo "$(YELLOW)Backend: http://localhost:8000$(RESET)"
	@echo "$(YELLOW)Frontend: http://localhost:5173$(RESET)"
	@make -j2 dev-backend dev-frontend

dev-backend:
	@echo "$(CYAN)Starting backend server (hot reload)...$(RESET)"
	@. venv/bin/activate && cd backend && uvicorn main:app --reload --port 8000

dev-frontend:
	@echo "$(CYAN)Starting frontend dev server...$(RESET)"
	@cd frontend && npm run dev

# ============================================================
# Production
# ============================================================

build:
	@echo "$(CYAN)Building frontend for production...$(RESET)"
	@cd frontend && npm run build
	@echo "$(GREEN)✓ Frontend built to frontend/dist/$(RESET)"

prod: build start

start:
	@echo "$(CYAN)Starting production server...$(RESET)"
	@echo "$(YELLOW)Server: http://localhost:8000$(RESET)"
	@. venv/bin/activate && cd backend && uvicorn main:app --host 0.0.0.0 --port 8000

stop:
	@echo "$(CYAN)Stopping all servers...$(RESET)"
	@pkill -f "uvicorn main:app" 2>/dev/null || true
	@pkill -f "vite" 2>/dev/null || true
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@lsof -ti:5173 | xargs kill -9 2>/dev/null || true
	@echo "$(GREEN)✓ All servers stopped$(RESET)"

restart: stop
	@sleep 1
	@make start

# ============================================================
# Testing
# ============================================================

test:
	@echo "$(CYAN)Running tests...$(RESET)"
	@. venv/bin/activate && cd backend && python -m pytest -v

test-watch:
	@echo "$(CYAN)Running tests in watch mode...$(RESET)"
	@. venv/bin/activate && cd backend && python -m pytest-watch

# ============================================================
# Maintenance
# ============================================================

clean:
	@echo "$(CYAN)Cleaning up...$(RESET)"
	@rm -rf frontend/dist
	@rm -rf frontend/node_modules/.vite
	@rm -rf backend/__pycache__
	@rm -rf backend/.pytest_cache
	@rm -rf venv
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(RESET)"

lint:
	@echo "$(CYAN)Checking code...$(RESET)"
	@. venv/bin/activate && cd backend && python -m py_compile *.py
	@cd frontend && npm run build -- --noEmit 2>/dev/null || echo "$(YELLOW)Frontend lint: run 'cd frontend && npx tsc --noEmit'$(RESET)"
	@echo "$(GREEN)✓ Lint check complete$(RESET)"

