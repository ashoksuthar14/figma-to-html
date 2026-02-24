# Pixel-Perfect Figma to HTML/CSS Converter

## Project Overview

A multi-agent system that converts Figma designs to pixel-perfect HTML/CSS with automated verification and self-correction.

**Input:** Figma frame/design
**Output:** Pixel-perfect HTML + CSS

---

## Technology Stack

| Component | Technology |
|---|---|
| Figma Plugin | TypeScript + esbuild |
| Backend | Python 3.11+ / FastAPI |
| AI Provider | OpenAI GPT-4 |
| Communication | REST API + WebSocket |
| Verification | Playwright (headless Chrome) + pixelmatch + SSIM |
| Figma Screenshots | Figma REST API export |
| Output Format | HTML/CSS (React later) |
| Auto-fix Iterations | Max 3 |

---

## Installation & Setup

### Prerequisites

- **Node.js** >= 18.x (for Figma plugin)
- **Python** >= 3.11 (for backend)
- **Git** (for version control)
- **Figma Desktop App** (for loading the plugin)

### 1. Clone / Navigate to Project

```bash
cd C:\Users\ashok\OneDrive\Desktop\figma_project
```

### 2. Install & Build Figma Plugin

```bash
cd figma-plugin
npm install
npm run build
```

This produces:
- `dist/main.js` — Plugin sandbox bundle
- `dist/ui.html` — Plugin UI with inlined JavaScript

**To load in Figma:**
1. Open Figma Desktop App
2. Go to **Plugins → Development → Import plugin from manifest...**
3. Select `figma-plugin/manifest.json`
4. The plugin appears under **Plugins → Development → Figma to HTML/CSS**

### 3. Install Python Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 4. Install Playwright Browser (first time only)

```bash
playwright install chromium
```

### 5. Configure Environment Variables

Create a `.env` file in the `backend/` directory:

```env
OPENAI_API_KEY=sk-your-openai-api-key-here
FIGMA_ACCESS_TOKEN=figd_your-figma-personal-access-token-here
```

**How to get these keys:**
- **OpenAI API Key:** Go to https://platform.openai.com/api-keys → Create new secret key
- **Figma Access Token:** Go to Figma → Settings → Personal Access Tokens → Generate new token

### 6. Start the Backend Server

```bash
cd backend


```

The server runs at `http://localhost:8000`. Verify with:
```bash
curl http://localhost:8000/health
```

### 7. Run Backend Tests

```bash
cd backend
python -m pytest tests/ -v
```

Expected: **88 tests pass**.

---

## How to Use

1. Open any Figma file in the Figma Desktop App
2. Select a frame you want to convert
3. Run the plugin: **Plugins → Development → Figma to HTML/CSS**
4. Click **"Export to HTML/CSS"**
5. The plugin extracts the design, sends it to the backend, and shows real-time progress
6. Once complete, download the generated HTML/CSS files

---

## Project Structure

```
figma_project/
├── figma-plugin/                    # TypeScript Figma Plugin
│   ├── manifest.json                # Figma plugin manifest
│   ├── package.json                 # NPM dependencies & scripts
│   ├── tsconfig.json                # TypeScript configuration
│   ├── esbuild.config.js           # Build script (main + UI bundles)
│   ├── src/
│   │   ├── main.ts                  # Plugin sandbox entry (figma.* API access)
│   │   ├── ui.html                  # Plugin UI (iframe)
│   │   ├── ui.ts                    # UI logic + backend communication
│   │   ├── parser/
│   │   │   ├── index.ts             # Main parser orchestrator
│   │   │   ├── nodeExtractor.ts     # Recursive node tree walker
│   │   │   ├── layoutExtractor.ts   # Auto-layout / constraints extraction
│   │   │   ├── styleExtractor.ts    # Colors, fills, strokes, effects
│   │   │   ├── textExtractor.ts     # Typography: fonts, segments, styles
│   │   │   ├── assetExtractor.ts    # Images, vectors, export handling
│   │   │   └── componentExtractor.ts # Components, variants, instances
│   │   ├── types/
│   │   │   ├── designSpec.ts        # Design Spec JSON interfaces
│   │   │   ├── messages.ts          # Plugin <-> UI message types
│   │   │   └── api.ts               # Backend API request/response types
│   │   └── utils/
│   │       ├── colorUtils.ts        # Color conversion helpers
│   │       ├── unitUtils.ts         # px rounding, unit conversion
│   │       └── figmaHelpers.ts      # Common Figma API wrappers
│   └── dist/                        # Built output (main.js + ui.html)
│
├── backend/                         # Python FastAPI Backend
│   ├── pyproject.toml               # Project metadata & dependencies
│   ├── requirements.txt             # Pip-format dependencies
│   ├── main.py                      # FastAPI app entry point
│   ├── config.py                    # Settings, API keys, thresholds
│   ├── routers/
│   │   ├── jobs.py                  # POST /jobs, GET /jobs/{id}, GET /jobs/{id}/download
│   │   └── ws.py                    # WebSocket /ws/{job_id}
│   ├── agents/
│   │   ├── base.py                  # BaseAgent abstract class
│   │   ├── layout_strategy.py       # Agent 2: Layout Strategy (Rules + GPT-4)
│   │   ├── code_generator.py        # Agent 3: HTML/CSS Generator (GPT-4)
│   │   ├── verification.py          # Agent 4: Visual Verification
│   │   ├── fixer.py                 # Agent 5: Auto-Fixer (GPT-4)
│   │   └── componentizer.py         # Agent 6: Refactor & Cleanup
│   ├── pipeline/
│   │   ├── orchestrator.py          # Main pipeline: runs agents in sequence
│   │   └── job_manager.py           # Job state tracking + WebSocket updates
│   ├── services/
│   │   ├── openai_service.py        # OpenAI GPT-4 API wrapper
│   │   ├── figma_api.py             # Figma REST API (screenshot export)
│   │   ├── browser_service.py       # Playwright headless Chrome rendering
│   │   └── diff_service.py          # pixelmatch + SSIM comparison
│   ├── schemas/
│   │   ├── design_spec.py           # Pydantic models for Design Spec JSON
│   │   ├── layout_plan.py           # Pydantic models for Layout Plan
│   │   ├── diff_report.py           # Pydantic models for Diff Report
│   │   └── job.py                   # Job status models
│   ├── prompts/
│   │   ├── layout_strategy.txt      # GPT-4 prompt for layout decisions
│   │   ├── code_generation.txt      # GPT-4 prompt for HTML/CSS generation
│   │   └── fixer.txt                # GPT-4 prompt for CSS fix suggestions
│   ├── templates/
│   │   ├── base.html                # HTML template with CSS reset
│   │   └── css_reset.css            # Normalize/reset styles
│   └── tests/
│       ├── test_parser.py           # 20 tests - Pydantic model validation
│       ├── test_layout_strategy.py  # 16 tests - Rules engine
│       ├── test_code_generator.py   # 15 tests - HTML/CSS generation
│       ├── test_verification.py     # 18 tests - Image diff & SSIM
│       └── test_fixer.py            # 10 tests - CSS fix application (originally 19, some may overlap)
│
└── shared/                          # Shared schemas (reference)
    └── design-spec-schema.json      # JSON Schema for Design Spec
```

**Total: 60 files across 3 modules**

---

## Design Spec JSON Schema (Core Data Contract)

The Design Spec JSON is the **source of truth** passed from the Figma plugin to the backend.

```typescript
interface DesignSpec {
  frameId: string;
  frameName: string;
  width: number;
  height: number;
  backgroundColor: Color;
  nodes: DesignNode[];
  assets: AssetReference[];
  metadata: {
    figmaFileKey: string;
    exportedAt: string;
    pluginVersion: string;
  };
}

interface DesignNode {
  id: string;
  name: string;
  type: "FRAME" | "TEXT" | "RECTANGLE" | "ELLIPSE" | "VECTOR" | "GROUP" | "INSTANCE" | "COMPONENT";
  visible: boolean;
  opacity: number;

  // Bounding box (absolute within frame)
  bounds: { x: number; y: number; width: number; height: number };

  // Layout
  layout: {
    type: "NONE" | "AUTO_LAYOUT" | "ABSOLUTE";
    direction?: "HORIZONTAL" | "VERTICAL";
    gap?: number;
    padding?: { top: number; right: number; bottom: number; left: number };
    primaryAxisAlign?: "MIN" | "CENTER" | "MAX" | "SPACE_BETWEEN";
    counterAxisAlign?: "MIN" | "CENTER" | "MAX";
    wrap?: boolean;
    constraints?: { horizontal: string; vertical: string };
  };

  // Styling
  style: {
    fills: Fill[];
    strokes: Stroke[];
    borderRadius: { tl: number; tr: number; br: number; bl: number };
    effects: Effect[];       // shadows, blurs
    blendMode: string;
    overflow: "VISIBLE" | "HIDDEN" | "SCROLL";
  };

  // Text-specific
  text?: {
    content: string;
    segments: TextSegment[];   // Mixed styling spans
    textAlign: "LEFT" | "CENTER" | "RIGHT" | "JUSTIFIED";
    verticalAlign: "TOP" | "CENTER" | "BOTTOM";
  };

  // Component-specific
  component?: {
    componentId: string;
    variantProperties?: Record<string, string>;
    isInstance: boolean;
  };

  // Children (recursive)
  children: DesignNode[];
}

interface TextSegment {
  start: number;
  end: number;
  fontFamily: string;
  fontSize: number;
  fontWeight: number;
  fontStyle: "normal" | "italic";
  lineHeight: number | "AUTO";
  letterSpacing: number;
  color: Color;
  textDecoration: "NONE" | "UNDERLINE" | "STRIKETHROUGH";
}

interface Color {
  r: number; // 0-1
  g: number; // 0-1
  b: number; // 0-1
  a: number; // 0-1
}
```

---

## Pipeline Flow (End-to-End)

```
[Figma Plugin]
     │
     │ 1. User selects frame, clicks "Export"
     │ 2. Plugin parses node tree → Design Spec JSON
     │ 3. Plugin exports assets (images/vectors as PNG/SVG)
     │
     ▼
[REST POST /jobs]  ──── sends Design Spec JSON + assets + Figma file key
     │
     ▼
[Backend Pipeline Orchestrator]
     │
     ├─► Agent 1 (Parser validation) ─── Validate + enrich Design Spec
     │
     ├─► Agent 2 (Layout Strategy) ──── Rules + GPT-4 → Layout Plan
     │         Input: Design Spec
     │         Output: Layout Plan (flex vs absolute decisions per node)
     │
     ├─► Agent 3 (Code Generator) ──── GPT-4 → HTML + CSS
     │         Input: Design Spec + Layout Plan
     │         Output: index.html + styles.css
     │
     ├─► [Figma REST API] ──── Export frame as PNG (ground truth)
     │
     ├─► Agent 4 (Verification) ──── Render HTML → Screenshot → Compare
     │         Input: generated HTML/CSS + figma screenshot
     │         Output: Diff Report (mismatch %, heatmap, issue list)
     │
     │   ┌─── IF mismatch > 0.5% AND iteration < 3 ───┐
     │   │                                              │
     │   ▼                                              │
     ├─► Agent 5 (Fixer) ──── GPT-4 → Targeted CSS fixes
     │         Input: HTML/CSS + Diff Report             │
     │         Output: Fixed HTML/CSS                    │
     │         └──────── Loop back to Agent 4 ──────────┘
     │
     │   (After pass OR 3 iterations)
     │
     ├─► Agent 6 (Componentizer) ──── Optional cleanup
     │
     ▼
[WebSocket] ──── Real-time progress updates to plugin UI
     │
     ▼
[REST GET /jobs/{id}] ──── Final HTML/CSS + verification report
     │
     ▼
[Plugin downloads files to user]
```

---

## Agent Details

### Agent 1: Figma Parser (TypeScript — runs in plugin)

- Recursively walks the Figma node tree via `figma.currentPage.selection`
- Extracts all visual properties into Design Spec JSON
- Exports images/vectors via `node.exportAsync()` as PNG/SVG
- Handles: auto-layout, constraints, component instances, variants, mixed text styles
- **Key challenge:** Accurate extraction of auto-layout gap, padding, and constraint logic

### Agent 2: Layout Strategy (Python — Rules + GPT-4)

- **Rules engine first** — Applies deterministic rules:
  - Auto-layout nodes → CSS flexbox
  - Non-auto-layout with overlapping children → absolute positioning
  - Single child in container → simple block/flex
  - Grid-like patterns → CSS Grid
- **GPT-4 fallback** — For ambiguous cases, sends node context to GPT-4
- **Output:** Layout Plan JSON mapping each node ID to a layout decision

### Agent 3: HTML/CSS Generator (Python — GPT-4 Assisted)

- Constructs a structured prompt with Design Spec + Layout Plan + CSS reset template
- GPT-4 generates HTML + CSS
- **Post-processing:** Validate HTML, inject CSS reset, enforce `box-sizing: border-box`

### Agent 4: Visual Verification (Python)

- **Step 1:** Fetch Figma screenshot via REST API at 2x scale
- **Step 2:** Render generated HTML in Playwright headless Chrome at exact frame dimensions
- **Step 3:** Compare using dual metrics:
  - **pixelmatch** — Fast pixel-by-pixel diff → mismatch percentage + diff image
  - **SSIM (scikit-image)** — Structural similarity → quality score (0-1)
- **Thresholds:**
  - **PASS:** pixelmatch < 0.5% AND SSIM > 0.98
  - **FAIL:** Otherwise → generate diff report for Fixer agent

### Agent 5: Fixer (Python — GPT-4)

- Receives current HTML/CSS + Diff Report + diff image
- GPT-4 generates targeted CSS-only fixes
- Sends back to Agent 4 for re-verification
- **Max 3 iterations**, then returns best result

### Agent 6: Componentizer (Optional)

- Detects repeated DOM structures
- Extracts common CSS into reusable classes
- Groups related elements into logical components

---

## API Endpoints

### REST API

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check |
| `POST` | `/jobs` | Create a new conversion job (accepts Design Spec JSON) |
| `GET` | `/jobs` | List all jobs |
| `GET` | `/jobs/{job_id}` | Get job status and results |
| `GET` | `/jobs/{job_id}/download` | Download HTML/CSS as ZIP |

### WebSocket

| Endpoint | Description |
|---|---|
| `ws://localhost:8000/ws/{job_id}` | Real-time progress updates |

### WebSocket Message Format

```json
{"step": "parsing", "status": "running", "message": "Validating Design Spec..."}
{"step": "layout", "status": "running", "message": "Analyzing layout strategy..."}
{"step": "generation", "status": "running", "message": "Generating HTML/CSS with AI..."}
{"step": "verification", "status": "running", "message": "Rendering and comparing (attempt 1/3)..."}
{"step": "verification", "status": "running", "data": {"mismatch": 3.2, "ssim": 0.94}}
{"step": "fixing", "status": "running", "message": "Applying corrections (attempt 1/3)..."}
{"step": "verification", "status": "running", "message": "Re-verifying (attempt 2/3)..."}
{"step": "complete", "status": "done", "data": {"finalMismatch": 0.3, "ssim": 0.99}}
```

---

## Dependencies

### Figma Plugin (package.json)

```json
{
  "devDependencies": {
    "@figma/plugin-typings": "^1.98.0",
    "typescript": "^5.4.0",
    "esbuild": "^0.21.0"
  }
}
```

### Python Backend (requirements.txt)

```
fastapi>=0.111.0
uvicorn>=0.30.0
websockets>=12.0
pydantic>=2.7.0
pydantic-settings>=2.3.0
openai>=1.30.0
playwright>=1.44.0
Pillow>=10.3.0
scikit-image>=0.23.0
numpy>=1.26.0
httpx>=0.27.0
python-multipart>=0.0.9
pytest>=8.2.0
pytest-asyncio>=0.24.0
```

---

## Quick Reference Commands

```bash
# ──────────────────────────────────────
# FIGMA PLUGIN
# ──────────────────────────────────────

# Install dependencies
cd figma-plugin && npm install

# Build plugin (produces dist/main.js + dist/ui.html)
npm run build

# Build in watch mode (auto-rebuild on changes)
npm run watch

# Type-check without building
npm run typecheck

# ──────────────────────────────────────
# PYTHON BACKEND
# ──────────────────────────────────────

# Install dependencies
cd backend && pip install -r requirements.txt

# Install Playwright browser (first time)
playwright install chromium

# Start dev server (auto-reload on changes)
uvicorn main:app --reload --port 8000

# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_verification.py -v

# Run with coverage
python -m pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Verification & Testing Plan

### Automated Tests (88 total)

| Test File | Count | What It Tests |
|---|---|---|
| `test_parser.py` | 20 | Pydantic model validation, serialization, helper methods |
| `test_layout_strategy.py` | 16 | Rules engine: overlap detection, grid detection, auto-layout mapping |
| `test_code_generator.py` | 15 | HTML/CSS extraction, post-processing, prompt building |
| `test_verification.py` | 18 | Pixel diff, SSIM, region analysis, heatmap generation |
| `test_fixer.py` | 10 | CSS extraction, fix application, history tracking |

### How to Test End-to-End

1. **Create a test Figma file** with known simple layouts (a button, a card, a header)
2. **Run the plugin** on each test frame → verify Design Spec JSON contains all properties
3. **Run the backend pipeline** → verify HTML/CSS generates correctly
4. **Check verification scores** → should achieve < 0.5% mismatch on simple layouts
5. **Manually compare** rendered output vs Figma for visual sanity check

---

## Development Phases

### Phase 1: Foundation & Skeleton ✅
- Figma plugin project initialized with TypeScript + esbuild
- Backend FastAPI project with all endpoints
- Plugin ↔ Backend communication (REST + WebSocket)
- Pydantic schemas for Design Spec
- BaseAgent class

### Phase 2: Full Design Extraction ✅
- All 7 parser/extractor modules in the Figma plugin
- Complete Design Spec JSON generation
- Asset export (PNG/SVG) with base64 encoding
- Backend Design Spec validation

### Phase 3: Layout Strategy + Code Generation ✅
- Rules engine (auto-layout → flex, overlapping → absolute, grid detection)
- GPT-4 integration for ambiguous cases
- Code generator with structured prompts
- Post-processing (HTML validation, CSS reset injection)

### Phase 4: Verification Engine ✅
- Playwright headless Chrome rendering
- Pixel diff comparison with Pillow + numpy
- SSIM comparison with scikit-image
- Diff heatmap generation
- Structured Diff Report

### Phase 5: Auto-Fix Loop ✅
- Fixer agent with GPT-4 targeted CSS fixes
- Verify → Fix → Re-verify loop (max 3 iterations)
- Rollback if mismatch increases
- Best result tracking

### Phase 6: Polish & Edge Cases (Future)
- [ ] Handle large frames (chunking strategy)
- [ ] Handle missing fonts (substitution + warning)
- [ ] Handle complex gradients and blur effects
- [ ] Plugin UI: show verification results with before/after images
- [ ] Plugin UI: settings panel (Figma API token, threshold, max iterations)
- [ ] Error handling improvements (graceful failures, retries)
- [ ] Performance optimization (parallel asset export, caching)
- [ ] React component output support

---

## Architecture Decisions

| Decision | Rationale |
|---|---|
| **esbuild** over webpack | 10-100x faster builds, simpler config for Figma plugins |
| **FastAPI** over Flask/Django | Async-native, WebSocket support, Pydantic integration |
| **Rules + GPT-4 hybrid** for layout | Deterministic rules handle 80% of cases cheaply; GPT-4 handles ambiguity |
| **Dual verification** (pixelmatch + SSIM) | pixelmatch catches exact pixel errors; SSIM catches structural/perceptual issues |
| **Max 3 fix iterations** | Diminishing returns after 3; prevents infinite loops and cost overruns |
| **In-memory job store** | Sufficient for single-user plugin; can upgrade to Redis/DB later |
| **Base64 asset encoding** | Simpler than multipart uploads for plugin-to-backend transfer |

---

## Troubleshooting

### Plugin doesn't appear in Figma
- Make sure you're using **Figma Desktop App** (not browser version)
- Import via **Plugins → Development → Import plugin from manifest...**
- Select the `figma-plugin/manifest.json` file

### Backend won't start
```bash
# Check Python version (needs 3.11+)
python --version

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Playwright fails
```bash
# Install/reinstall browser
playwright install chromium

# On some systems you may need system dependencies
playwright install-deps chromium
```

### OpenAI API errors
- Verify your API key in `.env` is correct and has credits
- Check rate limits at https://platform.openai.com/usage

### WebSocket connection fails
- Ensure backend is running on port 8000
- Check that the plugin's backend URL setting matches (default: `http://localhost:8000`)
- Browser/Figma may block `ws://` — try `wss://` with HTTPS

---

## License

This project is for personal/educational use.
