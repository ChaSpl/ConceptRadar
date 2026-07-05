import sqlite3
import json
import os
from datetime import datetime

DB_PATH = "concept_radar.db"

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn

from contextlib import contextmanager

@contextmanager
def batch_transaction():
    """Context manager for batching multiple writes in a single transaction.
    All writes succeed together or roll back together on error.
    
    Usage:
        with batch_transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
            cursor.execute(...)
        # auto-committed on exit, rolled back on exception
    """
    conn = get_db_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create Nodes Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT,
        url TEXT,
        source_type TEXT NOT NULL,
        created_at TIMESTAMP NOT NULL,
        embedding TEXT, -- JSON-serialized float list
        novelty_score REAL DEFAULT 0.0,
        validation_score REAL DEFAULT 0.0,
        momentum_score REAL DEFAULT 0.0,
        cluster_id TEXT,
        contact_name TEXT,
        contact_linkedin TEXT,
        contact_email TEXT,
        is_manual_or_scouted INTEGER DEFAULT 0
    )
    """)
    
    # Create Clusters Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS clusters (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        description TEXT,
        centroid_embedding TEXT, -- JSON-serialized float list
        is_active INTEGER DEFAULT 1,
        parent_cluster_id TEXT DEFAULT NULL,
        level INTEGER DEFAULT 3
    )
    """)
    
    # Create Edges Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS edges (
        source_id TEXT,
        target_id TEXT,
        relationship_type TEXT NOT NULL,
        similarity REAL DEFAULT 0.0,
        PRIMARY KEY (source_id, target_id, relationship_type),
        FOREIGN KEY (source_id) REFERENCES nodes (id) ON DELETE CASCADE,
        FOREIGN KEY (target_id) REFERENCES nodes (id) ON DELETE CASCADE
    )
    """)

    # Create Sandbox Logs Table (for private, internal metadata analysis)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sandbox_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        summary TEXT NOT NULL,
        novelty REAL,
        validation REAL,
        momentum REAL,
        created_at TIMESTAMP NOT NULL
    )
    """)
    
    # Run schema migrations for existing databases
    try:
        cursor.execute("ALTER TABLE clusters ADD COLUMN is_active INTEGER DEFAULT 1;")
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        cursor.execute("ALTER TABLE clusters ADD COLUMN parent_cluster_id TEXT DEFAULT NULL;")
    except sqlite3.OperationalError:
        pass # Column already exists
        
    try:
        cursor.execute("ALTER TABLE clusters ADD COLUMN level INTEGER DEFAULT 3;")
    except sqlite3.OperationalError:
        pass # Column already exists
    
    # Create Reputable Domains Table (for dynamic LLM publisher caching)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reputable_domains (
        domain TEXT PRIMARY KEY,
        score REAL NOT NULL,
        added_at TIMESTAMP NOT NULL
    )
    """)

    # Create Scouting History Table (for semantic query caching)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS scouting_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        query TEXT NOT NULL,
        query_embedding TEXT NOT NULL, -- JSON float list
        executed_at TIMESTAMP NOT NULL
    )
    """)

    # Run schema migrations for nodes attribution columns
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN contact_name TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN contact_linkedin TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN contact_email TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN contradiction_analysis TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN is_manual_or_scouted INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN document_type TEXT DEFAULT 'research_paper';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN scores_updated_at TEXT;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN status TEXT DEFAULT 'active';")
    except sqlite3.OperationalError:
        pass

    # T1: Taxonomy overhaul columns
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN tags TEXT DEFAULT '[]';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN classification_method TEXT DEFAULT 'llm';")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN is_cross_disciplinary INTEGER DEFAULT 0;")
    except sqlite3.OperationalError:
        pass
    # Novelty transparency: store raw component scores
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN llm_novelty_raw REAL DEFAULT 0.0;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN entropy_score REAL DEFAULT 0.0;")
    except sqlite3.OperationalError:
        pass
    try:
        cursor.execute("ALTER TABLE nodes ADD COLUMN structural_surprise REAL DEFAULT 0.0;")
    except sqlite3.OperationalError:
        pass
        
    # Create Node Refreshes Table (for tracking and rate-limiting refreshes)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS node_refreshes (
        node_id TEXT NOT NULL,
        refreshed_at TIMESTAMP NOT NULL
    )
    """)
    
    # Create indexes for high-scale O(1) lookups
    cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_nodes_url 
    ON nodes(url) 
    WHERE url IS NOT NULL AND url != '';
    """)
    cursor.execute("""
    CREATE INDEX IF NOT EXISTS idx_nodes_cluster 
    ON nodes(cluster_id);
    """)
    
    # Create URL Blacklist Table (for URLs that fail scraping to save tokens)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS url_blacklist (
        url TEXT PRIMARY KEY,
        reason TEXT,
        failed_at TIMESTAMP NOT NULL
    )
    """)

    conn.commit()
    conn.close()
    print("Database initialized successfully at:", DB_PATH)

def normalize_url(url: str) -> str:
    """Normalizes URLs for robust matching (strips trailing slashes, http/https schemes, query params)."""
    if not url:
        return ""
    u = url.strip()
    import re
    # Strip protocol scheme (http/https)
    u_noscheme = re.sub(r'^https?://', '', u, flags=re.IGNORECASE)
    # Strip www.
    u_noscheme = re.sub(r'^www\.', '', u_noscheme, flags=re.IGNORECASE)
    # Strip query string and fragments
    u_clean = u_noscheme.split('?')[0].split('#')[0]
    # Strip trailing slash & lowercase
    return u_clean.rstrip('/').lower()

def is_url_blacklisted(url: str) -> dict | None:
    """Check if a URL is in the blacklist. Returns {url, reason, failed_at} or None."""
    norm = normalize_url(url)
    if not norm:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT url, reason, failed_at FROM url_blacklist WHERE url = ?", (norm,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"url": row["url"], "reason": row["reason"], "failed_at": row["failed_at"]}
    return None

def insert_blacklisted_url(url: str, reason: str = "Scraping failed"):
    """Add a URL to the blacklist."""
    norm = normalize_url(url)
    if not norm:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO url_blacklist (url, reason, failed_at) VALUES (?, ?, ?)",
        (norm, reason, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    print(f"[Blacklist] Added URL to blacklist: {norm} (reason: {reason})")

def get_node_by_id_or_url(node_id=None, url=None):
    if not node_id and not url:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    row = None
    
    clean_u = url.strip() if url else None
    norm_u = normalize_url(clean_u) if clean_u else None

    # 1. Fast exact DB index match first
    if node_id and clean_u:
        cursor.execute("SELECT * FROM nodes WHERE id = ? OR (url = ? AND url != '') LIMIT 1", (node_id, clean_u))
        row = cursor.fetchone()
    elif node_id:
        cursor.execute("SELECT * FROM nodes WHERE id = ? LIMIT 1", (node_id,))
        row = cursor.fetchone()
    elif clean_u:
        cursor.execute("SELECT * FROM nodes WHERE url = ? AND url != '' LIMIT 1", (clean_u,))
        row = cursor.fetchone()
        
    # 2. Normalized URL fallback check if exact match missed
    if not row and norm_u:
        cursor.execute("SELECT * FROM nodes WHERE url IS NOT NULL AND url != ''")
        all_url_nodes = cursor.fetchall()
        for r in all_url_nodes:
            if normalize_url(r["url"]) == norm_u:
                row = r
                break

    conn.close()
    if row:
        d = dict(row)
        d['embedding'] = json.loads(d['embedding']) if d['embedding'] else None
        return d
    return None

def insert_node(node_id, title, summary, url, source_type, embedding=None, 
                novelty_score=0.0, validation_score=0.0, momentum_score=0.0, cluster_id=None,
                contact_name=None, contact_linkedin=None, contact_email=None, contradiction_analysis=None,
                is_manual_or_scouted=0, document_type="research_paper", conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    cursor = conn.cursor()
    embedding_str = json.dumps(embedding) if embedding is not None else None
    created_at = datetime.utcnow().isoformat()
    
    cursor.execute("""
    INSERT INTO nodes (id, title, summary, url, source_type, created_at, embedding, novelty_score, validation_score, momentum_score, cluster_id, contact_name, contact_linkedin, contact_email, contradiction_analysis, is_manual_or_scouted, document_type)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        title=excluded.title,
        summary=excluded.summary,
        url=excluded.url,
        embedding=coalesce(excluded.embedding, nodes.embedding),
        novelty_score=excluded.novelty_score,
        validation_score=excluded.validation_score,
        momentum_score=excluded.momentum_score,
        cluster_id=coalesce(excluded.cluster_id, nodes.cluster_id),
        contact_name=coalesce(excluded.contact_name, nodes.contact_name),
        contact_linkedin=coalesce(excluded.contact_linkedin, nodes.contact_linkedin),
        contact_email=coalesce(excluded.contact_email, nodes.contact_email),
        contradiction_analysis=coalesce(excluded.contradiction_analysis, nodes.contradiction_analysis),
        is_manual_or_scouted=coalesce(excluded.is_manual_or_scouted, nodes.is_manual_or_scouted),
        document_type=coalesce(excluded.document_type, nodes.document_type)
    """, (node_id, title, summary, url, source_type, created_at, embedding_str, novelty_score, validation_score, momentum_score, cluster_id, contact_name, contact_linkedin, contact_email, contradiction_analysis, is_manual_or_scouted, document_type))
    
    if own_conn:
        conn.commit()
        conn.close()

def get_node(node_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        res = dict(row)
        res['embedding'] = json.loads(res['embedding']) if res['embedding'] else None
        return res
    return None

def get_all_nodes(include_retired=False):
    conn = get_db_connection()
    cursor = conn.cursor()
    if include_retired:
        cursor.execute("SELECT * FROM nodes ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT * FROM nodes WHERE status = 'active' OR status IS NULL ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    nodes = []
    for r in rows:
        d = dict(r)
        d['embedding'] = json.loads(d['embedding']) if d['embedding'] else None
        nodes.append(d)
    return nodes

def insert_cluster(cluster_id, name, description, centroid_embedding, parent_cluster_id=None, is_active=1, level=3, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    cursor = conn.cursor()
    centroid_str = json.dumps(centroid_embedding) if centroid_embedding is not None else None
    cursor.execute("""
    INSERT INTO clusters (id, name, description, centroid_embedding, parent_cluster_id, is_active, level)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(id) DO UPDATE SET
        name=excluded.name,
        description=excluded.description,
        centroid_embedding=excluded.centroid_embedding,
        parent_cluster_id=excluded.parent_cluster_id,
        is_active=excluded.is_active,
        level=excluded.level
    """, (cluster_id, name, description, centroid_str, parent_cluster_id, is_active, level))
    if own_conn:
        conn.commit()
        conn.close()

def get_all_clusters(active_only=True):
    conn = get_db_connection()
    cursor = conn.cursor()
    if active_only:
        cursor.execute("SELECT * FROM clusters WHERE is_active = 1")
    else:
        cursor.execute("SELECT * FROM clusters")
    rows = cursor.fetchall()
    conn.close()
    clusters = []
    for r in rows:
        d = dict(r)
        d['centroid_embedding'] = json.loads(d['centroid_embedding']) if d['centroid_embedding'] else None
        clusters.append(d)
    return clusters

def retire_cluster(cluster_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE clusters SET is_active = 0 WHERE id = ?", (cluster_id,))
    conn.commit()
    conn.close()

def insert_edge(source_id, target_id, relationship_type, similarity, conn=None):
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    cursor = conn.cursor()
    # Guard: only insert edge if both source and target nodes exist in DB
    cursor.execute("SELECT COUNT(*) FROM nodes WHERE id IN (?, ?)", (source_id, target_id))
    count = cursor.fetchone()[0]
    if count < 2:
        print(f"[DB] Skipping orphan edge: {source_id} -> {target_id} (only {count}/2 nodes exist)")
        if own_conn:
            conn.close()
        return
    cursor.execute("""
    INSERT INTO edges (source_id, target_id, relationship_type, similarity)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(source_id, target_id, relationship_type) DO UPDATE SET
        similarity=excluded.similarity
    """, (source_id, target_id, relationship_type, similarity))
    if own_conn:
        conn.commit()
        conn.close()

def get_all_edges():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM edges")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_node_cluster(node_id, cluster_id, classification_method='llm', tags=None):
    """Update a node's cluster assignment, classification method, and secondary tags."""
    conn = get_db_connection()
    cursor = conn.cursor()
    tags_str = json.dumps(tags) if tags else '[]'
    cursor.execute(
        "UPDATE nodes SET cluster_id = ?, classification_method = ?, tags = ? WHERE id = ?",
        (cluster_id, classification_method, tags_str, node_id)
    )
    conn.commit()
    conn.close()

def update_node_cross_disciplinary(node_id, is_cross_disciplinary, conn=None):
    """Set or clear the cross-disciplinary flag on a node."""
    own_conn = conn is None
    if own_conn:
        conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE nodes SET is_cross_disciplinary = ? WHERE id = ?",
        (1 if is_cross_disciplinary else 0, node_id)
    )
    if own_conn:
        conn.commit()
        conn.close()

def get_nodes_by_cluster(cluster_id):
    """Get all active nodes in a specific cluster/topic."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM nodes WHERE cluster_id = ? AND (status = 'active' OR status IS NULL)",
        (cluster_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_nodes_by_classification_method(method):
    """Get all active nodes with a specific classification method (e.g., 'fallback_nn')."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM nodes WHERE classification_method = ? AND (status = 'active' OR status IS NULL)",
        (method,)
    )
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d['embedding'] = json.loads(d['embedding']) if d.get('embedding') else None
        result.append(d)
    return result

def get_parking_lot_nodes():
    """Get all active nodes parked in evaluation/review topics."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT n.* FROM nodes n
        JOIN clusters c ON n.cluster_id = c.id
        WHERE (n.status = 'active' OR n.status IS NULL)
        AND (c.name LIKE '%Evaluation Parking%' OR c.name LIKE '%HITL Review%')
    """)
    rows = cursor.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d['embedding'] = json.loads(d['embedding']) if d.get('embedding') else None
        result.append(d)
    return result

def get_topic_node_counts():
    """Get node count per L3 topic cluster for split threshold checking."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.id, c.name, c.parent_cluster_id, COUNT(n.id) as node_count
        FROM clusters c
        LEFT JOIN nodes n ON n.cluster_id = c.id AND (n.status = 'active' OR n.status IS NULL)
        WHERE c.level = 3 AND c.is_active = 1
        GROUP BY c.id
        ORDER BY node_count DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def update_node_scores(node_id, novelty, validation, momentum):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    UPDATE nodes 
    SET novelty_score = ?, validation_score = ?, momentum_score = ? 
    WHERE id = ?
    """, (novelty, validation, momentum, node_id))
    conn.commit()
    conn.close()

def insert_sandbox_log(title, summary, novelty, validation, momentum):
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO sandbox_logs (title, summary, novelty, validation, momentum, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (title, summary, novelty, validation, momentum, created_at))
    conn.commit()
    conn.close()

def insert_scouting_history(query: str, embedding: list[float]):
    conn = get_db_connection()
    cursor = conn.cursor()
    emb_str = json.dumps(embedding)
    executed_at = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO scouting_history (query, query_embedding, executed_at)
    VALUES (?, ?, ?)
    """, (query, emb_str, executed_at))
    conn.commit()
    conn.close()

def get_scouting_history_past_two_weeks():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT query, query_embedding, executed_at 
    FROM scouting_history 
    WHERE datetime(executed_at) >= datetime('now', '-14 days')
    """)
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "query": r["query"],
            "embedding": json.loads(r["query_embedding"]) if r["query_embedding"] else None,
            "executed_at": r["executed_at"]
        })
    return results

def get_node_refresh_history_14d(node_id: str) -> list[str]:
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT refreshed_at 
    FROM node_refreshes 
    WHERE node_id = ? AND datetime(refreshed_at) >= datetime('now', '-14 days')
    ORDER BY refreshed_at ASC
    """, (node_id,))
    rows = cursor.fetchall()
    conn.close()
    return [r["refreshed_at"] for r in rows]

def log_node_refresh(node_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    refreshed_at = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO node_refreshes (node_id, refreshed_at)
    VALUES (?, ?)
    """, (node_id, refreshed_at))
    conn.commit()
    conn.close()

def get_nodes_needing_refresh(hours: int = 24) -> list[dict]:
    """Returns nodes needing auto-refresh using a dynamic quota.
    
    Priority order:
    1. Recently added nodes (within last N hours) that haven't been auto-refreshed yet
    2. Nodes whose cluster gained new siblings since their last score update
    3. Legacy/stale nodes (never refreshed or oldest refresh) to fill remaining quota
    
    Dynamic quota: max(20, ceil(total_active_nodes / 30)) — ensures all nodes refreshed within 30 days.
    """
    import math
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Calculate dynamic quota based on total active nodes
    cursor.execute("SELECT COUNT(*) FROM nodes WHERE status = 'active' OR status IS NULL")
    total_active = cursor.fetchone()[0]
    daily_quota = max(20, math.ceil(total_active / 30))
    
    # Priority 1+2: Recently added OR neighborhood-changed (always included)
    cursor.execute("""
    SELECT n.* FROM nodes n
    WHERE (n.status = 'active' OR n.status IS NULL)
    AND (
        -- Condition 1: Recently added (within last N hours), never auto-refreshed
        (datetime(n.created_at) >= datetime('now', ? || ' hours')
         AND (n.scores_updated_at IS NULL OR n.scores_updated_at = ''))
    OR
        -- Condition 2: Cluster got new nodes since this node's last score update
        (n.scores_updated_at IS NOT NULL AND n.scores_updated_at != ''
         AND EXISTS (
            SELECT 1 FROM nodes sibling
            WHERE sibling.cluster_id = n.cluster_id
            AND sibling.id != n.id
            AND (sibling.status = 'active' OR sibling.status IS NULL)
            AND datetime(sibling.created_at) > datetime(n.scores_updated_at)
         ))
    )
    ORDER BY n.created_at DESC
    """, (f'-{hours}',))
    priority_rows = cursor.fetchall()
    
    # Priority 3: Legacy/stale nodes to fill remaining quota (oldest-refreshed first)
    remaining_quota = max(0, daily_quota - len(priority_rows))
    legacy_rows = []
    if remaining_quota > 0:
        cursor.execute("""
        SELECT n.* FROM nodes n
        WHERE (n.status = 'active' OR n.status IS NULL)
        AND (
            -- Never refreshed
            n.scores_updated_at IS NULL OR n.scores_updated_at = ''
        )
        AND NOT (
            -- Exclude nodes already in priority set (recently added)
            datetime(n.created_at) >= datetime('now', ? || ' hours')
            AND (n.scores_updated_at IS NULL OR n.scores_updated_at = '')
        )
        ORDER BY n.created_at ASC
        LIMIT ?
        """, (f'-{hours}', remaining_quota))
        legacy_rows = cursor.fetchall()
        
        # If still room, grab oldest-refreshed nodes
        if len(legacy_rows) < remaining_quota:
            extra_quota = remaining_quota - len(legacy_rows)
            existing_ids = set()
            for r in priority_rows:
                existing_ids.add(r["id"])
            for r in legacy_rows:
                existing_ids.add(r["id"])
            placeholders = ','.join('?' * len(existing_ids)) if existing_ids else "''"
            cursor.execute(f"""
            SELECT n.* FROM nodes n
            WHERE (n.status = 'active' OR n.status IS NULL)
            AND n.scores_updated_at IS NOT NULL AND n.scores_updated_at != ''
            AND n.id NOT IN ({placeholders})
            ORDER BY datetime(n.scores_updated_at) ASC
            LIMIT ?
            """, (*existing_ids, extra_quota))
            legacy_rows.extend(cursor.fetchall())
    
    conn.close()
    
    # Combine and parse
    result = []
    seen_ids = set()
    for r in list(priority_rows) + list(legacy_rows):
        row_dict = dict(r)
        if row_dict["id"] in seen_ids:
            continue
        seen_ids.add(row_dict["id"])
        if row_dict.get('embedding'):
            try:
                row_dict['embedding'] = json.loads(row_dict['embedding'])
            except (json.JSONDecodeError, TypeError):
                row_dict['embedding'] = None
        result.append(row_dict)
    
    print(f"[AutoRefresh] Dynamic quota: {daily_quota}/day (total active: {total_active}). Selected: {len(result)} nodes ({len(priority_rows)} priority + {len(legacy_rows)} backfill).")
    return result

def mark_node_refreshed(node_id: str):
    """Stamps a node's scores_updated_at to current UTC time."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE nodes SET scores_updated_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), node_id)
    )
    conn.commit()
    conn.close()

def retire_node(node_id: str, reason: str = "link_dead"):
    """Soft-deletes a node by marking its status as 'retired'. Node stays in DB for traceability."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE nodes SET status = 'retired' WHERE id = ?",
        (node_id,)
    )
    conn.commit()
    conn.close()
    print(f"[DB] Node '{node_id}' retired (reason: {reason}). Removed from active graph.")

def get_reputable_domain(domain: str) -> float:
    """Check if domain is cached in reputable_domains table. Returns score or None."""
    if not domain:
        return None
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT score FROM reputable_domains WHERE domain = ?", (domain.lower().strip(),))
    row = cursor.fetchone()
    conn.close()
    return float(row["score"]) if row else None

def insert_reputable_domain(domain: str, score: float):
    """Inserts or updates dynamic domain validation score."""
    if not domain:
        return
    conn = get_db_connection()
    cursor = conn.cursor()
    added_at = datetime.utcnow().isoformat()
    cursor.execute("""
    INSERT INTO reputable_domains (domain, score, added_at)
    VALUES (?, ?, ?)
    ON CONFLICT(domain) DO UPDATE SET score = excluded.score, added_at = excluded.added_at
    """, (domain.lower().strip(), float(score), added_at))
    conn.commit()
    conn.close()
