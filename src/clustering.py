"""
ConceptRadar Classification Agent (T1 Overhaul)

Closed-set taxonomy picker with confidence routing, cross-disciplinary evaluation,
topic splitting, and autonomous domain creation via dual-LLM consensus.
"""
import uuid
import json
import re

from google import genai

from .rate_limiter import gemini_generate_sync
from .db import (
    get_all_clusters, insert_cluster, get_all_edges, get_all_nodes,
    update_node_cluster, update_node_cross_disciplinary,
    get_nodes_by_classification_method, get_parking_lot_nodes,
    get_topic_node_counts, get_nodes_by_cluster, batch_transaction
)
from .scoring import cosine_similarity


# ---------------------------------------------------------------------------
# Taxonomy helpers
# ---------------------------------------------------------------------------

def _build_taxonomy_tree() -> dict:
    """Build a structured taxonomy dict from the clusters table.
    Returns: { 'domains': [ { id, name, desc, areas: [ { id, name, desc, topics: [...] } ] } ] }
    """
    active = get_all_clusters(active_only=True)
    l1s = [c for c in active if c["level"] == 1]
    l2s = [c for c in active if c["level"] == 2]
    l3s = [c for c in active if c["level"] == 3]

    domains = []
    for d in l1s:
        areas = []
        for a in [x for x in l2s if x["parent_cluster_id"] == d["id"]]:
            topics = [
                {"id": t["id"], "name": t["name"], "description": t["description"]}
                for t in l3s if t["parent_cluster_id"] == a["id"]
            ]
            areas.append({"id": a["id"], "name": a["name"], "description": a["description"], "topics": topics})
        domains.append({"id": d["id"], "name": d["name"], "description": d["description"], "areas": areas})
    return {"domains": domains}


def _build_taxonomy_prompt_text(taxonomy: dict) -> str:
    """Format the taxonomy as a compact text tree for the LLM prompt."""
    lines = []
    for d in taxonomy["domains"]:
        lines.append(f"DOMAIN: {d['name']} (ID: {d['id']})")
        for a in d["areas"]:
            lines.append(f"  AREA: {a['name']} (ID: {a['id']})")
            topic_strs = [f"{t['name']} [{t['id']}]" for t in a["topics"]]
            lines.append(f"    TOPICS: {', '.join(topic_strs)}")
    return "\n".join(lines)


def _get_topic_id_set() -> set:
    """Return set of all active L3 topic IDs."""
    active = get_all_clusters(active_only=True)
    return {c["id"] for c in active if c["level"] == 3}


def _get_domain_for_topic(topic_id: str) -> str | None:
    """Resolve a topic_id to its parent domain_id."""
    active = get_all_clusters(active_only=True)
    by_id = {c["id"]: c for c in active}
    topic = by_id.get(topic_id)
    if not topic:
        return None
    area = by_id.get(topic.get("parent_cluster_id"))
    if not area:
        return None
    return area.get("parent_cluster_id")


def _get_area_for_topic(topic_id: str) -> str | None:
    """Resolve a topic_id to its parent area_id."""
    active = get_all_clusters(active_only=True)
    by_id = {c["id"]: c for c in active}
    topic = by_id.get(topic_id)
    if not topic:
        return None
    return topic.get("parent_cluster_id")


# ---------------------------------------------------------------------------
# Main classification function
# ---------------------------------------------------------------------------

def assign_cluster(node_title: str, node_summary: str, embedding: list[float], existing_nodes: list[dict]) -> str:
    """Closed-set taxonomy picker: classifies a node into the curated taxonomy.

    Returns: The L3 topic cluster_id string.
    Side effects: Updates the node's tags and classification_method via the caller.
    """
    # Import examples lazily to avoid circular imports at module load
    try:
        from .taxonomy_examples import TAXONOMY_EXAMPLES
    except ImportError:
        TAXONOMY_EXAMPLES = {}

    taxonomy = _build_taxonomy_tree()

    if not taxonomy["domains"]:
        # No taxonomy seeded yet — should not happen after migration
        print("[Classifier] WARNING: No taxonomy found. Returning fallback.")
        return "cluster_initial"

    taxonomy_text = _build_taxonomy_prompt_text(taxonomy)

    # Build few-shot example text
    example_lines = []
    for topic_id, examples in TAXONOMY_EXAMPLES.items():
        if examples:
            example_lines.append(f"  {topic_id}: {'; '.join(examples)}")
    examples_text = "\n".join(example_lines[:100])  # Cap to keep prompt manageable

    prompt = f"""You are the ConceptRadar Classification Agent. Your task is to classify the following research node into the MOST APPROPRIATE existing Level 3 Topic in our curated taxonomy.

NODE TO CLASSIFY:
Title: {node_title}
Summary: {node_summary[:500]}

TAXONOMY (Domain → Area → Topic):
{taxonomy_text}

EXAMPLE CLASSIFICATIONS (topic_id: example paper titles):
{examples_text}

RULES:
1. You MUST pick an existing Topic ID from the taxonomy above. Do NOT invent new topics.
2. Pick the single BEST-FIT Topic. Consider the Domain first, then Area, then Topic.
3. If the node doesn't fit ANY topic well, use a parking topic:
   - If you know the Domain but can't pick a Topic: use that Domain's "Topic Evaluation Parking"
   - If you can't even determine the Domain: use the closest Domain's "Domain Evaluation Parking"
4. Return secondary_tags: a list of OTHER topic IDs that are also relevant (can be 0 to 5).
5. Return a confidence score between 0.0 and 1.0.
6. Think step by step: which Domain? -> which Area? -> which Topic?

Return ONLY a raw JSON object (no markdown backticks):
{{
  "topic_id": "the_exact_topic_id",
  "confidence": 0.85,
  "reasoning": "Brief explanation of classification decision",
  "secondary_tags": ["other_topic_id_1", "other_topic_id_2"]
}}"""

    try:
        resp_text = gemini_generate_sync(prompt, model="gemini-2.5-flash", max_retries=3, base_delay=2.0)

        if not resp_text:
            raise ValueError("Empty response from Gemini classification")

        # Clean response
        if "```" in resp_text:
            resp_text = re.sub(r'^```(?:json)?\s*', '', resp_text, flags=re.MULTILINE)
            resp_text = re.sub(r'\s*```$', '', resp_text, flags=re.MULTILINE)
        resp_text = resp_text.strip()
        resp_text = re.sub(r',(\s*[}\]])', r'\1', resp_text)
        data = json.loads(resp_text)

        topic_id = data.get("topic_id", "")
        confidence = float(data.get("confidence", 0.0))
        reasoning = data.get("reasoning", "")
        secondary_tags = data.get("secondary_tags", [])

        # Validate topic_id exists in taxonomy
        valid_ids = _get_topic_id_set()
        if topic_id not in valid_ids:
            print(f"[Classifier] LLM returned invalid topic_id '{topic_id}', falling back to nearest neighbor")
            return _fallback_nearest_neighbor(embedding, existing_nodes)

        # Apply confidence routing
        if confidence >= 0.7:
            print(f"[Classifier] Assigned '{node_title[:50]}' -> {topic_id} (confidence: {confidence:.2f})")
            # Store tags and method in the global _last_classification for the caller
            _store_classification_result(topic_id, 'llm', secondary_tags, confidence, reasoning)
            return topic_id
        elif confidence >= 0.4:
            # Route to Topic Evaluation Parking within the same Domain
            domain_id = _get_domain_for_topic(topic_id)
            parking_id = _find_parking_topic(domain_id, "Topic Evaluation Parking")
            if parking_id:
                print(f"[Classifier] Low confidence ({confidence:.2f}) for '{node_title[:50]}' -> parking: {parking_id}")
                _store_classification_result(parking_id, 'llm', secondary_tags, confidence, reasoning)
                return parking_id
            else:
                # Fallback: use the LLM's best guess anyway
                _store_classification_result(topic_id, 'llm', secondary_tags, confidence, reasoning)
                return topic_id
        else:
            # Route to Domain Evaluation Parking
            domain_id = _get_domain_for_topic(topic_id) if topic_id in valid_ids else None
            parking_id = _find_parking_topic(domain_id, "Domain Evaluation Parking")
            if parking_id:
                print(f"[Classifier] Very low confidence ({confidence:.2f}) for '{node_title[:50]}' -> domain parking: {parking_id}")
                _store_classification_result(parking_id, 'llm', secondary_tags, confidence, reasoning)
                return parking_id
            else:
                _store_classification_result(topic_id, 'llm', secondary_tags, confidence, reasoning)
                return topic_id

    except Exception as ex:
        print(f"[Classifier] Error in LLM classification, falling back to nearest neighbor: {ex}")
        return _fallback_nearest_neighbor(embedding, existing_nodes)


# ---------------------------------------------------------------------------
# Classification result passing (thread-safe via thread-local)
# ---------------------------------------------------------------------------
import threading
_classification_tls = threading.local()


def _store_classification_result(topic_id: str, method: str, tags: list, confidence: float, reasoning: str):
    """Store the last classification result for the caller to retrieve."""
    _classification_tls.last_result = {
        "topic_id": topic_id,
        "classification_method": method,
        "tags": tags or [],
        "confidence": confidence,
        "reasoning": reasoning,
    }


def get_last_classification_result() -> dict | None:
    """Retrieve the last classification result (tags, method, confidence).
    Call this AFTER assign_cluster() to get the secondary metadata.
    """
    return getattr(_classification_tls, 'last_result', None)


# ---------------------------------------------------------------------------
# Fallback: nearest neighbor
# ---------------------------------------------------------------------------

def _fallback_nearest_neighbor(embedding: list[float], existing_nodes: list[dict]) -> str:
    """Cosine similarity fallback when LLM classification fails."""
    nearest_node = None
    max_sim = 0.0
    for n in existing_nodes:
        if n.get("embedding"):
            sim = cosine_similarity(embedding, n["embedding"])
            if sim > max_sim:
                max_sim = sim
                nearest_node = n
    if max_sim > 0.70 and nearest_node and nearest_node.get("cluster_id"):
        topic_id = nearest_node["cluster_id"]
        _store_classification_result(topic_id, 'fallback_nn', [], max_sim, f"Nearest neighbor match (sim={max_sim:.3f})")
        print(f"[Classifier] Fallback NN match: sim={max_sim:.3f} -> {topic_id}")
        return topic_id

    # Last resort: first active L3 topic or any parking lot
    active = get_all_clusters(active_only=True)
    l3s = [c for c in active if c["level"] == 3]
    parking = [c for c in l3s if "Parking" in c.get("name", "") or "HITL" in c.get("name", "")]
    fallback_id = parking[0]["id"] if parking else (l3s[0]["id"] if l3s else "cluster_initial")
    _store_classification_result(fallback_id, 'fallback_nn', [], 0.0, "No good match found")
    return fallback_id


def _find_parking_topic(domain_id: str | None, parking_name: str) -> str | None:
    """Find a specific parking topic within a domain."""
    active = get_all_clusters(active_only=True)
    l2s = [c for c in active if c["level"] == 2]
    l3s = [c for c in active if c["level"] == 3]

    if domain_id:
        # Look for parking topic within this domain's areas
        domain_areas = {a["id"] for a in l2s if a["parent_cluster_id"] == domain_id}
        for t in l3s:
            if t["parent_cluster_id"] in domain_areas and parking_name in t.get("name", ""):
                return t["id"]

    # Fallback: find any parking topic with this name
    for t in l3s:
        if parking_name in t.get("name", ""):
            return t["id"]
    return None


# ---------------------------------------------------------------------------
# Cross-Disciplinary evaluation (runs in 24h batch cycle)
# ---------------------------------------------------------------------------

def evaluate_cross_disciplinary():
    """Check all nodes for cross-disciplinary eligibility and set/clear flags.

    Requirements:
    - >= 1 edge to a node in a DIFFERENT Domain (cross-domain link)
    - AND >= 3 edges to nodes in >= 3 different Areas (cross-area diversity)
    """
    all_nodes = get_all_nodes()
    all_edges = get_all_edges()
    active_clusters = get_all_clusters(active_only=True)

    # Build lookup: node_id -> (topic_id, area_id, domain_id)
    by_id = {c["id"]: c for c in active_clusters}
    node_taxonomy = {}
    for n in all_nodes:
        cid = n.get("cluster_id")
        if not cid or cid not in by_id:
            continue
        topic = by_id[cid]
        area_id = topic.get("parent_cluster_id")
        area = by_id.get(area_id) if area_id else None
        domain_id = area.get("parent_cluster_id") if area else None
        node_taxonomy[n["id"]] = {
            "topic_id": cid,
            "area_id": area_id,
            "domain_id": domain_id,
        }

    # Build adjacency
    adjacency = {}
    for e in all_edges:
        s, t = e["source_id"], e["target_id"]
        adjacency.setdefault(s, set()).add(t)
        adjacency.setdefault(t, set()).add(s)

    flagged = 0
    unflagged = 0

    with batch_transaction() as conn:
        for n in all_nodes:
            nid = n["id"]
            if nid not in node_taxonomy:
                continue

            my_domain = node_taxonomy[nid]["domain_id"]
            my_area = node_taxonomy[nid]["area_id"]
            neighbors = adjacency.get(nid, set())

            cross_domain_count = 0
            cross_areas = set()

            for neighbor_id in neighbors:
                if neighbor_id not in node_taxonomy:
                    continue
                nb = node_taxonomy[neighbor_id]
                if nb["domain_id"] and nb["domain_id"] != my_domain:
                    cross_domain_count += 1
                if nb["area_id"] and nb["area_id"] != my_area:
                    cross_areas.add(nb["area_id"])

            is_cross = cross_domain_count >= 1 and len(cross_areas) >= 3
            if is_cross:
                flagged += 1
            else:
                unflagged += 1

            update_node_cross_disciplinary(nid, is_cross, conn=conn)

    print(f"[CrossDisciplinary] Evaluation complete: {flagged} flagged, {unflagged} not qualifying")
    return {"flagged": flagged, "unflagged": unflagged}


# ---------------------------------------------------------------------------
# Topic splitting (runs in 24h batch cycle)
# ---------------------------------------------------------------------------

def check_and_split_topics(split_threshold: int = 50):
    """Check for overcrowded topics and propose splits using dual-LLM consensus.

    Only fires when threshold is reached. Judge LLM verifies the split.
    """
    topic_counts = get_topic_node_counts()
    overcrowded = [t for t in topic_counts if t["node_count"] >= split_threshold]

    if not overcrowded:
        print(f"[TopicSplit] No topics at threshold ({split_threshold}). Skipping.")
        return []

    splits_performed = []
    for topic in overcrowded:
        topic_id = topic["id"]
        topic_name = topic["name"]
        node_count = topic["node_count"]

        # Skip parking/review topics
        if "Parking" in topic_name or "HITL" in topic_name:
            continue

        print(f"[TopicSplit] Topic '{topic_name}' has {node_count} nodes (threshold: {split_threshold}). Proposing split...")

        # Get all nodes in this topic for context
        nodes = get_nodes_by_cluster(topic_id)
        node_titles = [n.get("title", "Untitled") for n in nodes[:30]]  # Cap for prompt size

        # Step 1: Proposer LLM
        propose_prompt = f"""You are a research taxonomy expert. The following Topic has grown too large ({node_count} nodes) and needs to be split into exactly TWO more specific sub-topics.

CURRENT TOPIC: {topic_name}
SAMPLE NODE TITLES IN THIS TOPIC:
{chr(10).join(f'- {t}' for t in node_titles)}

RULES:
1. Propose exactly 2 new topic names that together cover all content of the original topic.
2. Names must be 2-4 words, professional, and clearly distinct from each other.
3. Every existing node should clearly belong to one of the two new topics.

Return ONLY a raw JSON object:
{{
  "topic_a": {{ "name": "New Topic A Name", "description": "One sentence" }},
  "topic_b": {{ "name": "New Topic B Name", "description": "One sentence" }},
  "reasoning": "Why this split makes sense"
}}"""

        try:
            resp = gemini_generate_sync(propose_prompt, model="gemini-2.5-flash", max_retries=3, base_delay=2.0)
            if not resp:
                continue
            if "```" in resp:
                resp = re.sub(r'^```(?:json)?\s*', '', resp, flags=re.MULTILINE)
                resp = re.sub(r'\s*```$', '', resp, flags=re.MULTILINE)
            proposal = json.loads(resp.strip())
        except Exception as ex:
            print(f"[TopicSplit] Proposer failed for '{topic_name}': {ex}")
            continue

        # Step 2: Judge LLM verifies
        judge_prompt = f"""You are a taxonomy quality judge. Review this proposed topic split:

ORIGINAL TOPIC: {topic_name} ({node_count} nodes)
PROPOSED SPLIT:
  A: {proposal.get('topic_a', {}).get('name', '?')} - {proposal.get('topic_a', {}).get('description', '?')}
  B: {proposal.get('topic_b', {}).get('name', '?')} - {proposal.get('topic_b', {}).get('description', '?')}
REASONING: {proposal.get('reasoning', '?')}

EVALUATE:
1. Are the two topics genuinely distinct (not overlapping)?
2. Do they together cover the full scope of the original topic?
3. Are the names professional and concise?

Return ONLY a raw JSON object:
{{
  "approved": true or false,
  "feedback": "Why approved or rejected",
  "revised_a": {{ "name": "...", "description": "..." }},
  "revised_b": {{ "name": "...", "description": "..." }}
}}"""

        try:
            judge_resp = gemini_generate_sync(judge_prompt, model="gemini-2.5-flash", max_retries=3, base_delay=2.0)
            if not judge_resp:
                continue
            if "```" in judge_resp:
                judge_resp = re.sub(r'^```(?:json)?\s*', '', judge_resp, flags=re.MULTILINE)
                judge_resp = re.sub(r'\s*```$', '', judge_resp, flags=re.MULTILINE)
            judgment = json.loads(judge_resp.strip())
        except Exception as ex:
            print(f"[TopicSplit] Judge failed for '{topic_name}': {ex}")
            continue

        if not judgment.get("approved", False):
            print(f"[TopicSplit] Judge REJECTED split of '{topic_name}': {judgment.get('feedback', '?')}")
            continue

        # Step 3: Execute the split
        revised_a = judgment.get("revised_a", proposal.get("topic_a", {}))
        revised_b = judgment.get("revised_b", proposal.get("topic_b", {}))
        parent_area_id = topic.get("parent_cluster_id")

        # Create two new topics
        id_a = f"topic_{uuid.uuid4().hex[:12]}"
        id_b = f"topic_{uuid.uuid4().hex[:12]}"

        insert_cluster(id_a, revised_a["name"], revised_a.get("description", ""), None,
                        parent_cluster_id=parent_area_id, is_active=1, level=3)
        insert_cluster(id_b, revised_b["name"], revised_b.get("description", ""), None,
                        parent_cluster_id=parent_area_id, is_active=1, level=3)

        # Reclassify nodes into the two new topics
        reclassified = _reclassify_split_nodes(nodes, revised_a["name"], revised_b["name"], id_a, id_b)

        # Retire old topic
        from .db import retire_cluster
        retire_cluster(topic_id)

        print(f"[TopicSplit] Split '{topic_name}' -> '{revised_a['name']}' ({reclassified['a']}), '{revised_b['name']}' ({reclassified['b']})")
        splits_performed.append({
            "original": topic_name,
            "new_a": revised_a["name"],
            "new_b": revised_b["name"],
            "count_a": reclassified["a"],
            "count_b": reclassified["b"],
        })

    return splits_performed


def _reclassify_split_nodes(nodes: list, name_a: str, name_b: str, id_a: str, id_b: str) -> dict:
    """Use LLM to assign each node to one of two new split topics."""
    count_a, count_b = 0, 0

    for node in nodes:
        title = node.get("title", "")
        summary = (node.get("summary") or "")[:200]

        prompt = f"""Classify this into EXACTLY one of two topics:
A: {name_a}
B: {name_b}

Title: {title}
Summary: {summary}

Return ONLY "A" or "B"."""

        try:
            resp = gemini_generate_sync(prompt, model="gemini-2.5-flash", max_retries=2, base_delay=1.0)
            choice = resp.strip().upper()[:1] if resp else "A"
        except Exception:
            choice = "A"  # Default to A on failure

        if choice == "B":
            update_node_cluster(node["id"], id_b)
            count_b += 1
        else:
            update_node_cluster(node["id"], id_a)
            count_a += 1

    return {"a": count_a, "b": count_b}


# ---------------------------------------------------------------------------
# Autonomous domain creation (dual-LLM consensus)
# ---------------------------------------------------------------------------

def propose_new_domain():
    """Check Domain Evaluation Parking for items and propose new domain creation.

    Trigger: Only when items exist in any Domain Evaluation Parking, max once/24h.
    Uses dual-LLM consensus: proposer + judge.
    """
    parking_nodes = get_parking_lot_nodes()
    domain_parking = [n for n in parking_nodes if "Domain Evaluation" in (n.get("cluster_id") or "")]

    if not domain_parking:
        # Also check by cluster name
        active = get_all_clusters(active_only=True)
        domain_parking_ids = {c["id"] for c in active if "Domain Evaluation Parking" in c.get("name", "")}
        domain_parking = [n for n in get_all_nodes() if n.get("cluster_id") in domain_parking_ids]

    if not domain_parking:
        return None

    print(f"[DomainCreation] Found {len(domain_parking)} nodes in Domain Evaluation Parking")

    # Collect titles for context
    titles = [n.get("title", "Untitled") for n in domain_parking[:10]]
    summaries = [(n.get("summary") or "")[:200] for n in domain_parking[:5]]

    existing_taxonomy = _build_taxonomy_tree()
    existing_domains = [d["name"] for d in existing_taxonomy["domains"]]

    # Step 1: Proposer
    propose_prompt = f"""You are a research taxonomy expert. The following nodes could not be classified into any existing domain.

EXISTING DOMAINS: {', '.join(existing_domains)}

UNCLASSIFIABLE NODE TITLES:
{chr(10).join(f'- {t}' for t in titles)}

SUMMARIES:
{chr(10).join(summaries)}

TASK: Determine if these nodes represent a genuinely NEW research domain that doesn't fit any existing domain.

If YES, propose a complete taxonomy structure:
{{
  "new_domain": true,
  "domain_name": "2-3 word domain name",
  "domain_description": "One sentence",
  "areas": [
    {{
      "name": "Area Name",
      "description": "One sentence",
      "topics": [
        {{ "name": "Topic Name", "description": "One sentence" }}
      ]
    }}
  ]
}}

If NO (they can fit existing domains with better classification), return:
{{
  "new_domain": false,
  "suggested_reclassifications": [
    {{ "title": "node title", "suggested_domain": "existing domain name" }}
  ]
}}

Return ONLY raw JSON."""

    try:
        resp = gemini_generate_sync(propose_prompt, model="gemini-2.5-flash", max_retries=3, base_delay=2.0)
        if not resp:
            return None
        if "```" in resp:
            resp = re.sub(r'^```(?:json)?\s*', '', resp, flags=re.MULTILINE)
            resp = re.sub(r'\s*```$', '', resp, flags=re.MULTILINE)
        proposal = json.loads(resp.strip())
    except Exception as ex:
        print(f"[DomainCreation] Proposer failed: {ex}")
        return None

    if not proposal.get("new_domain", False):
        print(f"[DomainCreation] Proposer says no new domain needed. Reclassification suggested.")
        return {"action": "reclassify", "suggestions": proposal.get("suggested_reclassifications", [])}

    # Step 2: Judge
    judge_prompt = f"""You are a taxonomy quality judge. Review this proposed NEW research domain:

EXISTING DOMAINS: {', '.join(existing_domains)}

PROPOSED NEW DOMAIN: {proposal.get('domain_name', '?')}
Description: {proposal.get('domain_description', '?')}
Areas: {len(proposal.get('areas', []))}
Total Topics: {sum(len(a.get('topics', [])) for a in proposal.get('areas', []))}

EVALUATE:
1. Is this genuinely distinct from existing domains?
2. Is the structure complete (8-12 areas, 8-12 topics per area)?
3. Are names professional and consistent?
4. Does it include an "Emerging & Other" area with parking topics?

Return ONLY raw JSON:
{{
  "approved": true or false,
  "feedback": "Explanation",
  "revised_taxonomy": {{ ... }} // Only if approved, with corrections
}}"""

    try:
        judge_resp = gemini_generate_sync(judge_prompt, model="gemini-2.5-flash", max_retries=3, base_delay=2.0)
        if not judge_resp:
            return None
        if "```" in judge_resp:
            judge_resp = re.sub(r'^```(?:json)?\s*', '', judge_resp, flags=re.MULTILINE)
            judge_resp = re.sub(r'\s*```$', '', judge_resp, flags=re.MULTILINE)
        judgment = json.loads(judge_resp.strip())
    except Exception as ex:
        print(f"[DomainCreation] Judge failed: {ex}")
        return None

    if not judgment.get("approved", False):
        print(f"[DomainCreation] Judge REJECTED new domain: {judgment.get('feedback', '?')}")
        return {"action": "rejected", "feedback": judgment.get("feedback", "")}

    # Step 3: Create the domain
    revised = judgment.get("revised_taxonomy", proposal)
    domain_name = revised.get("domain_name", proposal.get("domain_name"))
    domain_desc = revised.get("domain_description", proposal.get("domain_description", ""))
    domain_slug = domain_name.lower().replace(" ", "_").replace("&", "and")
    domain_id = f"domain_{domain_slug}"

    with batch_transaction() as conn:
        insert_cluster(domain_id, domain_name, domain_desc, None,
                        parent_cluster_id=None, is_active=1, level=1, conn=conn)

        areas = revised.get("areas", proposal.get("areas", []))
        for area in areas:
            area_slug = area["name"].lower().replace(" ", "_").replace("&", "and").replace(",", "")[:40]
            area_id = f"cat_{domain_slug}_{area_slug}"
            insert_cluster(area_id, area["name"], area.get("description", ""), None,
                            parent_cluster_id=domain_id, is_active=1, level=2, conn=conn)

            for topic in area.get("topics", []):
                topic_slug = topic["name"].lower().replace(" ", "_").replace("&", "and").replace(",", "")[:40]
                topic_id = f"topic_{domain_slug}_{topic_slug}"
                insert_cluster(topic_id, topic["name"], topic.get("description", ""), None,
                                parent_cluster_id=area_id, is_active=1, level=3, conn=conn)

    print(f"[DomainCreation] Created new domain '{domain_name}' with {len(areas)} areas")
    return {"action": "created", "domain": domain_name, "domain_id": domain_id}


# ---------------------------------------------------------------------------
# Batch processing helpers (for 24h cycle)
# ---------------------------------------------------------------------------

def reclassify_fallback_nodes():
    """Re-attempt LLM classification on nodes that fell back to nearest-neighbor."""
    fallback_nodes = get_nodes_by_classification_method("fallback_nn")
    if not fallback_nodes:
        print("[Reclassify] No fallback_nn nodes to reclassify.")
        return 0

    all_nodes = get_all_nodes()
    reclassified = 0

    for node in fallback_nodes:
        embedding = node.get("embedding")
        if not embedding:
            continue

        new_cluster_id = assign_cluster(
            node.get("title", ""),
            node.get("summary", ""),
            embedding,
            all_nodes
        )

        result = get_last_classification_result()
        method = result.get("classification_method", "llm") if result else "llm"
        tags = result.get("tags", []) if result else []

        if method == "llm":  # Successfully reclassified by LLM
            update_node_cluster(node["id"], new_cluster_id, classification_method="llm", tags=tags)
            reclassified += 1
            print(f"[Reclassify] '{node.get('title', '')[:40]}' reclassified: {new_cluster_id}")

    print(f"[Reclassify] {reclassified}/{len(fallback_nodes)} fallback nodes reclassified by LLM")
    return reclassified


def evaluate_parking_lots():
    """Re-attempt classification on parked nodes. Only call when parking has items."""
    parking_nodes = get_parking_lot_nodes()
    if not parking_nodes:
        print("[ParkingEval] No parked nodes. Skipping.")
        return 0

    all_nodes = get_all_nodes()
    resolved = 0

    for node in parking_nodes:
        embedding = node.get("embedding")
        if not embedding:
            continue

        new_cluster_id = assign_cluster(
            node.get("title", ""),
            node.get("summary", ""),
            embedding,
            all_nodes
        )

        result = get_last_classification_result()
        confidence = result.get("confidence", 0.0) if result else 0.0
        tags = result.get("tags", []) if result else []

        # Only resolve if confidence improved above parking threshold
        if confidence >= 0.7:
            update_node_cluster(node["id"], new_cluster_id, classification_method="llm", tags=tags)
            resolved += 1

    print(f"[ParkingEval] {resolved}/{len(parking_nodes)} parked nodes resolved")
    return resolved
