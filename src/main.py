import os
import uuid
import json
import math
import hashlib
import asyncio
import urllib.parse
from datetime import datetime, timedelta

from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from google import genai
from .patches import apply_patches
apply_patches()

from .db import (
    init_db, insert_node, get_all_nodes, get_all_edges, insert_edge,
    get_all_clusters, insert_cluster, update_node_cluster, update_node_scores,
    retire_cluster, insert_scouting_history, get_scouting_history_past_two_weeks,
    get_node_refresh_history_14d, log_node_refresh, get_node_by_id_or_url,
    get_reputable_domain, insert_reputable_domain, get_db_connection,
    is_url_blacklisted, insert_blacklisted_url,
    get_nodes_needing_refresh, mark_node_refreshed, retire_node
)
from .scoring import (
    get_embedding, cosine_similarity, calculate_novelty,
    calculate_validation, calculate_momentum,
    calculate_edge_entropy, get_diverse_neighbors
)
from .agent import run_ingestion_agent, run_contradiction_agent, evaluate_publisher_authority
from .scraper import scrape_source_url
from .clustering import assign_cluster, get_last_classification_result, evaluate_cross_disciplinary, check_and_split_topics, reclassify_fallback_nodes, evaluate_parking_lots, propose_new_domain
from .validation import get_smart_validation_score, is_duplicate_match, get_publication_path_type
from .scouting import scout_manager, process_ingestion, check_query_semantic_cache
from .rate_limiter import gemini_generate

app = FastAPI(title="ConceptRadar API", version="1.0.0")

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models ---

class IngestRequest(BaseModel):
    query: str
    max_results: Optional[int] = 5

class IdeaRequest(BaseModel):
    title: str
    summary: str
    url: Optional[str] = None

class PromoteIdeaRequest(BaseModel):
    title: str
    summary: str
    novelty: float
    validation: float
    momentum: float
    cluster_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_linkedin: Optional[str] = None
    contact_email: Optional[str] = None

class UrlIngestRequest(BaseModel):
    url: str

class ManualIngestRequest(BaseModel):
    title: str
    url: str
    text: str

class RefreshNodeRequest(BaseModel):
    node_id: str

class ChatRequest(BaseModel):
    message: str
    session_id: str


# --- Startup Events ---

@app.on_event("startup")
def startup_init_db():
    init_db()

@app.on_event("startup")
async def startup_scout_manager():
    scout_manager.start()

@app.on_event("startup")
async def startup_auto_refresh():
    """Launches a background loop that auto-refreshes node scores every 24 hours."""
    asyncio.create_task(_auto_refresh_loop())

async def _auto_refresh_loop():
    """Background loop: refreshes stale node scores every 24 hours using the hybrid approach.
    
    For each node:
    1. HTTP HEAD check on URL — retire dead links (soft-delete)
    2. Recalculate novelty via embedding + contradiction agent
    3. On Gemini API error: skip (don't stamp) — retry next cycle
    4. On success: update scores + stamp
    """
    import urllib.request
    import urllib.error
    REFRESH_INTERVAL_SECONDS = 24 * 60 * 60  # 24 hours
    DELAY_BETWEEN_NODES = 2.0  # seconds between each node refresh (rate limiting)
    
    # Wait 60 seconds after startup before first run (let app fully initialize)
    await asyncio.sleep(60)
    
    while True:
        try:
            nodes_to_refresh = get_nodes_needing_refresh(hours=24)
            if nodes_to_refresh:
                print(f"[AutoRefresh] Starting cycle: {len(nodes_to_refresh)} nodes queued for score updates.")
                refreshed = 0
                retired = 0
                skipped = 0
                for node in nodes_to_refresh:
                    node_id = node["id"]
                    title = node.get("title", node_id)[:40]
                    url = node.get("url", "")
                    
                    # Step 1: Link validity check (HTTP HEAD)
                    if url:
                        try:
                            req = urllib.request.Request(url, method='HEAD')
                            req.add_header('User-Agent', 'ConceptRadar/1.0 (link-check)')
                            response = await asyncio.get_event_loop().run_in_executor(
                                None, lambda: urllib.request.urlopen(req, timeout=10)
                            )
                            # 2xx = OK, proceed
                        except urllib.error.HTTPError as http_err:
                            if http_err.code in (404, 410, 451):
                                # Dead link — retire the node
                                retire_node(node_id, reason=f"HTTP {http_err.code}: link dead")
                                retired += 1
                                print(f"[AutoRefresh] [{retired}] '{title}': RETIRED (HTTP {http_err.code})")
                                await asyncio.sleep(0.5)
                                continue
                            # Other HTTP errors (403, 429, 500): skip, try again next cycle
                            print(f"[AutoRefresh] '{title}': HTTP {http_err.code} — skipping (transient)")
                            skipped += 1
                            await asyncio.sleep(DELAY_BETWEEN_NODES)
                            continue
                        except Exception as url_ex:
                            # DNS/timeout/connection errors: transient — skip
                            print(f"[AutoRefresh] '{title}': URL check failed ({url_ex}) — skipping")
                            skipped += 1
                            await asyncio.sleep(DELAY_BETWEEN_NODES)
                            continue
                    
                    # Step 2: Score refresh
                    try:
                        summary = node["summary"]
                        embedding = node.get("embedding")
                        
                        if not embedding:
                            embedding = get_embedding(f"{node['title']}\n{summary}")
                        
                        # Get all other nodes for comparison
                        existing_nodes = get_all_nodes()
                        other_nodes = [n for n in existing_nodes if n["id"] != node_id]
                        
                        # Get diverse neighbors (3 same topic + 2 cross-topic)
                        node_dict = {"id": node_id, "title": node["title"], "summary": summary, "source_type": node["source_type"], "embedding": embedding, "cluster_id": node.get("cluster_id"), "is_cross_disciplinary": node.get("is_cross_disciplinary"), "tags": node.get("tags")}
                        clusters = get_all_clusters()
                        cmap = {c["id"]: c for c in clusters}
                        top_neighbors = get_diverse_neighbors(node_dict, other_nodes, cmap)
                        top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
                        max_sim = max((cosine_similarity(embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)
                        
                        # Build taxonomy context for improved LLM prompt
                        tax_ctx = build_taxonomy_context(node_dict, existing_nodes)
                        
                        # Run contradiction agent with taxonomy context
                        contradiction_data = await run_contradiction_agent(
                            node_dict,
                            top_neighbors,
                            max_sim=max_sim,
                            base_novelty=0.5,
                            model_name="gemini-2.5-flash",
                            taxonomy_context=tax_ctx
                        )
                        
                        llm_novelty = contradiction_data.get("novelty_score", 0.5)
                        # Blend with 3-component percentile model
                        all_edges = get_all_edges()
                        node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
                        revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, node_id, all_edges, node_topic_map, cmap)
                        contradiction_analysis = contradiction_data.get("critique", "")
                        
                        # Update scores in DB (all 4 components)
                        conn = get_db_connection()
                        conn.execute("""
                            UPDATE nodes 
                            SET novelty_score = ?, contradiction_analysis = ?,
                                llm_novelty_raw = ?, entropy_score = ?, structural_surprise = ?
                            WHERE id = ?
                        """, (revised_novelty, contradiction_analysis, llm_novelty, ent_raw, surp_raw, node_id))
                        conn.commit()
                        
                        # Stamp refresh time
                        mark_node_refreshed(node_id)
                        refreshed += 1
                        print(f"[AutoRefresh] [{refreshed}/{len(nodes_to_refresh)}] '{title}': novelty updated to {revised_novelty:.2f} (LLM={llm_novelty:.2f} ent={ent_raw:.3f} surp={surp_raw:.3f})")
                        
                    except Exception as score_ex:
                        # Gemini API or processing error — skip, don't stamp, retry next cycle
                        print(f"[AutoRefresh] '{title}': score refresh failed ({score_ex}) — will retry next cycle")
                        skipped += 1
                    
                    # Rate limiting delay between nodes
                    await asyncio.sleep(DELAY_BETWEEN_NODES)
                
                print(f"[AutoRefresh] Cycle complete: {refreshed} refreshed, {retired} retired, {skipped} skipped out of {len(nodes_to_refresh)} total.")
            else:
                print("[AutoRefresh] No nodes need refreshing this cycle.")
        except Exception as ex:
            print(f"[AutoRefresh] Cycle error: {ex}")
        
        # Sleep until next cycle
        await asyncio.sleep(REFRESH_INTERVAL_SECONDS)

        # --- T1: Taxonomy maintenance tasks (after node refresh cycle) ---
        try:
            print("[AutoRefresh] Running T1 taxonomy maintenance...")
            # 1. Re-classify fallback_nn nodes with full LLM
            await asyncio.to_thread(reclassify_fallback_nodes)
            # 2. Evaluate parking lots (only processes if items exist)
            await asyncio.to_thread(evaluate_parking_lots)
            # 3. Check topic splits (>= 50 threshold)
            await asyncio.to_thread(check_and_split_topics)
            # 4. Update cross-disciplinary flags
            await asyncio.to_thread(evaluate_cross_disciplinary)
            # 5. Propose new domains (only if Domain Eval Parking has items)
            await asyncio.to_thread(propose_new_domain)
            print("[AutoRefresh] T1 taxonomy maintenance complete.")
        except Exception as t1_ex:
            print(f"[AutoRefresh] T1 taxonomy maintenance error: {t1_ex}")


# --- Helper: Resolve category from cluster ---

def resolve_category(cluster_id: str):
    """Resolves a cluster_id to (category_id, category_name) by walking up the taxonomy."""
    clusters = get_all_clusters()
    cluster_map = {c["id"]: c["name"] for c in clusters}
    l3_c = next((c for c in clusters if c["id"] == cluster_id), None)
    category_id = l3_c.get("parent_cluster_id") if (l3_c and l3_c.get("level") == 3) else cluster_id
    category_name = cluster_map.get(category_id, "General AI")
    return category_id, category_name


def build_taxonomy_context(node: dict, all_nodes: list[dict]) -> dict:
    """Build taxonomy context dict for the improved LLM novelty prompt."""
    clusters = get_all_clusters()
    cmap = {c["id"]: c for c in clusters}
    topic = cmap.get(node.get("cluster_id", ""), {})
    area = cmap.get(topic.get("parent_cluster_id", ""), {})
    domain = cmap.get(area.get("parent_cluster_id", ""), {})
    peer_count = sum(1 for n in all_nodes if n.get("cluster_id") == node.get("cluster_id"))
    # Parse tags
    import json as _json
    tags_raw = node.get("tags", "[]")
    if isinstance(tags_raw, str):
        try:
            tags = _json.loads(tags_raw)
        except Exception:
            tags = []
    else:
        tags = tags_raw or []
    tag_names = [cmap.get(t, {}).get("name", t) for t in tags[:5]]
    return {
        "domain_name": domain.get("name", "Unknown"),
        "area_name": area.get("name", "Unknown"),
        "topic_name": topic.get("name", "Unknown"),
        "peer_count": peer_count,
        "is_cross_disciplinary": bool(node.get("is_cross_disciplinary")),
        "tag_names": tag_names,
    }


def _annotate_neighbors_with_taxonomy(neighbors: list[dict]) -> list[dict]:
    """Add _topic_name and _domain_name metadata to neighbor dicts for the LLM prompt."""
    clusters = get_all_clusters()
    cmap = {c["id"]: c for c in clusters}
    for n in neighbors:
        topic = cmap.get(n.get("cluster_id", ""), {})
        area = cmap.get(topic.get("parent_cluster_id", ""), {})
        domain = cmap.get(area.get("parent_cluster_id", ""), {})
        n["_topic_name"] = topic.get("name", "")
        n["_domain_name"] = domain.get("name", "")
    return neighbors


def blend_novelty(llm_novelty: float, node_id: str, edges: list[dict], node_topic_map: dict, cluster_map: dict) -> tuple[float, float, float]:
    """3-component percentile-normalized novelty score.
    
    Formula: 0.50 × LLM_percentile + 0.25 × Entropy_percentile + 0.25 × Surprise_percentile
    
    Returns: (final_blended_score, entropy_raw, surprise_raw)
    """
    from .scoring import calculate_edge_entropy, calculate_structural_surprise
    
    entropy_raw = calculate_edge_entropy(node_id, edges, node_topic_map, cluster_map)
    surprise_raw = calculate_structural_surprise(node_id, edges, node_topic_map)
    
    # Cold start: no edges → LLM only, capped at 0.50
    if entropy_raw == 0 and surprise_raw == 0:
        return (max(0.0, min(0.50, llm_novelty * 0.50)), entropy_raw, surprise_raw)
    
    # Fetch all existing raw scores for percentile computation
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT llm_novelty_raw, entropy_score, structural_surprise FROM nodes "
        "WHERE llm_novelty_raw IS NOT NULL"
    ).fetchall()
    conn.close()
    
    all_llm = sorted([r['llm_novelty_raw'] for r in rows if r['llm_novelty_raw'] and r['llm_novelty_raw'] > 0])
    all_ent = sorted([r['entropy_score'] for r in rows if r['entropy_score'] and r['entropy_score'] > 0])
    all_surp = sorted([r['structural_surprise'] for r in rows if r['structural_surprise'] and r['structural_surprise'] > 0])
    
    def percentile_rank(value, sorted_values):
        """Compute percentile rank of value within sorted_values."""
        if not sorted_values:
            return 0.5
        count_below = sum(1 for v in sorted_values if v < value)
        count_equal = sum(1 for v in sorted_values if v == value)
        return (count_below + 0.5 * count_equal) / len(sorted_values)
    
    llm_pct = percentile_rank(llm_novelty, all_llm) if all_llm else 0.5
    ent_pct = percentile_rank(entropy_raw, all_ent) if all_ent else 0.5
    surp_pct = percentile_rank(surprise_raw, all_surp) if all_surp else 0.5
    
    blended = 0.50 * llm_pct + 0.25 * ent_pct + 0.25 * surp_pct
    return (max(0.0, min(1.0, blended)), entropy_raw, surprise_raw)


# =====================================================================
# API ENDPOINTS
# =====================================================================


# --- Graph API ---

@app.get("/api/graph")
async def get_graph():
    """Returns nodes and edges formatted for Cytoscape.js, including Level 1 and Level 2 virtual bubbles."""
    nodes = get_all_nodes()
    edges = get_all_edges()
    clusters = get_all_clusters(active_only=True)
    
    cytoscape_elements = []
    
    # Build cluster lookup maps
    cluster_map = {c["id"]: c for c in clusters}
    
    l1_clusters = [c for c in clusters if c.get("level") == 1]
    l2_clusters = [c for c in clusters if c.get("level") == 2]
    l3_clusters = [c for c in clusters if c.get("level") == 3]
    
    # Calculate L2 category node counts for dynamic sizing
    l2_node_counts = {}
    for n in nodes:
        cid = n.get("cluster_id")
        if cid:
            l3 = cluster_map.get(cid)
            if l3 and l3.get("level") == 3:
                parent_cat = l3.get("parent_cluster_id")
                if parent_cat:
                    l2_node_counts[parent_cat] = l2_node_counts.get(parent_cat, 0) + 1
            elif l3 and l3.get("level") == 2:
                l2_node_counts[cid] = l2_node_counts.get(cid, 0) + 1
    
    # Emit Level 1 Domain bubbles
    for d in l1_clusters:
        total_nodes = sum(
            l2_node_counts.get(c["id"], 0) for c in l2_clusters if c.get("parent_cluster_id") == d["id"]
        )
        if total_nodes == 0:
            continue
        cytoscape_elements.append({
            "group": "nodes",
            "data": {
                "id": f"domain_{d['id']}",
                "label": d["name"],
                "description": d.get("description", ""),
                "is_domain_bubble": True,
                "node_count": total_nodes,
                "level": 1
            }
        })

    # Emit Level 2 Category bubbles
    for c in l2_clusters:
        count = l2_node_counts.get(c["id"], 0)
        if count == 0:
            continue
        parent_domain = c.get("parent_cluster_id")
        cytoscape_elements.append({
            "group": "nodes",
            "data": {
                "id": f"category_{c['id']}",
                "label": c["name"],
                "description": c.get("description", ""),
                "is_cluster_bubble": True,
                "node_count": count,
                "parent_domain_id": f"domain_{parent_domain}" if parent_domain else None,
                "level": 2
            }
        })

    # Emit real nodes (L3 topic nodes)
    for n in nodes:
        cid = n["cluster_id"]
        parent_cat_id = None
        if cid:
            l3 = cluster_map.get(cid)
            if l3 and l3.get("level") == 3:
                parent_cat_id = l3.get("parent_cluster_id")
            elif l3 and l3.get("level") == 2:
                parent_cat_id = cid

        # Compute dynamic label size based on momentum
        mom = n.get("momentum_score", 0.0)
        cluster_id_for_node = n.get("cluster_id")
        sibling_count = sum(1 for nn in nodes if nn.get("cluster_id") == cluster_id_for_node)
        cluster_boost = min(0.5, sibling_count * 0.02) if sibling_count > 1 else 0.0
        boosted_momentum = min(1.0, mom + cluster_boost)
        dynamic_size = max(30, min(200, int(30 + boosted_momentum * 170)))

        source_icon = {"arxiv": "📄", "github": "💻", "web": "🌐", "idea": "💡"}.get(n["source_type"], "📌")
        
        # Resolve L3 topic name for color attribution
        topic_name = ""
        if cid:
            l3_info = cluster_map.get(cid)
            if l3_info:
                topic_name = l3_info.get("name", "")

        cytoscape_elements.append({
            "group": "nodes",
            "data": {
                "id": n["id"],
                "label": f'{source_icon} {n["title"]}',
                "title": n["title"],
                "summary": n["summary"],
                "url": n["url"],
                "source_type": n["source_type"],
                "novelty": n["novelty_score"],
                "validation": n["validation_score"],
                "momentum": boosted_momentum,
                "cluster_id": cid,
                "topic_name": topic_name,
                "parent_category_id": f"category_{parent_cat_id}" if parent_cat_id else None,
                "dynamic_size": dynamic_size,
                "created_at": n.get("created_at", ""),
                "contact_name": n.get("contact_name"),
                "contact_linkedin": n.get("contact_linkedin"),
                "contact_email": n.get("contact_email"),
                "document_type": n.get("document_type", "other"),
                "scores_updated_at": n.get("scores_updated_at", ""),
                "is_cross_disciplinary": bool(n.get("is_cross_disciplinary", 0)),
                "tags": json.loads(n.get("tags", "[]")) if isinstance(n.get("tags"), str) else (n.get("tags") or [])
            }
        })

    # Build node ID set for orphan edge filtering
    node_ids = {el["data"]["id"] for el in cytoscape_elements if el["group"] == "nodes"}

    valid_edges = []
    orphan_edges = []
    for e in edges:
        # Filter orphan edges: only include edges where both source and target exist
        if e["source_id"] not in node_ids or e["target_id"] not in node_ids:
            orphan_edges.append(e)
            continue
        valid_edges.append(e)
        cytoscape_elements.append({
            "group": "edges",
            "data": {
                "id": f'{e["source_id"]}__{e["target_id"]}__{e["relationship_type"]}',
                "source": e["source_id"],
                "target": e["target_id"],
                "relationship_type": e["relationship_type"],
                "similarity": e["similarity"]
            }
        })

    # Auto-heal: delete orphan edges from the database so they don't reappear
    if orphan_edges:
        conn = get_db_connection()
        for oe in orphan_edges:
            conn.execute(
                "DELETE FROM edges WHERE source_id = ? AND target_id = ? AND relationship_type = ?",
                (oe["source_id"], oe["target_id"], oe["relationship_type"])
            )
        conn.commit()
        print(f"[API] Cleaned up {len(orphan_edges)} orphan edges from database.")

    # --- Reach Score Calculation ---
    # Measures taxonomic diversity of a node's connections.
    # Cross-domain edges are weighted higher than same-topic edges.
    
    # Build taxonomy lookup: node_id -> (L3 topic_id, L2 category_id, L1 domain_id)
    node_taxonomy = {}
    for n in nodes:
        cid = n.get("cluster_id")
        l3_id = cid
        l2_id = None
        l1_id = None
        if cid:
            l3_info = cluster_map.get(cid)
            if l3_info and l3_info.get("level") == 3:
                l2_id = l3_info.get("parent_cluster_id")
                if l2_id:
                    l2_info = cluster_map.get(l2_id)
                    if l2_info:
                        l1_id = l2_info.get("parent_cluster_id")
            elif l3_info and l3_info.get("level") == 2:
                l2_id = cid
                l1_id = l3_info.get("parent_cluster_id")
        node_taxonomy[n["id"]] = (l3_id, l2_id, l1_id)

    # Build adjacency: node_id -> list of connected node_ids
    adjacency = {}
    for e in valid_edges:
        adjacency.setdefault(e["source_id"], []).append(e["target_id"])
        adjacency.setdefault(e["target_id"], []).append(e["source_id"])

    # Calculate Reach for each node
    node_reach = {}
    for nid, (l3, l2, l1) in node_taxonomy.items():
        neighbors = adjacency.get(nid, [])
        if not neighbors:
            node_reach[nid] = 0.0
            continue
        
        total_weight = 0.0
        for neighbor_id in neighbors:
            n_l3, n_l2, n_l1 = node_taxonomy.get(neighbor_id, (None, None, None))
            if l1 != n_l1:
                total_weight += 1.0   # Different L1 Domain — max interdisciplinary
            elif l2 != n_l2:
                total_weight += 0.6   # Same Domain, different L2 Category
            elif l3 != n_l3:
                total_weight += 0.3   # Same Category, different L3 Topic
            else:
                total_weight += 0.1   # Same L3 Topic — trivial
        
        # Normalize: sqrt scaling to prevent runaway scores for hyper-connected nodes
        # A node with 4 cross-domain links ≈ 0.80, 8 ≈ 0.95
        raw = total_weight / max(len(neighbors), 1)  # Average weight per edge
        count_factor = math.sqrt(min(len(neighbors), 20) / 20)  # Scale by edge count (cap at 20)
        reach = min(1.0, raw * count_factor)
        node_reach[nid] = round(reach, 3)

    # Update node elements with Reach and re-boost momentum
    for el in cytoscape_elements:
        if el["group"] != "nodes" or el["data"].get("is_cluster_bubble") or el["data"].get("is_domain_bubble"):
            continue
        nid = el["data"]["id"]
        reach = node_reach.get(nid, 0.0)
        el["data"]["reach"] = reach
        
        # Re-calculate momentum with Reach boost (×0.25, capped at 1.0)
        current_momentum = el["data"].get("momentum", 0.5)
        boosted = min(1.0, current_momentum + reach * 0.25)
        el["data"]["momentum"] = boosted
        el["data"]["dynamic_size"] = max(30, min(200, int(30 + boosted * 170)))
        
        # Dot size for Cytoscape: momentum contributes 60%, reach contributes 40%
        dot_size = int(10 + boosted * 22 + reach * 18)
        el["data"]["dot_size"] = min(50, dot_size)
        
    return cytoscape_elements


# --- Ingest Trigger (Scouting) ---

@app.post("/api/ingest")
async def trigger_ingest(req: IngestRequest):
    """Endpoint to trigger synchronous ingestion for a research keyword."""
    try:
        cached_match = check_query_semantic_cache(req.query)
        if cached_match:
            # Find existing nodes most relevant to this cached query via embedding similarity
            try:
                query_emb = get_embedding(req.query)
                all_nodes = get_all_nodes()
                scored = []
                for n in all_nodes:
                    if n.get("embedding"):
                        sim = cosine_similarity(query_emb, n["embedding"])
                        if sim > 0.30:
                            scored.append((sim, n["id"]))
                scored.sort(reverse=True)
                relevant_ids = [nid for _, nid in scored[:10]]
            except Exception:
                relevant_ids = []
            
            # If fewer than 10 relevant nodes exist, bypass cache and run a full scout
            if len(relevant_ids) < 10:
                print(f"[ConceptRadar Cache] Cache hit for '{req.query}' but only {len(relevant_ids)} relevant nodes found (<10). Bypassing cache for deeper scouting.")
                processed_ids, new_ids = await process_ingestion(req.query, req.max_results, is_explicit_scout=True)
                # Combine: processed IDs + any existing relevant IDs (deduplicated)
                combined = list(dict.fromkeys((processed_ids or []) + relevant_ids))
                return {"status": "Ingestion completed.", "topic": req.query, "node_ids": combined, "new_node_ids": new_ids or []}
            
            # Cache hit with enough results: all are existing nodes, none are truly new
            return {"status": "Cached", "topic": req.query, "cached_match": cached_match, "node_ids": relevant_ids, "new_node_ids": []}
        processed_ids, new_ids = await process_ingestion(req.query, req.max_results, is_explicit_scout=True)
        return {"status": "Ingestion completed.", "topic": req.query, "node_ids": processed_ids or [], "new_node_ids": new_ids or []}
    except Exception as ex:
        err_msg = str(ex)
        if "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
            raise HTTPException(
                status_code=429,
                detail="Gemini API rate limit exceeded. Please wait a few seconds and try again."
            )
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {err_msg}")


# --- URL Ingestion ---

# In-memory lock to prevent duplicate concurrent ingestion of the same URL
_ingesting_urls: set[str] = set()

@app.post("/api/ingest-url")
async def ingest_url(req: UrlIngestRequest, background_tasks: BackgroundTasks):
    """
    Ingests a URL, scraping its content, generating embeddings,
    determining its cluster category, saving it to the database,
    and launching background scouting to enrich the surrounding radar landscape.
    """
    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL cannot be empty.")
    
    # Dedup lock: reject if this URL is already being ingested by another request
    if url in _ingesting_urls:
        raise HTTPException(status_code=409, detail="This URL is already being ingested. Please wait.")
    _ingesting_urls.add(url)
    
    try:
        # 1. Fast direct database index lookup first (prevents wasting resources scraping)
        existing_check = get_node_by_id_or_url(url=url)
        if existing_check:
            category_id, category_name = resolve_category(existing_check["cluster_id"])
            return {
                "status": "success", 
                "node_id": existing_check["id"], 
                "message": "Source already exists on the map.",
                "category_id": category_id,
                "category_name": category_name
            }

        # 2. Check blacklist (URLs known to fail scraping)
        blacklisted = is_url_blacklisted(url)
        if blacklisted:
            print(f"[API URL Ingestion] URL is blacklisted: {url} (reason: {blacklisted['reason']})")
            return JSONResponse(
                status_code=422,
                content={
                    "status": "failed",
                    "detail": f"This URL has been previously flagged as unscrape-able: {blacklisted['reason']}. Use 'Add Published Source' with manual entry instead."
                }
            )

        # 3. Scrape the URL (only if not found in db)
        try:
            scraped_data = await scrape_source_url(url)
        except Exception as scrape_err:
            reason = str(scrape_err)[:200]
            insert_blacklisted_url(url, reason)
            return JSONResponse(
                status_code=422,
                content={
                    "status": "failed",
                    "detail": "This webpage blocks automated scrapers or returned unreadable content. It has been added to the blacklist. Use manual entry instead."
                }
            )
        title = scraped_data["title"]
        summary = scraped_data["summary"]
        source_type = scraped_data["source_type"]
        published_at = scraped_data.get("published_at")
        metrics = scraped_data.get("metrics", {})
        document_type = scraped_data.get("document_type", "other")
        
        # 3. Check if a node with this ID already exists
        node_id = scraped_data.get("id")
        if not node_id:
            url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
            node_id = f"{source_type}:{url_hash}"

        existing_check = get_node_by_id_or_url(node_id=node_id)
        if existing_check:
            category_id, category_name = resolve_category(existing_check["cluster_id"])
            return {
                "status": "success", 
                "node_id": node_id, 
                "message": "Source already exists on the map.",
                "category_id": category_id,
                "category_name": category_name
            }

        # 3. Generate embedding
        embedding = get_embedding(f"{title}\n{summary}")
        
        # 4. Assign cluster category
        existing_nodes = get_all_nodes()
        cluster_id = assign_cluster(title, summary, embedding, existing_nodes)
        # Retrieve secondary metadata from classification
        classification_result = get_last_classification_result()
        classification_tags = classification_result.get('tags', []) if classification_result else []
        classification_method = classification_result.get('classification_method', 'llm') if classification_result else 'llm'
        
        # 5. Smart validation scoring (Seed list + cached/dynamic LLM evaluation)
        val_score = await get_smart_validation_score(url, title, summary, source_type)
        
        # 6. Novelty calculated after contradiction agent via entropy+LLM blend
        raw_nov_score = 0.5  # placeholder, refined below after contradiction agent
        
        # Calculate momentum dynamically
        mom_score = 0.20
        if source_type == "github":
            github_stars = metrics.get("stars", 0)
            boost = min(0.8, math.log(github_stars + 1) / 8.0) if github_stars > 0 else 0.0
            mom_score = min(1.0, 0.20 + boost)

        # --- Layer 1: Authoritative domain boost ---
        # Check URL path type: artifact (whitepaper/paper), blog, or general
        parsed_url = urllib.parse.urlparse(url)
        netloc = parsed_url.netloc.lower().split(':')[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        url_path_type = get_publication_path_type(url)  # "artifact", "blog", or "general"
        
        AUTHORITY_DOMAINS = {
            # Government / regulatory
            "nist.gov": "standard", "iso.org": "standard", "iec.ch": "standard",
            "eur-lex.europa.eu": "legislation", "ec.europa.eu": "framework_official",
            "digital-strategy.ec.europa.eu": "legislation",
            "whitehouse.gov": "framework_official", "congress.gov": "legislation",
            "gov.uk": "framework_official", "legislation.gov.uk": "legislation",
            # Standards bodies & industry authorities
            "mitre.org": "framework_official", "attack.mitre.org": "framework_official",
            "cloudsecurityalliance.org": "best_practice",
            "owasp.org": "best_practice", "cisa.gov": "framework_official",
            "enisa.europa.eu": "framework_official",
            # Major tech company official AI resources
            "aws.amazon.com": "best_practice", "cloud.google.com": "best_practice",
            "learn.microsoft.com": "best_practice", "ai.google": "best_practice",
            "anthropic.com": "best_practice", "responsible.ai": "best_practice",
        }
        
        is_authority_domain = False
        authority_domain_type = None
        for domain_pattern, domain_type in AUTHORITY_DOMAINS.items():
            if netloc == domain_pattern or netloc.endswith("." + domain_pattern):
                is_authority_domain = True
                authority_domain_type = domain_type
                break
        
        if is_authority_domain:
            if url_path_type == "blog":
                # Blog from authority: mild upgrade to blog_post, NOT full authority type
                # Still better than random Medium posts, but not as strong as official artifacts
                document_type = "blog_post"
                print(f"[Authority Blog] '{netloc}' blog post — mild boost (blog_post), not full {authority_domain_type}")
            else:
                # Artifact or general page from authority: full upgrade
                type_rank = {"legislation": 6, "regulation": 5, "standard": 4, 
                             "framework_official": 3, "best_practice": 2}
                current_rank = type_rank.get(document_type, 0)
                domain_rank = type_rank.get(authority_domain_type, 0)
                if domain_rank > current_rank:
                    print(f"[Authority] Domain '{netloc}' upgraded document_type: {document_type} -> {authority_domain_type}")
                    document_type = authority_domain_type
        
        # Also check for .gov TLD (any country's government domain)
        if document_type in ("other", "research_paper", "blog_post") and not is_authority_domain:
            gov_tlds = (".gov", ".gov.", ".mil", ".gouv.", ".gob.")
            if any(t in netloc for t in gov_tlds):
                if url_path_type == "blog":
                    document_type = "blog_post"
                    print(f"[Authority Blog] Gov domain '{netloc}' blog post — mild boost")
                else:
                    document_type = "framework_official"
                    print(f"[Authority] Government domain '{netloc}' -> framework_official")

        # --- Layer 2: Platform & domain detection (reduce "other") ---
        if document_type == "other":
            # YouTube -> own category
            YOUTUBE_DOMAINS = {"youtube.com", "youtu.be"}
            if any(netloc == yd or netloc.endswith("." + yd) for yd in YOUTUBE_DOMAINS):
                document_type = "youtube"
                print(f"[YouTube] '{netloc}' -> youtube")
            # Known blog/content platforms -> blog_post
            elif any(netloc == bp or netloc.endswith("." + bp) for bp in 
                     {"medium.com", "substack.com", "dev.to", "hashnode.dev",
                      "wordpress.com", "blogger.com", "hackernoon.com",
                      "towardsdatascience.com"}):
                document_type = "blog_post"
                print(f"[Blog Platform] '{netloc}' -> blog_post")
            # .edu domains -> research_paper
            elif netloc.endswith(".edu") or ".edu." in netloc or netloc.endswith(".ac.uk"):
                document_type = "research_paper"
                print(f"[Academic] '{netloc}' -> research_paper")
            # Known standards bodies not in AUTHORITY_DOMAINS
            elif any(netloc == sb or netloc.endswith("." + sb) for sb in 
                     ["oecd.ai", "oecd.org", "omg.org", "beuth.de", "din.de"]):
                document_type = "standard"
                print(f"[Standards Body] '{netloc}' -> standard")
            # Carnegie, Brookings, etc. -> research_paper
            elif any(netloc == rp or netloc.endswith("." + rp) for rp in
                     ["carnegieendowment.org", "brookings.edu", "rand.org"]):
                document_type = "research_paper"
                print(f"[Think Tank] '{netloc}' -> research_paper")
        
        # Also catch source_type=youtube that wasn't classified
        if source_type == "youtube" and document_type not in ("youtube",):
            document_type = "youtube"

        # --- Layer 2.5: LLM fallback for remaining "other" ---
        if document_type == "other":
            try:
                fallback_prompt = f"""Classify this document into EXACTLY ONE type. Try hard to avoid "other".

Title: {title}
Summary: {summary[:300]}
URL: {url}

Types:
- "legislation" = Official law or directive
- "regulation" = Binding regulatory rules
- "standard" = Published standard (NIST, ISO, IEEE, OECD, DIN)
- "framework_official" = Official government/authority framework
- "best_practice" = Industry best practice from recognized authority
- "research_paper" = Academic paper, preprint, or think-tank analysis
- "blog_post" = Blog, opinion, news, tutorial, vendor content
- "tool" = Software, library, SDK, open-source project
- "youtube" = YouTube video content
- "idea" = Original concept proposal
- "other" = Only if truly none of the above fit

Return ONLY the type string, nothing else. Example: research_paper"""
                
                llm_text = await gemini_generate(fallback_prompt)
                if llm_text:
                    llm_type = llm_text.strip('"').strip("'").lower()
                    valid_fallback = {"legislation", "regulation", "standard", "framework_official",
                                     "best_practice", "research_paper", "blog_post", "tool", "youtube", "idea", "other"}
                    if llm_type in valid_fallback:
                        document_type = llm_type
                        print(f"[LLM Fallback] Reclassified '{title[:40]}' from 'other' -> '{llm_type}'")
                    else:
                        print(f"[LLM Fallback] Got unrecognized '{llm_type}', keeping 'other'")
            except Exception as ex:
                print(f"[LLM Fallback] Error: {ex}, keeping 'other'")

        # --- Layer 3: Score overrides based on document_type ---
        SCORE_OVERRIDES = {
            "legislation":        {"val_floor": 0.99, "nov_cap": 0.10},
            "regulation":         {"val_floor": 0.98, "nov_cap": 0.15},
            "standard":           {"val_floor": 0.97, "nov_cap": 0.20},
            "framework_official": {"val_floor": 0.96, "nov_cap": 0.25},
            "best_practice":      {"val_floor": 0.95, "nov_cap": 0.35},
        }
        
        # Authority blog posts get a mild validation boost (above random blogs, below official artifacts)
        if is_authority_domain and url_path_type == "blog":
            old_val = val_score
            val_score = max(val_score, 0.70)
            if old_val != val_score:
                print(f"[Authority Blog Override] '{title}': val {old_val:.2f}->{val_score:.2f} (authority blog mild boost)")
        else:
            override = SCORE_OVERRIDES.get(document_type)
            if override:
                old_val = val_score
                val_score = max(val_score, override["val_floor"])
                if old_val != val_score:
                    print(f"[Authority Override] '{title}' ({document_type}): val {old_val:.2f}->{val_score:.2f}")

        # 7. Fast DB insertion (instant response for user UI — novelty refined below)
        insert_node(
            node_id=node_id,
            title=title,
            summary=summary,
            url=url,
            source_type=source_type,
            embedding=embedding,
            novelty_score=0.5,
            validation_score=val_score,
            momentum_score=mom_score,
            cluster_id=cluster_id,
            contradiction_analysis="Prior-art critique & contradiction check in progress...",
            is_manual_or_scouted=1,
            document_type=document_type
        )

        # 7b. Run contradiction agent for LLM-blended novelty (consistent with scout/sandbox paths)
        try:
            node_dict = {"id": node_id, "title": title, "summary": summary, "source_type": source_type, "embedding": embedding, "cluster_id": cluster_id, "is_cross_disciplinary": classification_result.get("is_cross_disciplinary") if classification_result else False, "tags": classification_tags}
            clusters = get_all_clusters()
            cmap = {c["id"]: c for c in clusters}
            top_neighbors = get_diverse_neighbors(node_dict, existing_nodes, cmap)
            top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
            max_sim = max((cosine_similarity(embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)

            # Build taxonomy context for improved LLM prompt
            tax_ctx = build_taxonomy_context(node_dict, existing_nodes)

            contradiction_data = await run_contradiction_agent(
                node_dict,
                top_neighbors,
                max_sim=max_sim,
                base_novelty=0.5,
                model_name="gemini-2.5-flash",
                taxonomy_context=tax_ctx
            )

            # Blend with 3-component percentile model
            llm_novelty = contradiction_data.get("novelty_score", 0.5)
            all_edges = get_all_edges()
            node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
            revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, node_id, all_edges, node_topic_map, cmap)
            contradiction_analysis = contradiction_data.get("critique", "")

            # Re-apply authority novelty cap if applicable
            override = SCORE_OVERRIDES.get(document_type)
            if override and "nov_cap" in override:
                revised_novelty = min(revised_novelty, override["nov_cap"])

            # Update node with all 4 component scores
            conn = get_db_connection()
            conn.execute("""
                UPDATE nodes
                SET novelty_score = ?, contradiction_analysis = ?,
                    llm_novelty_raw = ?, entropy_score = ?, structural_surprise = ?
                WHERE id = ?
            """, (revised_novelty, contradiction_analysis, llm_novelty, ent_raw, surp_raw, node_id))
            conn.commit()
            raw_nov_score = revised_novelty
            mark_node_refreshed(node_id)
            print(f"[LLM Novelty] '{title[:40]}': LLM={llm_novelty:.2f} -> blended={revised_novelty:.2f} (ent={ent_raw:.3f} surp={surp_raw:.3f})")
        except Exception as ex:
            print(f"[LLM Novelty] Contradiction agent failed for '{title[:40]}': {ex} (keeping placeholder novelty)")

        # Resolve parent L2 Category cluster ID and name
        category_id, category_name = resolve_category(cluster_id)

        # Trigger background scouting and contradiction critique via managed queue
        scout_keywords = title.split(":")[0].strip()[:50]
        if scout_keywords:
            await scout_manager.enqueue(scout_keywords, 5)

        print(f"[API URL Ingestion] Ingested node: '{title}' (type: {document_type}, Nov: {raw_nov_score:.2f}, Val: {val_score:.2f}) into category cluster: '{category_id}' ({category_name})")
        return {
            "status": "success", 
            "node_id": node_id,
            "category_id": category_id,
            "category_name": category_name
        }
    except HTTPException:
        raise
    except Exception as ex:
        print(f"[API URL Ingestion] Failed to ingest URL: {ex}")
        return JSONResponse(
            status_code=500,
            content={"status": "failed", "detail": f"Ingestion failed: {str(ex)}"}
        )
    finally:
        _ingesting_urls.discard(url)


# --- Manual Text Ingestion ---

@app.post("/api/ingest-manual")
async def ingest_manual(req: ManualIngestRequest, background_tasks: BackgroundTasks):
    """
    DEACTIVATED: Manual ingestion bypasses the automated scoring/classification
    pipeline and cannot guarantee consistency. All sources must go through the
    automated Add Source or Scouting pipelines.
    """
    raise HTTPException(
        status_code=501,
        detail="Manual ingestion is not available. Please use the Add Source (URL) or Scouting features instead."
    )

    # --- Original implementation preserved for reference ---
    # try:
    #     title = req.title.strip()
    #     url = req.url.strip()
    #     text = req.text.strip()
    #     ... (full implementation removed for consistency guarantees)
    # except Exception as ex:
    #     raise HTTPException(status_code=500, detail=f"Manual ingestion failed: {str(ex)}")


# --- Sandbox: Analyze Idea ---

@app.post("/api/analyze-idea")
async def analyze_idea(req: IdeaRequest, background_tasks: BackgroundTasks):
    """
    Sandbox Endpoint: Embeds and calculates scores/contradictions for a user's raw idea 
    without saving it permanent to the database.
    Checks for duplicates/prior-art matches (staggered thresholds + LLM reranking) and redirects if found.
    """
    title = req.title
    summary = req.summary
    url = req.url
    
    # 0. Check description length (word count >= 100)
    word_count = len(summary.split())
    if word_count < 100:
        raise HTTPException(
            status_code=400,
            detail=f"Description is too short ({word_count} words). To avoid LLM hallucinations, please provide a detailed explanation of at least 100 words outlining the mechanism, architecture, and problem solved."
        )
        
    # 1. Run detail adequacy check using Gemini
    try:
        adequacy_prompt = f"""
        Evaluate if the following concept description has enough technical logic, architectural structure, or conceptual coherence to be evaluated for novelty and validation.
        
        CRITICAL RULES:
        - Be highly permissive. Do NOT act like a peer-reviewer demanding full implementation details, code specs, math proofs, or concrete parameters.
        - Accept high-level architectural frameworks, research proposals, conceptual governance structures, and theoretical integrations.
        - Only reject (classify as INSUFFICIENT) if the description is pure gibberish, nonsensical spam, completely off-topic (e.g. personal notes, grocery lists), or too brief/vague to represent a coherent idea.
        
        Concept:
        Title: {title}
        Description: {summary}
        
        Return ONLY 'SUFFICIENT' or 'INSUFFICIENT: [Reason why the text is gibberish, spam, or lacks a coherent concept]'.
        """
        client = genai.Client()
        adequacy_resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=adequacy_prompt
        )
        adequacy_result = adequacy_resp.text.strip()
        if adequacy_result.startswith("INSUFFICIENT"):
            reason = adequacy_result.replace("INSUFFICIENT:", "").strip()
            raise HTTPException(
                status_code=400,
                detail=f"Description is too vague or lacks technical detail to be evaluated: {reason}"
            )
    except HTTPException:
        raise
    except Exception as ex:
        print(f"[Sandbox Ingestion] Adequacy LLM check failed: {ex}")
        
    # 2. If a URL is provided, check if it already exists in the database first (fast path)
    if url and url.strip():
        url = url.strip()
        existing_check = get_node_by_id_or_url(url=url)
        if existing_check:
            print(f"[Sandbox Ingestion] URL already exists locally (Fast Path): '{url}'")
            category_id, category_name = resolve_category(existing_check["cluster_id"])
            return {
                "status": "redirected",
                "matched_node": {
                    "id": existing_check["id"],
                    "title": existing_check["title"],
                    "url": existing_check["url"],
                    "category_id": category_id,
                    "category_name": category_name
                }
            }

    # 3. If a URL is provided, run safety, relevancy, and alignment validation
    if url and url.strip():
        print(f"[Sandbox Ingestion] Concept linked to published URL: '{url}'")
        try:
            # Scrape URL content
            scraped_data = await scrape_source_url(url)
            cand_title = scraped_data["title"]
            cand_summary = scraped_data["summary"]
            cand_source_type = scraped_data["source_type"]
            cand_id = scraped_data.get("id")
            
            if not cand_id:
                url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()[:12]
                cand_id = f"{cand_source_type}:{url_hash}"
                
            # safety & alignment check using Gemini
            safety_prompt = f"""
            Analyze the scraped publication content and check for:
            1. Inappropriate, illegal, or abusive content.
            2. Relevancy/Alignment: Does this scraped content describe the same topic, mechanism, or project as the user-pitched concept below?
            
            User's Pitched Concept:
            Title: {title}
            Description: {summary}
            
            Scraped URL Content:
            Title: {cand_title}
            Snippet/Summary: {cand_summary}
            
            Determine if the scraped content is safe/appropriate AND aligns with the user's concept description.
            If unsafe, illegal, or unrelated, explain why. If valid, return 'VALID'.
            Response must start with 'VALID' if ok, or 'INVALID: [Reason]' if not.
            """
            client = genai.Client()
            safety_resp = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=safety_prompt
            )
            validation_result = safety_resp.text.strip()
            if not validation_result.startswith("VALID"):
                print(f"[Sandbox Ingestion] Safety/relevancy validation failed: {validation_result}")
                raise HTTPException(status_code=400, detail=f"URL validation failed: {validation_result.replace('INVALID:', '').strip()}")
                
            # Check if this ID or URL is already in our DB (O(1) direct query)
            existing_check = get_node_by_id_or_url(cand_id, url)
            if existing_check:
                print(f"[Sandbox Ingestion] Candidate already exists locally: '{cand_title}'")
                category_id, category_name = resolve_category(existing_check["cluster_id"])
                return {
                    "status": "redirected",
                    "matched_node": {
                        "id": existing_check["id"],
                        "title": existing_check["title"],
                        "url": existing_check["url"],
                        "category_id": category_id,
                        "category_name": category_name
                    }
                }
                
            # Ingest candidate permanently
            cand_embedding = get_embedding(f"{cand_title}\n{cand_summary}")
            existing_nodes = get_all_nodes()
            cat_id = assign_cluster(cand_title, cand_summary, cand_embedding, existing_nodes)
            # Retrieve secondary metadata from classification
            cls_result = get_last_classification_result()
            category_id, category_name = resolve_category(cat_id)
            
            val_score = calculate_validation(cand_source_type)
            
            # Get diverse neighbors and build taxonomy context
            node_dict = {"id": cand_id, "title": cand_title, "summary": cand_summary, "source_type": cand_source_type, "embedding": cand_embedding, "cluster_id": cat_id, "is_cross_disciplinary": cls_result.get("is_cross_disciplinary") if cls_result else False, "tags": cls_result.get("tags", []) if cls_result else []}
            clusters = get_all_clusters()
            cmap = {c["id"]: c for c in clusters}
            top_neighbors = get_diverse_neighbors(node_dict, existing_nodes, cmap)
            top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
            max_sim = max((cosine_similarity(cand_embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)
            
            tax_ctx = build_taxonomy_context(node_dict, existing_nodes)
            
            contradiction_data = await run_contradiction_agent(
                node_dict,
                top_neighbors,
                max_sim=max_sim,
                base_novelty=0.5,
                model_name="gemini-2.5-flash",
                taxonomy_context=tax_ctx
            )
            
            # Blend with 3-component percentile model
            llm_novelty = contradiction_data.get("novelty_score", 0.5)
            all_edges = get_all_edges()
            node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
            revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, cand_id, all_edges, node_topic_map, cmap)
            contradiction_analysis = contradiction_data.get("critique", "")
            
            insert_node(
                node_id=cand_id,
                title=cand_title,
                summary=cand_summary,
                url=url,
                source_type=cand_source_type,
                embedding=cand_embedding,
                novelty_score=revised_novelty,
                validation_score=val_score,
                momentum_score=0.20,
                cluster_id=cat_id,
                contradiction_analysis=contradiction_analysis,
                is_manual_or_scouted=1
            )
            print(f"[Sandbox Ingestion] Ingested linked external publication permanently: '{cand_title}'")
            
            # Extract keywords for background auto-scouting
            scout_query = contradiction_data.get("keywords")
            if scout_query:
                print(f"[ConceptRadar Auto-Scouting] Triggering background scouting for keywords: '{scout_query}'")
                await scout_manager.enqueue(scout_query, 5)
                
            return {
                "status": "redirected",
                "matched_node": {
                    "id": cand_id,
                    "title": cand_title,
                    "url": url,
                    "category_id": category_id,
                    "category_name": category_name
                },
                "scout_query": scout_query
            }
            
        except HTTPException:
            raise
        except Exception as e_ingest:
            print(f"[Sandbox Ingestion] URL Ingestion failed: {e_ingest}")
            raise HTTPException(status_code=400, detail=f"Failed to scrape or analyze the provided URL: {str(e_ingest)}")

    # Generate embedding
    embedding = get_embedding(f"{title}\n{summary}")
    
    # 1. Check for duplicates in local database
    existing_nodes = get_all_nodes()
    local_match = None
    for n in existing_nodes:
        if n.get("embedding") and n["source_type"] in ["arxiv", "github", "web"]:
            if is_duplicate_match(title, summary, n["title"], n["summary"], embedding, n["embedding"]):
                local_match = n
                break
                    
    if local_match:
        print(f"[Sandbox De-duplication] Local duplicate match found: '{local_match['title']}'")
        category_id, category_name = resolve_category(local_match["cluster_id"])
        return {
            "status": "redirected",
            "matched_node": {
                "id": local_match["id"],
                "title": local_match["title"],
                "url": local_match["url"],
                "category_id": category_id,
                "category_name": category_name
            }
        }
        
    # 2. Check for duplicates in external literature (general web prior-art search)
    try:
        client = genai.Client()
        kw_prompt = f"Extract 1-2 search terms for finding scientific publications or articles related to this topic. Title: '{title}', Description: '{summary}'. Return only the keywords separated by spaces, no punctuation or extra words."
        kw_response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=kw_prompt
        )
        search_keywords = kw_response.text.strip().replace('"', '').replace("'", "")
        print(f"[Sandbox De-duplication] Extracted search keywords: '{search_keywords}'")
        
        # Search DuckDuckGo HTML using two queries
        import urllib.request
        import urllib.parse
        import re
        import ssl
        
        queries = [title, search_keywords]
        found_urls = []
        ctx_ssl = ssl._create_unverified_context()
        
        for q in queries:
            try:
                print(f"[Sandbox De-duplication] Querying DuckDuckGo for: '{q}'")
                encoded_query = urllib.parse.quote(q)
                ddg_url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
                req_ddg = urllib.request.Request(
                    ddg_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
                )
                with urllib.request.urlopen(req_ddg, context=ctx_ssl, timeout=10) as response:
                    html = response.read().decode('utf-8')
                    
                links = re.findall(r'href="([^"]+)"', html)
                for link in links:
                    if "/l/?uddg=" in link:
                        actual_url = link.split("uddg=")[1].split("&")[0]
                        actual_url = urllib.parse.unquote(actual_url)
                        found_urls.append(actual_url)
                    elif link.startswith("http") and not "duckduckgo.com" in link:
                        found_urls.append(link)
            except Exception as e_search:
                print(f"[Sandbox De-duplication] DuckDuckGo search query '{q}' failed: {e_search}")
                
        # Filter candidate URLs
        candidates = []
        seen = set()
        for u in found_urls:
            if u in seen:
                continue
            seen.add(u)
            if any(dom in u for dom in ["arxiv.org", "github.com", "medium.com", "researchgate.net", "substack.com"]):
                candidates.append(u)
                
        # Limit to top 4 candidates to avoid excessive API time
        candidates = candidates[:4]
        print(f"[Sandbox De-duplication] Found candidate URLs to check: {candidates}")
        
        for cand_url in candidates:
            try:
                print(f"[Sandbox De-duplication] Scraping candidate URL: '{cand_url}'")
                scraped_data = await scrape_source_url(cand_url)
                cand_title = scraped_data["title"]
                cand_summary = scraped_data["summary"]
                cand_source_type = scraped_data["source_type"]
                cand_id = scraped_data.get("id")
                
                if not cand_id:
                    url_hash = hashlib.md5(cand_url.encode('utf-8')).hexdigest()[:12]
                    cand_id = f"{cand_source_type}:{url_hash}"
                
                # Check if this ID or URL is already in our DB (O(1) direct query)
                existing_check = get_node_by_id_or_url(cand_id, cand_url)
                if existing_check:
                    print(f"[Sandbox De-duplication] Candidate already exists locally: '{cand_title}'")
                    category_id, category_name = resolve_category(existing_check["cluster_id"])
                    return {
                        "status": "redirected",
                        "matched_node": {
                            "id": existing_check["id"],
                            "title": existing_check["title"],
                            "url": existing_check["url"],
                            "category_id": category_id,
                            "category_name": category_name
                        }
                    }
                
                # Embed and calculate similarity + LLM reranking
                cand_embedding = get_embedding(f"{cand_title}\n{cand_summary}")
                
                if is_duplicate_match(title, summary, cand_title, cand_summary, embedding, cand_embedding):
                    print(f"[Sandbox De-duplication] External duplicate match found: '{cand_title}'")
                    
                    # Ingest candidate permanently
                    cat_id = assign_cluster(cand_title, cand_summary, cand_embedding, existing_nodes)
                    # Retrieve secondary metadata from classification
                    cls_result2 = get_last_classification_result()
                    category_id, category_name = resolve_category(cat_id)
                    
                    val_score = calculate_validation(cand_source_type)
                    
                    # Get diverse neighbors and build taxonomy context
                    node_dict = {"id": cand_id, "title": cand_title, "summary": cand_summary, "source_type": cand_source_type, "embedding": cand_embedding, "cluster_id": cat_id, "is_cross_disciplinary": cls_result2.get("is_cross_disciplinary") if cls_result2 else False, "tags": cls_result2.get("tags", []) if cls_result2 else []}
                    clusters = get_all_clusters()
                    cmap = {c["id"]: c for c in clusters}
                    top_neighbors = get_diverse_neighbors(node_dict, existing_nodes, cmap)
                    top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
                    max_sim = max((cosine_similarity(cand_embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)
                    
                    tax_ctx = build_taxonomy_context(node_dict, existing_nodes)
                    
                    contradiction_data = await run_contradiction_agent(
                        node_dict,
                        top_neighbors,
                        max_sim=max_sim,
                        base_novelty=0.5,
                        model_name="gemini-2.5-flash",
                        taxonomy_context=tax_ctx
                    )
                    
                    # Blend with 3-component percentile model
                    llm_novelty = contradiction_data.get("novelty_score", 0.5)
                    all_edges = get_all_edges()
                    node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
                    revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, cand_id, all_edges, node_topic_map, cmap)
                    contradiction_analysis = contradiction_data.get("critique", "")
                    
                    insert_node(
                        node_id=cand_id,
                        title=cand_title,
                        summary=cand_summary,
                        url=cand_url,
                        source_type=cand_source_type,
                        embedding=cand_embedding,
                        novelty_score=revised_novelty,
                        validation_score=val_score,
                        momentum_score=0.20,
                        cluster_id=cat_id,
                        contradiction_analysis=contradiction_analysis,
                        is_manual_or_scouted=1
                    )
                    print(f"[Sandbox De-duplication] Ingested matched external publication permanently: '{cand_title}'")
                    
                    # Extract keywords for background auto-scouting
                    scout_query = contradiction_data.get("keywords")
                    if scout_query:
                        print(f"[ConceptRadar Auto-Scouting] Triggering background scouting for keywords: '{scout_query}'")
                        await scout_manager.enqueue(scout_query, 5)
                        
                    return {
                        "status": "redirected",
                        "matched_node": {
                            "id": cand_id,
                            "title": cand_title,
                            "url": cand_url,
                            "category_id": category_id,
                            "category_name": category_name
                        },
                        "scout_query": scout_query
                    }
            except Exception as e_cand:
                print(f"[Sandbox De-duplication] Failed checking candidate URL '{cand_url}': {e_cand}")
    except Exception as ex:
        print(f"[Sandbox De-duplication] External duplicate search failed: {ex}")
        
    # Dynamic Cluster name approximation
    nearest_node = None
    max_sim = 0.0
    for n in existing_nodes:
        if n.get("embedding"):
            sim = cosine_similarity(embedding, n["embedding"])
            if sim > max_sim:
                max_sim = sim
                nearest_node = n
                
    cluster_name = "Emerging Category"
    cluster_id = None
    category_id = None
    category_name = "Other Category"
    if max_sim > 0.70 and nearest_node and nearest_node.get("cluster_id"):
        cluster_id = nearest_node["cluster_id"]
        category_id, category_name = resolve_category(cluster_id)
        clusters = get_all_clusters()
        cluster_map = {c["id"]: c["name"] for c in clusters}
        cluster_name = cluster_map.get(cluster_id, "General AI")
    
    # Get diverse neighbors and build taxonomy context
    node_dict = {"id": "sandbox:idea", "title": title, "summary": summary, "source_type": "idea", "embedding": embedding, "cluster_id": cluster_id or (nearest_node.get("cluster_id") if nearest_node else None), "is_cross_disciplinary": False, "tags": []}
    clusters = get_all_clusters()
    cmap = {c["id"]: c for c in clusters}
    top_neighbors = get_diverse_neighbors(node_dict, existing_nodes, cmap)
    top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
    max_sim = max((cosine_similarity(embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)
    
    tax_ctx = build_taxonomy_context(node_dict, existing_nodes)
    
    # Run contradiction agent with taxonomy context
    contradiction_data = await run_contradiction_agent(
        node_dict,
        top_neighbors,
        max_sim=max_sim,
        base_novelty=0.5,
        model_name="gemini-2.5-flash",
        taxonomy_context=tax_ctx
    )
    
    # Blend with 3-component percentile model
    llm_novelty = contradiction_data.get("novelty_score", 0.5)
    all_edges = get_all_edges()
    node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
    revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, "sandbox:idea", all_edges, node_topic_map, cmap)
    
    validation = calculate_validation("idea")
    momentum = 0.3  # Baseline static momentum for raw user idea
 
    # Log the sandbox idea privately for internal analysis
    try:
        from .db import insert_sandbox_log
        insert_sandbox_log(title, summary, revised_novelty, validation, momentum)
    except Exception as ex:
        print(f"Failed to log sandbox idea privately: {ex}")
    
    # Format matches list for UI
    matches = []
    for n in top_neighbors:
        sim = cosine_similarity(embedding, n["embedding"]) if n.get("embedding") else 0.0
        matches.append({
            "id": n["id"],
            "title": n["title"],
            "summary": n["summary"],
            "url": n["url"],
            "source_type": n["source_type"],
            "similarity": sim
        })
        
    # Extract keywords and generated summary directly from the consolidated agent analysis
    brief_summary = contradiction_data.get("summary", summary[:250] + "...")
    scout_query = contradiction_data.get("keywords")
    
    if scout_query:
        print(f"[ConceptRadar Auto-Scouting] Triggering background scouting for keywords: '{scout_query}'")
        await scout_manager.enqueue(scout_query, 5)
        
    return {
        "title": title,
        "summary": brief_summary,
        "x": revised_novelty,
        "y": validation,
        "novelty": revised_novelty,
        "validation": validation,
        "momentum": momentum,
        "cluster_id": cluster_id,
        "cluster_name": cluster_name,
        "category_id": category_id,
        "category_name": category_name,
        "contradiction_analysis": contradiction_data.get("analysis", "No severe contradictions detected."),
        "matches": matches,
        "suggested_edges": contradiction_data.get("edges", []),
        "scout_query": scout_query
    }


# --- Promote Idea ---

@app.post("/api/promote-idea")
async def promote_idea(req: PromoteIdeaRequest):
    """Promotes a sandbox idea to a permanent node in the database, with optional contact info."""
    try:
        node_id = f"idea:{uuid.uuid4().hex[:8]}"
        embedding = get_embedding(f"{req.title}\n{req.summary}")
        
        insert_node(
            node_id=node_id,
            title=req.title,
            summary=req.summary,
            url=None,
            source_type="idea",
            embedding=embedding,
            novelty_score=req.novelty,
            validation_score=req.validation,
            momentum_score=req.momentum,
            cluster_id=req.cluster_id,
            contact_name=req.contact_name,
            contact_linkedin=req.contact_linkedin,
            contact_email=req.contact_email,
            is_manual_or_scouted=1,
            document_type="idea"
        )
        return {"status": "Idea promoted successfully.", "node_id": node_id}
    except Exception as ex:
        print(f"Error promoting sandbox idea: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to promote idea: {str(ex)}")


# --- Refresh Node ---

@app.get("/api/refresh-status/{node_id:path}")
async def get_refresh_status(node_id: str):
    history = get_node_refresh_history_14d(node_id)
    if len(history) >= 3:
        oldest_time = datetime.fromisoformat(history[0])
        next_allowed = oldest_time + timedelta(days=14)
        time_left_sec = (next_allowed - datetime.utcnow()).total_seconds()
        
        if time_left_sec > 0:
            days_left = int(time_left_sec / 86400)
            hours_left = int((time_left_sec % 86400) / 3600)
            minutes_left = int((time_left_sec % 3600) / 60)
            
            if days_left > 0:
                time_str = f"{days_left}d {hours_left}h remaining"
            elif hours_left > 0:
                time_str = f"{hours_left}h {minutes_left}m remaining"
            else:
                time_str = f"{minutes_left}m remaining"
                
            return {
                "allowed": False,
                "reason": f"Node updated 3 times in last 14d. Locked for {time_str}.",
                "refreshes_used": len(history)
            }
            
    return {
        "allowed": True,
        "refreshes_used": len(history),
        "refreshes_remaining": max(0, 3 - len(history))
    }

@app.post("/api/refresh-node")
async def refresh_node(req: RefreshNodeRequest):
    node_id = req.node_id
    
    # 1. Fetch the node from the database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
    node = cursor.fetchone()
    conn.close()
    
    if not node:
        raise HTTPException(status_code=404, detail="Node not found.")
        
    # 2. Check the rate limit
    history = get_node_refresh_history_14d(node_id)
    if len(history) >= 3:
        oldest_time = datetime.fromisoformat(history[0])
        next_allowed = oldest_time + timedelta(days=14)
        time_left_sec = (next_allowed - datetime.utcnow()).total_seconds()
        if time_left_sec > 0:
            days_left = int(time_left_sec / 86400)
            hours_left = int((time_left_sec % 86400) / 3600)
            minutes_left = int((time_left_sec % 3600) / 60)
            
            if days_left > 0:
                time_str = f"{days_left}d {hours_left}h"
            elif hours_left > 0:
                time_str = f"{hours_left}h {minutes_left}m"
            else:
                time_str = f"{minutes_left}m"
                
            raise HTTPException(
                status_code=429, 
                detail=f"Refresh locked: Node was updated 3 times within the last 14 days. Next refresh available in {time_str}."
            )
            
    # 3. Log the refresh in the database
    log_node_refresh(node_id)
    
    # 4. Perform the re-evaluation
    try:
        title = node["title"]
        summary = node["summary"]
        embedding_str = node["embedding"]
        
        # Parse or generate embedding
        if embedding_str:
            embedding = json.loads(embedding_str)
        else:
            embedding = get_embedding(summary)
            
        # Get all other nodes
        existing_nodes = get_all_nodes()
        other_nodes = [n for n in existing_nodes if n["id"] != node_id]
        
        # Convert sqlite3.Row to dict so .get() works
        node = dict(node)
        
        # Get diverse neighbors (3 same topic + 2 cross-topic)
        node_dict = {"id": node_id, "title": title, "summary": summary, "source_type": node["source_type"], "embedding": embedding, "cluster_id": node.get("cluster_id"), "is_cross_disciplinary": node.get("is_cross_disciplinary"), "tags": node.get("tags")}
        clusters = get_all_clusters()
        cmap = {c["id"]: c for c in clusters}
        top_neighbors = get_diverse_neighbors(node_dict, other_nodes, cmap)
        top_neighbors = _annotate_neighbors_with_taxonomy(top_neighbors)
        max_sim = max((cosine_similarity(embedding, n["embedding"]) for n in top_neighbors if n.get("embedding")), default=0.0)
        
        # Build taxonomy context for improved LLM prompt
        tax_ctx = build_taxonomy_context(node_dict, existing_nodes)
        
        # Run contradiction agent with taxonomy context
        contradiction_data = await run_contradiction_agent(
            node_dict,
            top_neighbors,
            max_sim=max_sim,
            base_novelty=0.5,
            model_name="gemini-2.5-flash",
            taxonomy_context=tax_ctx
        )
        
        # Blend with 3-component percentile model
        llm_novelty = contradiction_data.get("novelty_score", 0.5)
        all_edges = get_all_edges()
        node_topic_map = {n["id"]: n.get("cluster_id", "") for n in existing_nodes}
        revised_novelty, ent_raw, surp_raw = blend_novelty(llm_novelty, node_id, all_edges, node_topic_map, cmap)
        contradiction_analysis = contradiction_data.get("critique", "")
        
        validation = calculate_validation(node["source_type"])
        
        # Update database with all 4 component scores
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
        UPDATE nodes 
        SET novelty_score = ?, validation_score = ?, contradiction_analysis = ?,
            llm_novelty_raw = ?, entropy_score = ?, structural_surprise = ?
        WHERE id = ?
        """, (revised_novelty, validation, contradiction_analysis, llm_novelty, ent_raw, surp_raw, node_id))
        conn.commit()
        conn.close()
        
        # Stamp refresh time
        mark_node_refreshed(node_id)
        
        return {
            "status": "success",
            "node": {
                "id": node_id,
                "novelty": revised_novelty,
                "validation": validation,
                "contradiction_analysis": contradiction_analysis
            }
        }
    except Exception as ex:
        print(f"Error refreshing node {node_id}: {ex}")
        raise HTTPException(status_code=500, detail=f"Failed to refresh node: {str(ex)}")


# --- Static Files ---

class NoCacheStaticFiles(StaticFiles):
    """Custom StaticFiles to disable browser caching during development."""
    def is_not_modified(self, response_headers, request_headers) -> bool:
        return False
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

# Create static directory if it doesn't exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)

# --- Chatbot Endpoint ---

@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Chat with the ConceptRadar research assistant. Supports multi-turn."""
    from .chatbot import run_chatbot
    try:
        response = await run_chatbot(request.message, request.session_id)
        return {"response": response}
    except Exception as e:
        print(f"[Chat API] Error: {e}")
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


# Serve favicon for browsers that request /favicon.ico directly
favicon_path = os.path.join(static_dir, "favicon.png")

from fastapi.responses import FileResponse as _FileResponse

@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    if os.path.exists(favicon_path):
        return _FileResponse(favicon_path, media_type="image/png")
    return Response(status_code=204)

# Mount the static files (Frontend dashboard)
app.mount("/", NoCacheStaticFiles(directory=static_dir, html=True), name="static")
