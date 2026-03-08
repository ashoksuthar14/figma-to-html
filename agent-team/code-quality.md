# Code Quality Review

## 1. Code Organization

### Backend (Python/FastAPI)

**Rating: Good**

The backend follows a well-structured layered architecture with clear separation of concerns:

- **`agents/`** -- Pipeline agents (code_generator, fixer, verification, layout_strategy, componentizer, micro_fixer) each inherit from `BaseAgent` (`backend/agents/base.py:12`)
- **`routers/`** -- FastAPI route handlers (`jobs.py`, `ws.py`) handle HTTP/WebSocket concerns only
- **`services/`** -- Reusable services (`browser_service.py`, `diff_service.py`, `figma_api.py`, `openai_service.py`)
- **`schemas/`** -- Pydantic models for design specs, jobs, diff reports, and layout plans
- **`pipeline/`** -- Orchestrator and job manager coordinate the multi-agent pipeline
- **`prompts/`** -- External prompt templates (fixer.txt, fixer_typography.txt, fixer_spacing.txt, fixer_assets.txt)
- **`templates/`** -- HTML template and CSS reset

**Strengths:**
- Each agent encapsulates a single step of the conversion pipeline
- Pydantic models provide schema validation at system boundaries
- Prompt templates are externalized to text files
- Configuration is centralized in `config.py` using pydantic-settings

### Web App (TypeScript/Next.js)

**Rating: Good**

- **`components/`** -- 11 focused React components (PreviewFrame, ElementEditor, SpacingPanel, etc.)
- **`lib/`** -- Pure utility modules (api.ts, codeMutator.ts, domMapper.ts, websocket.ts, positionCalculator.ts)
- **`store/`** -- Single Zustand store (`useEditorStore.ts`)
- **`types/`** -- Centralized TypeScript types in `editor.ts`

**Strengths:**
- Clean separation between UI components, state management, and API calls
- Zustand store provides a single source of truth with explicit action methods
- Type definitions are comprehensive and well-organized

---

## 2. Design Patterns

| Pattern | Where Used | Notes |
|---------|-----------|-------|
| **Agent Pattern** | `backend/agents/` | Each pipeline step is an agent with `execute()` method via `BaseAgent` abstract class |
| **Pipeline/Orchestrator** | `backend/pipeline/orchestrator.py` | Multi-phase pipeline with fix loop: validation -> layout -> codegen -> verify -> fix -> componentize |
| **Repository Pattern** | `backend/db.py` | SQLite persistence with async functions for CRUD operations |
| **Observer/Callback** | `BaseAgent.set_progress_callback()` | Agents report progress via callbacks to WebSocket clients |
| **Strategy Pattern** | Layout decisions in `LayoutPlan` | `LayoutStrategy` enum (FLEX, GRID, ABSOLUTE, INLINE) determines per-node layout approach |
| **Centralized Store** | `web-app/store/useEditorStore.ts` | Zustand store with all state and actions for the editor UI |
| **API Wrapper** | `web-app/lib/api.ts` | Thin typed wrapper over fetch with centralized error handling |
| **Builder Pattern** | `_build_design_context()`, `_build_fix_prompt()` | Constructs complex prompt strings from structured data |

---

## 3. Error Handling

### Backend

**`backend/pipeline/orchestrator.py` (lines 246-769)**
- [Suggestion] The entire pipeline is wrapped in a single broad try/except at line 763. Individual stage failures within the fix loop (line 509) are handled gracefully with `consecutive_failures` tracking, but a failure in Stage 2 (layout) or Stage 3 (code generation) crashes the whole pipeline with a generic error message.
- [Warning] At line 309-314, Figma screenshot fetch failure logs a warning but continues, which is correct. However, the `except Exception` is very broad.

**`backend/routers/jobs.py` (lines 56-232)**
- [Good] Input validation with specific `HTTPException` status codes (422 for validation errors, 404 for not found, 400 for invalid state). Content-type handling at lines 74-126 covers JSON and multipart correctly.
- [Suggestion] Lines 78, 92, 107 catch `Exception` broadly during JSON parsing. Could use more specific exception types (e.g., `json.JSONDecodeError`, `pydantic.ValidationError`).

**`backend/services/browser_service.py`**
- [Warning] At line 145, `_time.sleep(1.0)` is a hardcoded blocking wait inside a thread. This adds 1 second to every single screenshot render. Should be configurable or replaced with an event-based wait.
- [Good] Browser is properly cleaned up with try/finally in `_render_sync()` (lines 158-159).

**`backend/agents/verification.py` (lines 105-106)**
- [Warning] Bare `except Exception: pass` silently swallows errors when opening the Figma screenshot image. Should at least log the error.

**`backend/db.py`**
- [Good] All database operations use try/finally to ensure connections are closed. Uses parameterized queries preventing SQL injection.
- [Suggestion] Each function opens and closes its own connection. A connection pool or context manager pattern would be more efficient.

### Frontend

**`web-app/lib/api.ts`**
- [Good] Centralized error handling in `apiFetch` (line 10-11) with status code and body in error messages.
- [Suggestion] No retry logic or timeout handling. Failed API calls could leave the UI in inconsistent states.

**`web-app/lib/codeMutator.ts`**
- [Good] `isUrlSafe()` function (lines 117-126) validates URLs against a safe protocol list before wrapping links, preventing XSS via `javascript:` URLs.
- [Suggestion] `updateTextContent()` (lines 10-37) uses string index manipulation instead of a proper DOM parser for text updates. While `getNodeInfo()` uses cheerio, text updates do manual string slicing which could break with nested elements.

---

## 4. Type Safety

### Python (Backend)

**Rating: Good with minor gaps**

- [Good] Extensive use of Pydantic models for all data structures (`DesignSpec`, `DiffReport`, `JobResult`, etc.) providing runtime validation
- [Good] Type hints on all major function signatures (e.g., `orchestrator.py:224`, `browser_service.py:163`, `diff_service.py:402`)
- [Good] `_CamelBase` model config (`design_spec.py:19-26`) handles camelCase/snake_case compatibility with the Figma plugin
- [Warning] `BaseAgent.execute()` (`agents/base.py:24`) uses `**kwargs -> Any` return type, losing type information for subclass-specific parameters. Each agent defines its own parameters but the base class can't enforce them.
- [Suggestion] `_progress_callback` at `base.py:21` is typed as `Optional[Any]` instead of a proper callable protocol type.

### TypeScript (Frontend)

**Rating: Very Good**

- [Good] Comprehensive type definitions in `types/editor.ts` (308 lines) covering all domain models
- [Good] `EditorState` interface (lines 239-307) fully types the Zustand store including all action method signatures
- [Good] API functions are generically typed (`apiFetch<T>` at `api.ts:8`)
- [Good] Discriminated union for WebSocket messages (`WSMessage` type at `editor.ts:218-223`)
- [Suggestion] `VIEWPORT_PRESETS` constant (line 48) is defined in the types file with emoji icons -- constants with runtime values belong in a separate config file

---

## 5. Potential Issues

### Critical

1. **Exposed API Keys in `.env` file committed to git** (`backend/.env:1-2`)
   - The `.env` file contains real OpenAI API key (`sk-proj-zJChBg...`) and Figma access token (`figd_N5_ai...`).
   - This file is tracked by git (shown in `git status` output).
   - **Impact**: Anyone with repository access can extract and misuse these credentials.
   - **Fix**: Add `backend/.env` to `.gitignore`, rotate the exposed keys immediately, use environment variables or a secrets manager in production.

2. **Wildcard CORS Configuration** (`backend/main.py:83-89`)
   ```python
   app.add_middleware(
       CORSMiddleware,
       allow_origins=["*"],
       allow_credentials=True,
       allow_methods=["*"],
       allow_headers=["*"],
   )
   ```
   - `allow_origins=["*"]` with `allow_credentials=True` is a security anti-pattern. While browsers ignore credentials with wildcard origins, this signals no access control consideration.
   - **Fix**: Restrict to known origins (plugin origin, localhost for dev, specific production domains).

3. **Path Traversal Risk in Asset Serving** (`backend/routers/jobs.py:276-306`)
   - The `filename` path parameter is used directly in file path construction: `asset_path = Path(settings.TEMP_DIR) / job_id / "assets" / filename`.
   - The `filename:path` type allows slashes, enabling traversal attempts like `../../etc/passwd`.
   - **Fix**: Validate that the resolved path is within the expected asset directory using `Path.resolve()` and checking `is_relative_to()`.

### Warning

4. **Hardcoded 1-second Sleep in Screenshot Rendering** (`backend/services/browser_service.py:145,214`)
   - `_time.sleep(1.0)` blocks the thread pool for every render. This adds up significantly during the fix loop (up to 10+ renders per job).
   - **Fix**: Replace with a font-ready event or make the delay configurable.

5. **Database Connection Churn** (`backend/db.py`)
   - Every database operation opens a new connection, executes, and closes it. Under load, this creates excessive connection overhead.
   - **Fix**: Use a connection pool or shared connection per request lifecycle.

6. **Global Mutable State for Browser** (`backend/services/browser_service.py:20-22`)
   ```python
   _browser: Optional[Browser] = None
   _pw_context = None
   _lock = threading.Lock()
   ```
   - Global mutable state with a threading lock. If the browser crashes mid-render, the lock state and reconnection logic could leave the system stuck.
   - The `_ensure_browser()` function checks `is_connected()` but doesn't handle partial failure states.

7. **Large orchestrator function** (`backend/pipeline/orchestrator.py:224-769`)
   - `run_pipeline()` is 545 lines long with deeply nested loops. The fix loop alone (lines 448-624) manages multiple state variables (`best_html`, `best_css`, `best_report`, `best_ssim`, `best_mismatch`, `best_typo_html`, `best_typo_css`, `best_typo_report`, `best_typo_score`, `best_typo_rendered`).
   - **Fix**: Extract fix loop into a separate function/class. Each phase could be its own method.

8. **Comment in orchestrator references stale line numbers** (`backend/tests/test_pipeline_integration.py:12-14`)
   - Comment says "mirrors the logic in routers/jobs.py lines 154-170" but line numbers will drift as code changes.
   - **Fix**: Reference function names instead of line numbers in comments.

### Suggestion

9. **No Rate Limiting on API Endpoints** (`backend/routers/jobs.py`)
   - The job creation endpoint (`POST /jobs`) and micro-fix endpoint (`POST /{job_id}/micro-fix`) trigger expensive GPT-4 API calls with no rate limiting.
   - **Fix**: Add rate limiting middleware (e.g., `slowapi`).

10. **No Input Size Validation** (`backend/routers/jobs.py:57-232`)
    - The `create_job` endpoint accepts arbitrary-size JSON bodies and base64-encoded screenshots with no size limits.
    - A malicious client could send extremely large design specs or screenshots to exhaust memory.
    - **Fix**: Add request body size limits and validate design spec node count.

11. **Regex-Based CSS Parsing** (`backend/agents/fixer.py:90-136`, `backend/services/diff_service.py:325-373`)
    - Multiple places parse CSS using custom regex-based parsers. These don't handle all CSS edge cases (media queries nested more than one level, CSS custom properties, `calc()` expressions with braces, etc.).
    - **Fix**: Consider using a proper CSS parser library like `cssutils` or `tinycss2` for production robustness.

12. **No Frontend Tests**
    - The web-app has no test files. The backend has tests but the frontend TypeScript code (components, store, lib) has zero test coverage.
    - **Fix**: Add tests for critical paths: `codeMutator.ts` functions, store actions, API error handling.

---

## 6. Test Coverage

### Backend Tests

The `backend/tests/` directory contains **7 test files**:

| File | Coverage Area | Test Count (approx) |
|------|---------------|---------------------|
| `test_parser.py` | Pydantic model parsing, design spec, job models, plugin field compatibility | ~30 tests |
| `test_verification.py` | Image comparison (SSIM, pixel diff, region analysis, heatmap, classification) | ~18 tests |
| `test_fixer.py` | CSS extraction, fixer agent with mocked GPT-4, fix history tracking | ~5 tests |
| `test_code_generator.py` | HTML/CSS extraction, post-processing, node summaries, font lists | ~10 tests |
| `test_pipeline_integration.py` | Asset saving, screenshot copying, fix loop state management | ~12 tests |
| `test_asset_filenames.py` | Asset filename uniqueness and edge cases | ~15 tests |
| `test_layout_strategy.py` | (exists but not read -- likely tests layout strategy agent) | Unknown |

**Strengths:**
- Good unit test coverage for data models and parsing logic
- Fixer and code generator agents are tested with mocked GPT-4 responses
- Image comparison service has comprehensive unit and integration tests
- Edge cases are tested (corrupt base64, empty inputs, unicode filenames)

**Gaps:**
- No tests for the `orchestrator.py` pipeline as a whole (only extracted logic is tested)
- No tests for `routers/jobs.py` HTTP endpoints (no FastAPI TestClient usage)
- No tests for `db.py` database operations
- No tests for `browser_service.py` rendering
- No tests for `ws.py` WebSocket endpoint
- **No frontend tests at all** (no `__tests__` or `*.test.ts` files in web-app)

---

## Summary

| Category | Rating | Key Finding |
|----------|--------|-------------|
| Code Organization | Good | Clean layered architecture on both backend and frontend |
| Design Patterns | Good | Appropriate use of agents, pipeline, observer, and store patterns |
| Error Handling | Moderate | Good at boundaries but some broad `except Exception`, silent `pass` blocks |
| Type Safety | Good | Pydantic models + TypeScript types provide strong compile/runtime checking |
| Security | **Critical** | Exposed API keys in `.env`, wildcard CORS, potential path traversal in asset serving |
| Test Coverage | Moderate | Solid backend unit tests but no endpoint/integration/frontend tests |
