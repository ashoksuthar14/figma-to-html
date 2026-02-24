# Figma to HTML/CSS — Multi-Agent Conversion System

A full-stack system that converts Figma designs into pixel-perfect, production-ready HTML/CSS using a multi-agent AI pipeline with visual verification.

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  Figma Plugin    │────>│  FastAPI Backend  │<───>│  Next.js Web App │
│  (Design Parser) │     │  (AI Pipeline)    │     │  (Preview Editor)│
└─────────────────┘     └──────────────────┘     └──────────────────┘
                              │
                    ┌─────────┼─────────┐
                    │         │         │
               GPT-5.2   Playwright  SQLite
              (Code Gen) (Verify)   (Persist)
```

**Three main components:**

| Component | Tech | Purpose |
|-----------|------|---------|
| `figma-plugin/` | TypeScript, Figma Plugin API | Extracts design specs (nodes, styles, assets, layout) from Figma |
| `backend/` | Python, FastAPI, OpenAI, Playwright | Multi-agent pipeline: parses design → generates HTML/CSS → verifies visually → fixes iteratively |
| `web-app/` | Next.js 14, React, Zustand, Tailwind | Live preview editor with text editing, drag positioning, spacing controls, AI micro-fixer |

---

## Prerequisites

Before starting, make sure you have these installed:

| Tool | Version | Check with |
|------|---------|------------|
| **Python** | 3.11+ | `python --version` |
| **Node.js** | 18+ | `node --version` |
| **npm** | 9+ | `npm --version` |
| **Git** | any | `git --version` |

You also need:
- An **OpenAI API key** — [Get one here](https://platform.openai.com/api-keys)
- A **Figma Personal Access Token** — [Generate here](https://www.figma.com/developers/api#access-tokens)

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/ashoksuthar14/figma-to-html.git
cd figma-to-html
```

### 2. Set up the Backend

```bash
cd backend
```

**Create the environment file:**

```bash
# Linux / macOS
cp .env.example .env

# Windows (PowerShell)
Copy-Item .env.example .env

# Windows (CMD)
copy .env.example .env
```

**Edit `.env` and add your API keys:**

```env
OPENAI_API_KEY=sk-your-actual-openai-api-key
FIGMA_ACCESS_TOKEN=figd_your-actual-figma-token
```

**Install Python dependencies:**

```bash
# (Recommended) Create a virtual environment first
python -m venv venv

# Activate it
# Linux/macOS:
source venv/bin/activate
# Windows PowerShell:
.\venv\Scripts\Activate
# Windows CMD:
venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt
```

**Install Playwright browsers** (needed for visual verification):

```bash
playwright install chromium
```

**Start the backend server:**

```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Application startup complete.
```

> The backend runs on **http://localhost:8000** by default.

### 3. Set up the Web App

Open a **new terminal** and run:

```bash
cd web-app
```

**Create the environment file:**

```bash
# Linux / macOS
cp .env.example .env.local

# Windows (PowerShell)
Copy-Item .env.example .env.local

# Windows (CMD)
copy .env.example .env.local
```

The default value (`http://localhost:8000`) works for local development. Only change it if your backend runs on a different host/port.

**Install dependencies:**

```bash
npm install
```

**Start the dev server:**

```bash
npm run dev
```

You should see:
```
▲ Next.js 14.x
- Local: http://localhost:3000
✓ Ready
```

> The web app runs on **http://localhost:3000**. Open this URL in your browser.

### 4. Set up the Figma Plugin (for design extraction)

Open a **new terminal** and run:

```bash
cd figma-plugin
npm install
npm run build
```

**Load the plugin in Figma:**

1. Open **Figma Desktop** (the plugin requires the desktop app)
2. Go to **Plugins** → **Development** → **Import plugin from manifest...**
3. Select the file: `figma-plugin/manifest.json`
4. The plugin "Figma to HTML/CSS" will appear in your plugins menu

---

## Usage

### Converting a Figma design

1. **Start the backend** (`uvicorn main:app --reload --port 8000`)
2. **Start the web app** (`npm run dev` in `web-app/`)
3. **Open Figma** and select a frame you want to convert
4. **Run the plugin**: Right-click → Plugins → Development → Figma to HTML/CSS
5. The plugin sends the design to the backend, which processes it through the AI pipeline
6. **Open the web app** at `http://localhost:3000` — your job will appear in the list
7. Click on the job to see the live preview with the code editor

### Editing in the Web App

Once a design is converted, you can:

- **Select any element** by clicking on it in the preview
- **Edit text** — Change text content in the Text tab and click Apply
- **Adjust spacing** — Modify margin/padding via the Spacing tab
- **Drag to reposition** — Enable drag mode in the Spacing tab to visually move elements
- **Add hyperlinks** — Select text and add/edit links in the Link tab
- **AI Fix** — Select a problematic area, describe the issue, and let GPT fix just that section
- **Undo** — Use the undo button in the toolbar to revert changes
- **Save** — Click Save to persist changes to the backend
- **Download** — Export the final HTML/CSS as a ZIP file

---

## Project Structure

```
figma-to-html/
├── backend/                    # FastAPI backend
│   ├── agents/                 # AI agent modules
│   │   ├── position_generator.py  # Deterministic HTML/CSS generator
│   │   ├── fixer.py            # Iterative visual fixer agent
│   │   ├── micro_fixer.py      # Targeted AI fixer for specific areas
│   │   ├── verification.py     # Visual comparison (SSIM, pixel diff)
│   │   └── ...
│   ├── pipeline/               # Job orchestration
│   │   ├── job_manager.py      # Job lifecycle + SQLite persistence
│   │   └── orchestrator.py     # Multi-agent pipeline runner
│   ├── routers/                # API endpoints
│   │   ├── jobs.py             # REST API for jobs (CRUD, download, micro-fix)
│   │   └── ws.py               # WebSocket for real-time progress
│   ├── schemas/                # Pydantic models
│   ├── services/               # External service wrappers (OpenAI, Playwright, Figma)
│   ├── prompts/                # GPT prompt templates
│   ├── templates/              # HTML/CSS base templates
│   ├── config.py               # App configuration (env vars)
│   ├── db.py                   # SQLite async database layer
│   ├── main.py                 # FastAPI app entry point
│   ├── requirements.txt        # Python dependencies
│   └── .env.example            # Environment template
│
├── web-app/                    # Next.js 14 frontend
│   ├── app/                    # App Router pages
│   │   ├── page.tsx            # Home page (job list)
│   │   └── job/[jobId]/page.tsx # Job detail page (editor)
│   ├── components/             # React components
│   │   ├── PreviewFrame.tsx    # Iframe preview with element selection
│   │   ├── CodePanel.tsx       # HTML/CSS code viewer
│   │   ├── ElementEditor.tsx   # Floating editor panel (text/spacing/link)
│   │   ├── SpacingPanel.tsx    # Margin/padding controls + drag mode
│   │   ├── DragOverlay.tsx     # Visual drag overlay for positioning
│   │   ├── AIFixModal.tsx      # AI micro-fixer modal
│   │   ├── LinkEditor.tsx      # Hyperlink editor
│   │   └── Toolbar.tsx         # Top toolbar (viewport, save, undo)
│   ├── store/                  # Zustand state management
│   ├── lib/                    # Utilities (API, code mutation, DOM mapping)
│   ├── hooks/                  # Custom React hooks
│   ├── types/                  # TypeScript type definitions
│   └── .env.example            # Environment template
│
├── figma-plugin/               # Figma plugin
│   ├── src/
│   │   ├── main.ts             # Plugin entry point
│   │   ├── ui.ts               # Plugin UI logic
│   │   ├── parser/             # Design extraction modules
│   │   └── types/              # TypeScript types
│   ├── manifest.json           # Figma plugin manifest
│   └── package.json
│
├── shared/                     # Shared schemas
│   └── design-spec-schema.json # Design spec JSON schema
│
├── .gitignore
└── README.md
```

---

## Configuration Reference

### Backend (`backend/.env`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key for GPT calls |
| `FIGMA_ACCESS_TOKEN` | Yes | — | Figma personal access token for asset downloads |
| `OPENAI_MODEL` | No | `gpt-5.2` | Model to use (`gpt-4o`, `gpt-5.2`, etc.) |
| `OPENAI_MAX_TOKENS` | No | `16384` | Max response tokens |
| `OPENAI_TEMPERATURE` | No | `0.1` | Sampling temperature |
| `MAX_FIX_ITERATIONS` | No | `5` | Max visual fix iterations |
| `SSIM_THRESHOLD` | No | `0.70` | SSIM score to accept as "good enough" |
| `PIXEL_MISMATCH_THRESHOLD` | No | `15.0` | Pixel mismatch % threshold |
| `USE_DETERMINISTIC_GENERATION` | No | `True` | Use deterministic generator (faster, no GPT for layout) |
| `BACKEND_PORT` | No | `8000` | Server port |
| `LOG_LEVEL` | No | `INFO` | Logging level |

### Web App (`web-app/.env.local`)

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `NEXT_PUBLIC_API_URL` | No | `http://localhost:8000` | Backend API URL |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/jobs` | Create a new conversion job |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/jobs/{id}` | Get job status |
| `DELETE` | `/jobs/{id}` | Delete a job |
| `GET` | `/jobs/{id}/html` | Get generated HTML |
| `GET` | `/jobs/{id}/css` | Get generated CSS |
| `GET` | `/jobs/{id}/preview` | Get rendered preview image |
| `GET` | `/jobs/{id}/download` | Download HTML/CSS as ZIP |
| `POST` | `/jobs/{id}/update` | Save edited HTML/CSS |
| `POST` | `/jobs/{id}/micro-fix` | AI micro-fix a specific area |
| `WS` | `/ws/{id}` | WebSocket for real-time progress |

---

## Troubleshooting

**Backend won't start:**
- Make sure Python 3.11+ is installed: `python --version`
- Check that `.env` file exists in `backend/` with valid API keys
- Install dependencies: `pip install -r requirements.txt`

**Playwright errors:**
- Run `playwright install chromium` to install browser binaries
- On Linux, you may also need: `playwright install-deps`

**Web app build errors:**
- Make sure Node.js 18+ is installed: `node --version`
- Delete `node_modules` and reinstall: `rm -rf node_modules && npm install`

**Figma plugin not showing:**
- You must use **Figma Desktop** (not the web version)
- Make sure you built the plugin: `cd figma-plugin && npm run build`
- Re-import the manifest if you rebuilt

**AI fix returns 400 error:**
- If using `gpt-5.2` or newer, the backend automatically uses `max_completion_tokens` instead of `max_tokens`
- Make sure your OpenAI API key has access to the model you configured

---

## Tech Stack

- **Backend:** Python 3.11, FastAPI, OpenAI SDK, Playwright, aiosqlite, Pydantic
- **Frontend:** Next.js 14, React 18, Zustand, Tailwind CSS, Cheerio
- **Plugin:** TypeScript, Figma Plugin API, esbuild
- **Database:** SQLite (async via aiosqlite)
- **AI Models:** GPT-5.2 (configurable — also supports GPT-4o)

## License

MIT
