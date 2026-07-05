import uuid
import json
import asyncio

from google import genai

from .db import (
    get_all_nodes, get_all_clusters, insert_node, insert_edge,
    insert_cluster, update_node_cluster, retire_cluster,
    insert_scouting_history, get_scouting_history_past_two_weeks,
    batch_transaction
)
from .scoring import (
    get_embedding, cosine_similarity,
    calculate_validation, calculate_momentum,
    calculate_edge_entropy, get_diverse_neighbors
)
from .clustering import assign_cluster, get_last_classification_result
from .agent import run_ingestion_agent, run_contradiction_agent


def check_query_semantic_cache(query: str):
    """
    Checks if a semantically similar scouting query has been run in the past 14 days.
    Returns the matching query string if similarity >= 0.88, else None.
    """
    if not query:
        return None
    try:
        history = get_scouting_history_past_two_weeks()
        if not history:
            return None
            
        query_emb = get_embedding(query.strip().lower())
        
        for h in history:
            if not h["embedding"]:
                continue
            sim = cosine_similarity(query_emb, h["embedding"])
            if sim >= 0.88:
                return h["query"]
        return None
    except Exception as ex:
        print(f"Error checking semantic scouting cache: {ex}")

async def process_ingestion(query: str, max_results: int, is_explicit_scout: bool = False):
    """Background task to run the ingestion agent, score new items, and check contradictions.
    Returns (processed_node_ids, truly_new_ids) - all touched IDs and only genuinely new inserts."""
    processed_node_ids = []
    truly_new_ids = []
    try:
        # Only delay for auto-triggered background scouting (not explicit user scouts)
        if not is_explicit_scout:
            await asyncio.sleep(12.0)
        
        # Check semantic cache first
        cached_match = check_query_semantic_cache(query)
        if cached_match:
            print(f"[ConceptRadar Cache] Semantic cache hit for '{query}' (matches '{cached_match}' in last 14 days). Skipping background scouting.")
            return processed_node_ids, truly_new_ids
            
        raw_items = await run_ingestion_agent(query, max_results)
        if not raw_items:
            print("No items ingested.")
            return processed_node_ids, truly_new_ids
            
        existing_nodes = get_all_nodes()
        existing_node_id_set = {n["id"] for n in existing_nodes}
        existing_ref_embs = [n["embedding"] for n in existing_nodes if n["source_type"] in ["arxiv", "github"] and n["embedding"]]
        
        # Collect all write operations during the loop, execute atomically at the end
        pending_writes = []  # list of (func, kwargs) tuples
        pending_ids = []     # track successfully processed IDs
        pending_new = []     # track truly new IDs
        
        for item in raw_items:
            await asyncio.sleep(0.1)  # Yield event loop control to allow instant user request processing
            node_id = item.get("id")
            title = item.get("title")
            summary = item.get("summary")
            url = item.get("url")
            source_type = item.get("source_type")
            metrics = item.get("metrics", {})
            
            if not node_id or not title:
                continue
            
            try:
                print(f"Processing ingested node: {node_id} - {title}")
                
                # 1. Generate embedding
                embedding = get_embedding(f"{title}\n{summary}")
                
                # 2. Find neighbors (fast, no LLM). New nodes have no edges, so entropy=0.
                #    Novelty will be set to LLM-only score from contradiction agent.
                neighbors = []
                for n in existing_nodes:
                    if n["id"] != node_id and n.get("embedding"):
                        sim = cosine_similarity(embedding, n["embedding"])
                        neighbors.append((sim, n))
                neighbors.sort(key=lambda x: x[0], reverse=True)
                top_neighbors = [n for sim, n in neighbors[:5]]
                max_sim = neighbors[0][0] if neighbors else 0.0
                
                # 3. Run cluster assignment + contradiction agent IN PARALLEL (both are LLM calls)
                cluster_task = asyncio.create_task(
                    asyncio.to_thread(assign_cluster, title, summary, embedding, existing_nodes)
                )
                contradiction_task = asyncio.create_task(
                    run_contradiction_agent(
                        {"id": node_id, "title": title, "summary": summary, "source_type": source_type},
                        top_neighbors,
                        max_sim=max_sim,
                        base_novelty=0.5
                    )
                )
                cluster_id, contradiction_data = await asyncio.gather(cluster_task, contradiction_task)
                
                # New scouted nodes have no edges yet (entropy=0), so novelty = LLM-only
                llm_novelty = contradiction_data.get("novelty_score", 0.5)
                novelty = max(0.0, min(1.0, llm_novelty))
                
                # Calculate validation and momentum
                # Get cluster size for momentum boost
                siblings = [n for n in existing_nodes if n.get("cluster_id") == cluster_id]
                cluster_size = len(siblings) + 1
                
                validation = calculate_validation(
                    source_type, 
                    citations=metrics.get("citations", 0),
                    is_reproduced=(contradiction_data.get("novelty_penalty", 0.0) > 0.0 and source_type == "github") # implements paper
                )
                
                momentum = calculate_momentum(
                    source_type,
                    stars=metrics.get("stars", 0),
                    forks=metrics.get("forks", 0),
                    citations=metrics.get("citations", 0),
                    cluster_size=0  # Store base momentum only; boost calculated at query time
                )
                
                # Queue node insert (will be committed atomically)
                pending_writes.append(("node", {
                    "node_id": node_id, "title": title, "summary": summary, "url": url,
                    "source_type": source_type, "embedding": embedding,
                    "novelty_score": novelty, "validation_score": validation,
                    "momentum_score": momentum, "cluster_id": cluster_id,
                    "is_manual_or_scouted": (1 if is_explicit_scout else 0)
                }))
                pending_ids.append(node_id)
                if node_id not in existing_node_id_set:
                    pending_new.append(node_id)
                
                # Queue edges from contradiction agent
                for edge in contradiction_data.get("edges", []):
                    target_id = edge.get("target_id")
                    rel_type = edge.get("relationship_type")
                    sim = edge.get("similarity", 0.5)
                    target_node = next((n for n in existing_nodes if n["id"] == target_id), None)
                    if target_node:
                        pending_writes.append(("edge", {
                            "source_id": node_id, "target_id": target_id,
                            "relationship_type": rel_type, "similarity": sim
                        }))
                        
                # Queue implicit nearest-neighbor edge
                if neighbors and neighbors[0][0] > 0.60:
                    nearest_sim, nearest_node = neighbors[0]
                    implicit_rel = "implements" if source_type == "github" and nearest_node["source_type"] == "arxiv" else "extends"
                    pending_writes.append(("edge", {
                        "source_id": node_id, "target_id": nearest_node["id"],
                        "relationship_type": implicit_rel, "similarity": nearest_sim
                    }))
                    
                # Add to local list so next items in loop can compare against it
                item_node = {
                    "id": node_id,
                    "title": title,
                    "summary": summary,
                    "embedding": embedding,
                    "source_type": source_type,
                    "cluster_id": cluster_id
                }
                existing_nodes.append(item_node)
                if source_type in ["arxiv", "github"]:
                    existing_ref_embs.append(embedding)
            except Exception as item_ex:
                print(f"[Ingestion] Failed to process item '{node_id}': {item_ex}. Skipping to next item.")
        
        # Commit all writes atomically — all-or-nothing
        if pending_writes:
            with batch_transaction() as txn_conn:
                for write_type, kwargs in pending_writes:
                    if write_type == "node":
                        insert_node(**kwargs, conn=txn_conn)
                    elif write_type == "edge":
                        insert_edge(**kwargs, conn=txn_conn)
            processed_node_ids = pending_ids
            truly_new_ids = pending_new
            print(f"[Ingestion] Committed {len(pending_writes)} writes atomically ({len(processed_node_ids)} nodes).")
                
        # T1: Cluster split logic removed — now handled by 24h batch cycle
        # via check_and_split_topics() in main.py auto-refresh loop

        # Log query to semantic cache
        try:
            query_emb = get_embedding(query.strip().lower())
            insert_scouting_history(query, query_emb)
            print(f"[ConceptRadar Cache] Cached query '{query}' in scouting history.")
        except Exception as cache_ex:
            print(f"Failed to insert scouting history cache: {cache_ex}")

        print("Ingestion batch processing complete!")
        return processed_node_ids, truly_new_ids
    except Exception as e:
        print(f"Error in background ingestion task: {e}")
        raise e


class ScoutQueueManager:
    """
    Manages an async queue for background scouting jobs with:
    1. Maximum 2 parallel worker tasks.
    2. Capacity-based job consumption (workers auto-pull next task when free).
    3. Gemini API rate-limit semaphore (max 3 concurrent calls).
    4. Capped batch items (max 5 results per scout task).
    """
    def __init__(self, max_workers: int = 2, max_gemini_concurrency: int = 3):
        self.queue = asyncio.Queue()
        self.max_workers = max_workers
        self.gemini_semaphore = asyncio.Semaphore(max_gemini_concurrency)
        self.workers = []
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        for i in range(self.max_workers):
            task = asyncio.create_task(self._worker_loop(i + 1))
            self.workers.append(task)
        print(f"[ScoutQueueManager] Started {self.max_workers} background scouting worker loops.")

    async def enqueue(self, query: str, max_results: int = 5):
        clean_query = query.strip()
        if not clean_query:
            return
        await self.queue.put({"query": clean_query, "max_results": min(5, max_results)})
        print(f"[ScoutQueueManager] Enqueued background scouting task for '{clean_query}' (Pending in queue: {self.queue.qsize()})")

    async def _worker_loop(self, worker_id: int):
        while True:
            job = None
            try:
                job = await self.queue.get()
                query = job["query"]
                max_results = job["max_results"]
                
                print(f"[ScoutWorker-{worker_id}] Dequeued task for '{query}'. Starting background scouting...")
                await process_ingestion(query, max_results)
                print(f"[ScoutWorker-{worker_id}] Completed task for '{query}'. Worker is ready for next job.")
            except asyncio.CancelledError:
                # Clean exit on shutdown — don't call task_done if we never got a job
                print(f"[ScoutWorker-{worker_id}] Shutting down gracefully.")
                break
            except Exception as ex:
                print(f"[ScoutWorker-{worker_id}] Error in worker task: {ex}")
            finally:
                if job is not None:
                    self.queue.task_done()


# Module-level singleton
scout_manager = ScoutQueueManager(max_workers=2, max_gemini_concurrency=3)
