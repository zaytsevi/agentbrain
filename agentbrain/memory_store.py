"""
AgentBrain MemoryStore: Dual-Layer Append-Only Event Log + SQLite FTS5 Index
=============================================================================
Zero external dependencies. Python Standard Library (sqlite3, json, re, pathlib).

Features:
- Immutable JSONL append-only audit trail (events.jsonl)
- Pre-write credential and secret scrubbing
- SQLite database (memory.db) with WAL mode & foreign keys
- FTS5 prefix indexing (2, 3, 4 char prefixes) for sub-millisecond keyword lookup
- Materialized supersession tracking (claims_current view): new decisions supersede old IDs
- Negative Knowledge Buffer (anti_patterns table): prevents repeating known failures
- Procedural Graph DAG (procedural_nodes, procedural_edges) for multi-step pipelines
"""

import os
import sys
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    from .scrub_secrets import scrub_text
except ImportError:
    try:
        from scrub_secrets import scrub_text
    except ImportError:
        def scrub_text(text: str):
            return text, 0

DEFAULT_DATA_DIR = Path.cwd() / ".agentbrain"
DB_PATH = DEFAULT_DATA_DIR / "memory.db"
EVENT_LOG_PATH = DEFAULT_DATA_DIR / "events.jsonl"

def get_db_connection(data_dir: Optional[Path] = None) -> sqlite3.Connection:
    target_dir = data_dir or DEFAULT_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_dir / "memory.db"))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db(data_dir: Optional[Path] = None):
    conn = get_db_connection(data_dir)
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            event_id         TEXT PRIMARY KEY NOT NULL,
            timestamp        TEXT NOT NULL,
            category         TEXT NOT NULL, -- 'preference', 'decision', 'gotcha', 'identity', 'project', 'note'
            domain           TEXT NOT NULL, -- e.g. 'architecture', 'infrastructure', 'auth', 'general'
            title            TEXT NOT NULL,
            body             TEXT NOT NULL,
            tags             TEXT NOT NULL, -- comma separated
            chain_id         TEXT,          -- thread or topic grouping ID
            parent_event_id  TEXT,          -- prior event ID superseded/refined
            verdict          TEXT NOT NULL DEFAULT 'active', -- 'active', 'superseded', 'refuted'
            source           TEXT NOT NULL DEFAULT 'agent'   -- 'agent', 'user', 'sync'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS events_fts USING fts5(
            title,
            body,
            tags,
            domain,
            category,
            content='events',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2',
            prefix='2 3 4'
        );

        CREATE TRIGGER IF NOT EXISTS events_ai AFTER INSERT ON events BEGIN
            INSERT INTO events_fts(rowid, title, body, tags, domain, category)
            VALUES (new.rowid, new.title, new.body, new.tags, new.domain, new.category);
        END;

        CREATE TRIGGER IF NOT EXISTS events_ad AFTER DELETE ON events BEGIN
            INSERT INTO events_fts(events_fts, rowid, title, body, tags, domain, category)
            VALUES('delete', old.rowid, old.title, old.body, old.tags, old.domain, old.category);
        END;

        CREATE TRIGGER IF NOT EXISTS events_au AFTER UPDATE ON events BEGIN
            INSERT INTO events_fts(events_fts, rowid, title, body, tags, domain, category)
            VALUES('delete', old.rowid, old.title, old.body, old.tags, old.domain, old.category);
            INSERT INTO events_fts(rowid, title, body, tags, domain, category)
            VALUES (new.rowid, new.title, new.body, new.tags, new.domain, new.category);
        END;

        CREATE VIEW IF NOT EXISTS claims_current AS
        SELECT * FROM events WHERE verdict = 'active' ORDER BY timestamp DESC;

        -- Negative Knowledge Buffer (Anti-Patterns)
        CREATE TABLE IF NOT EXISTS anti_patterns (
            anti_pattern_id TEXT PRIMARY KEY NOT NULL,
            domain          TEXT NOT NULL,
            context         TEXT NOT NULL, -- Preconditions / problem setting
            flawed_action   TEXT NOT NULL, -- What was attempted / rejected
            failure_mode    TEXT NOT NULL, -- Root-cause failure, API trap, physical limit
            alternative     TEXT NOT NULL, -- Verified correct method
            severity        TEXT NOT NULL DEFAULT 'high', -- 'critical', 'high', 'medium', 'low'
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            source          TEXT NOT NULL DEFAULT 'agent'
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS anti_patterns_fts USING fts5(
            domain,
            context,
            flawed_action,
            failure_mode,
            alternative,
            content='anti_patterns',
            content_rowid='rowid',
            tokenize='unicode61 remove_diacritics 2',
            prefix='2 3 4'
        );

        CREATE TRIGGER IF NOT EXISTS anti_patterns_ai AFTER INSERT ON anti_patterns BEGIN
            INSERT INTO anti_patterns_fts(rowid, domain, context, flawed_action, failure_mode, alternative)
            VALUES (new.rowid, new.domain, new.context, new.flawed_action, new.failure_mode, new.alternative);
        END;

        -- Procedural Execution DAG
        CREATE TABLE IF NOT EXISTS procedural_nodes (
            node_id          TEXT PRIMARY KEY NOT NULL,
            domain           TEXT NOT NULL,
            goal             TEXT NOT NULL,
            step_order       INTEGER NOT NULL DEFAULT 1,
            node_type        TEXT NOT NULL DEFAULT 'action', -- 'action', 'verification', 'decision', 'recovery'
            action_type      TEXT NOT NULL DEFAULT 'tool_call',
            description      TEXT NOT NULL,
            input_state      TEXT NOT NULL DEFAULT '',
            success_criteria TEXT NOT NULL DEFAULT '',
            failure_recovery TEXT NOT NULL DEFAULT '',
            code_ref         TEXT NOT NULL DEFAULT '',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS procedural_edges (
            edge_id        TEXT PRIMARY KEY NOT NULL,
            domain         TEXT NOT NULL,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            condition      TEXT NOT NULL DEFAULT 'on_success', -- 'on_success', 'on_failure', 'always'
            edge_type      TEXT NOT NULL DEFAULT 'sequential',
            created_at     TEXT NOT NULL,
            FOREIGN KEY(source_node_id) REFERENCES procedural_nodes(node_id) ON DELETE CASCADE,
            FOREIGN KEY(target_node_id) REFERENCES procedural_nodes(node_id) ON DELETE CASCADE
        );
        """)
    conn.close()

def record_event(
    title: str,
    body: str,
    category: str = "note",
    domain: str = "general",
    tags: str = "",
    chain_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    source: str = "agent",
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    target_dir = data_dir or DEFAULT_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    
    clean_title, _ = scrub_text(title)
    clean_body, _ = scrub_text(body)

    event_id = f"ev_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    event = {
        "event_id": event_id,
        "timestamp": now_iso,
        "category": category,
        "domain": domain,
        "title": clean_title,
        "body": clean_body,
        "tags": tags,
        "chain_id": chain_id,
        "parent_event_id": parent_event_id,
        "verdict": "active",
        "source": source,
    }

    # 1. Append to raw JSONL event log
    with open(target_dir / "events.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(event) + "\n")

    # 2. Insert into SQLite index
    conn = get_db_connection(target_dir)
    with conn:
        conn.execute("""
            INSERT INTO events (event_id, timestamp, category, domain, title, body, tags, chain_id, parent_event_id, verdict, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            event["event_id"], event["timestamp"], event["category"], event["domain"],
            event["title"], event["body"], event["tags"], event["chain_id"],
            event["parent_event_id"], event["verdict"], event["source"]
        ))
    conn.close()
    return event

def record_decision(
    domain: str,
    decision: str,
    rationale: str = "",
    supersedes_event_id: Optional[str] = None,
    tags: str = "",
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    target_dir = data_dir or DEFAULT_DATA_DIR
    body = decision
    if rationale:
        body += f"\nRationale: {rationale}"

    conn = get_db_connection(target_dir)
    with conn:
        if supersedes_event_id:
            conn.execute("""
                UPDATE events SET verdict = 'superseded' WHERE event_id = ?
            """, (supersedes_event_id,))
    conn.close()

    return record_event(
        title=f"Decision: {decision[:80]}",
        body=body,
        category="decision",
        domain=domain,
        tags=tags or f"decision,{domain}",
        parent_event_id=supersedes_event_id,
        data_dir=target_dir,
    )

def record_anti_pattern(
    domain: str,
    context: str,
    flawed_action: str,
    failure_mode: str,
    alternative: str,
    severity: str = "high",
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    target_dir = data_dir or DEFAULT_DATA_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    
    clean_context, _ = scrub_text(context)
    clean_flawed, _ = scrub_text(flawed_action)
    clean_failure, _ = scrub_text(failure_mode)
    clean_alt, _ = scrub_text(alternative)

    ap_id = f"ap_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    conn = get_db_connection(target_dir)
    with conn:
        conn.execute("""
            INSERT INTO anti_patterns (anti_pattern_id, domain, context, flawed_action, failure_mode, alternative, severity, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (ap_id, domain, clean_context, clean_flawed, clean_failure, clean_alt, severity, now_iso, now_iso))
    conn.close()

    return {
        "anti_pattern_id": ap_id,
        "domain": domain,
        "flawed_action": clean_flawed,
        "failure_mode": clean_failure,
        "alternative": clean_alt,
        "severity": severity,
    }

def check_anti_patterns(query: str, domain: Optional[str] = None, limit: int = 5, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    target_dir = data_dir or DEFAULT_DATA_DIR
    conn = get_db_connection(target_dir)
    
    # Clean query for FTS5
    safe_query = re.sub(r"[^\w\s]", " ", query).strip()
    if not safe_query:
        return []

    tokens = safe_query.split()
    fts_expr = " OR ".join(f'"{tok}"*' for tok in tokens)

    cursor = conn.cursor()
    try:
        if domain:
            cursor.execute("""
                SELECT ap.* FROM anti_patterns ap
                JOIN anti_patterns_fts fts ON ap.rowid = fts.rowid
                WHERE anti_patterns_fts MATCH ? AND ap.domain = ?
                ORDER BY rank LIMIT ?
            """, (fts_expr, domain, limit))
        else:
            cursor.execute("""
                SELECT ap.* FROM anti_patterns ap
                JOIN anti_patterns_fts fts ON ap.rowid = fts.rowid
                WHERE anti_patterns_fts MATCH ?
                ORDER BY rank LIMIT ?
            """, (fts_expr, limit))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Fallback to LIKE
        cursor.execute("""
            SELECT * FROM anti_patterns 
            WHERE (flawed_action LIKE ? OR failure_mode LIKE ? OR context LIKE ?)
            ORDER BY created_at DESC LIMIT ?
        """, (f"%{safe_query}%", f"%{safe_query}%", f"%{safe_query}%", limit))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

def query_memory(query: str, domain: Optional[str] = None, active_only: bool = True, limit: int = 10, data_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    target_dir = data_dir or DEFAULT_DATA_DIR
    conn = get_db_connection(target_dir)
    
    safe_query = re.sub(r"[^\w\s]", " ", query).strip()
    if not safe_query:
        return []

    tokens = safe_query.split()
    fts_expr = " OR ".join(f'"{tok}"*' for tok in tokens)

    cursor = conn.cursor()
    try:
        where_clause = "WHERE events_fts MATCH ?"
        params: List[Any] = [fts_expr]

        if active_only:
            where_clause += " AND e.verdict = 'active'"
        if domain:
            where_clause += " AND e.domain = ?"
            params.append(domain)

        params.append(limit)
        cursor.execute(f"""
            SELECT e.* FROM events e
            JOIN events_fts fts ON e.rowid = fts.rowid
            {where_clause}
            ORDER BY rank LIMIT ?
        """, params)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except sqlite3.OperationalError:
        # Fallback to LIKE query
        cursor.execute("""
            SELECT * FROM events 
            WHERE (title LIKE ? OR body LIKE ?) AND verdict = 'active'
            ORDER BY timestamp DESC LIMIT ?
        """, (f"%{safe_query}%", f"%{safe_query}%", limit))
        return [dict(r) for r in cursor.fetchall()]
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("AgentBrain MemoryStore initialized successfully!")
