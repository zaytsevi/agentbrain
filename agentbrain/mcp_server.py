"""
AgentBrain MCP Server: Exposes Persistent Memory Tools to Any AI Agent
======================================================================
Compatible with Antigravity, Claude Code, Cursor, Windsurf, Cline, and any MCP client.

Tools exposed:
- memory_ask: Instant full-text search across decisions, notes, and active claims.
- memory_note: Record an atomic fact, preference, or gotcha with automated secret scrubbing.
- memory_decision: Record an architectural decision with causal supersession tracking.
- memory_check_anti_patterns: Check negative knowledge before designing architectures.
- memory_anti_pattern: Record a rejected approach or known failure mode.
"""

import sys
from pathlib import Path
from typing import Optional

# Ensure local imports work
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

import memory_store

try:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("agentbrain-memory")

    @mcp.tool()
    def memory_ask(query: str, domain: Optional[str] = None, limit: int = 8) -> str:
        """Search persistent memory for verified decisions, user preferences, and facts."""
        results = memory_store.query_memory(query=query, domain=domain, limit=limit)
        if not results:
            return "No matching memory records found."
        out = []
        for r in results:
            out.append(f"[{r['event_id']}] ({r['timestamp'][:10]}) {r['title']}\n{r['body']}")
        return "\n\n---\n\n".join(out)

    @mcp.tool()
    def memory_note(title: str, text: str, category: str = "note", domain: str = "general", tags: str = "") -> str:
        """Store an atomic fact, gotcha, or user preference with automated credential scrubbing."""
        ev = memory_store.record_event(title=title, body=text, category=category, domain=domain, tags=tags)
        return f"Recorded event {ev['event_id']} under {domain}."

    @mcp.tool()
    def memory_decision(domain: str, decision: str, rationale: str = "", supersedes_event_id: Optional[str] = None) -> str:
        """Record an architectural decision. Supersedes prior decision event IDs to prevent stale recall."""
        ev = memory_store.record_decision(domain=domain, decision=decision, rationale=rationale, supersedes_event_id=supersedes_event_id)
        msg = f"Logged decision {ev['event_id']} in domain '{domain}'."
        if supersedes_event_id:
            msg += f" (Superseded {supersedes_event_id})"
        return msg

    @mcp.tool()
    def memory_check_anti_patterns(query: str, domain: Optional[str] = None) -> str:
        """Query negative knowledge buffer for past failures, physical traps, or deprecated patterns."""
        results = memory_store.check_anti_patterns(query=query, domain=domain)
        if not results:
            return "No anti-patterns found for query."
        out = []
        for ap in results:
            out.append(
                f"[ANTI-PATTERN {ap['anti_pattern_id']}] ({ap['domain']} - Severity: {ap['severity']})\n"
                f"Context: {ap['context']}\n"
                f"Flawed Action: {ap['flawed_action']}\n"
                f"Failure Mode: {ap['failure_mode']}\n"
                f"Verified Alternative: {ap['alternative']}"
            )
        return "\n\n---\n\n".join(out)

    @mcp.tool()
    def memory_anti_pattern(domain: str, context: str, flawed_action: str, failure_mode: str, alternative: str, severity: str = "high") -> str:
        """Record a newly discovered failure mode or rejected approach into the Negative Knowledge Buffer."""
        res = memory_store.record_anti_pattern(
            domain=domain, context=context, flawed_action=flawed_action,
            failure_mode=failure_mode, alternative=alternative, severity=severity
        )
        return f"Recorded anti-pattern {res['anti_pattern_id']} under domain '{domain}'."

    def main():
        memory_store.init_db()
        mcp.run()

except ImportError:
    def main():
        print("MCP SDK not installed. Run: pip install mcp")
        print("Or use memory_store.py directly in your scripts.")
        sys.exit(1)

if __name__ == "__main__":
    main()
