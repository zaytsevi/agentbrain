# AgentBrain 1-Shot Bootstrap Prompt
> Copy and paste the entire block below into your AI coding assistant (Cursor, Claude Code, Windsurf, Antigravity, Cline, or ChatGPT).
> It will automatically inspect your workspace, generate your persistent memory substrate, and configure zero-drift cross-session context.

---

```markdown
You are now acting as the Systems Architect setting up the "AgentBrain" persistent state and memory architecture in this workspace.

Execute the following setup steps autonomously:

### Step 1: Workspace Analysis
Inspect the current repository and workspace:
- Identify the project name, primary programming languages, frameworks, and architecture.
- Identify active configuration files (package.json, pyproject.toml, docker-compose, etc.).
- Note any known credentials or environment patterns to protect.

### Step 2: Establish the Tier-0 Boot Manifest
Create `BOOT_MANIFEST.md` in the root of the workspace (keep it under 40 lines):
1. Executive Profile: Developer name, primary role, timezone, and strict execution rules (concise, verified results, zero emojis).
2. Locked Architecture & Decision Ground Truth: Key technical choices (framework, database, styling, deployment target).
3. Active Primary Projects: Top 1-3 active initiatives with current status and immediate next step.
4. Procedural & Memory Directives: Instructions to check anti-patterns and record decisions with supersession.

### Step 3: Create Supporting Ledgers
Create the following markdown files in the workspace root:
- `CORE_IDENTITY.md`: User preferences, coding guidelines, testing standards, and environment details.
- `ACTION_ITEMS.md`: Structured backlog organized by priority (P0, P1, P2, P3).
- `PROJECT_LEDGER.md`: Markdown table mapping projects to repositories, URLs, and specification documents.
- `ANTI_PATTERNS.md`: Documented failure modes, rejected architectures, and verified alternatives.

### Step 4: Install the Dual-Layer Memory Engine
Create a directory named `.agentbrain/` and install `memory_store.py` and `scrub_secrets.py`:
- Use standard Python `sqlite3` (zero third-party dependencies).
- Enable SQLite WAL mode (`PRAGMA journal_mode = WAL`) and foreign keys.
- Create tables: `events`, `events_fts` (FTS5 with prefixes 2,3,4), `anti_patterns`, `procedural_nodes`, and `procedural_edges`.
- Create the materialized view `claims_current` (filtering `WHERE verdict = 'active'`).
- Ensure all text written to `events.jsonl` and `memory.db` passes through regex credential scrubbing first.

### Step 5: Configure the Agent Boot Rule
Detect which AI agent harness is running:
- If Cursor: Append to `.cursorrules`
- If Claude Code: Append to `CLAUDE.md`
- If Antigravity / Gemini: Append to `GEMINI.md`
- If generic / Codex: Append to `AGENTS.md`

Add this directive to the rules file:
```
### AgentBrain Persistent Context Directive
1. At the start of every session or planning task, silently read `BOOT_MANIFEST.md` before taking action.
2. Before designing architecture or executing technical steps, check `ANTI_PATTERNS.md` or call `memory_check_anti_patterns` to avoid known traps.
3. Whenever an architectural choice is settled or changed, record it with explicit supersession of prior event IDs.
4. Never assume or hallucinate execution success without active tool verification (exit codes, test outputs, file contents read back).
```

### Step 6: Verify
Run a quick self-test using Python to verify that `.agentbrain/memory.db` initializes and `BOOT_MANIFEST.md` exists. Confirm when complete.
```
