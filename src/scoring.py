import os
import math
from google import genai
from google.genai import errors

# Monkeypatch genai.Client to always use retry config for robustness against transient 429s
try:
    original_client_init = genai.Client.__init__
    def patched_client_init(self, *args, **kwargs):
        if 'http_options' not in kwargs or kwargs['http_options'] is None:
            kwargs['http_options'] = {
                'retry_options': {
                    'attempts': 6,
                    'initial_delay': 2.0,
                    'max_delay': 60.0
                }
            }
        return original_client_init(self, *args, **kwargs)
    genai.Client.__init__ = patched_client_init
    print("[ConceptRadar] Applied genai.Client scoring retry monkeypatches: SUCCESS.")
except Exception as patch_ex:
    print(f"Failed to patch genai.Client in scoring: {patch_ex}")

# Initialize GenAI Client
client = None

def get_client():
    global client
    if client is None:
        client = genai.Client()
    return client

def get_embedding(text: str) -> list[float]:
    """Generates a 3072-dimensional vector embedding using gemini-embedding-2."""
    if not text:
        return [0.0] * 3072
    try:
        c = get_client()
        # Truncate text if it is extremely long to prevent API errors
        truncated_text = text[:10000]
        response = c.models.embed_content(
            model="gemini-embedding-2",
            contents=truncated_text
        )
        if response.embeddings:
            return response.embeddings[0].values
        return [0.0] * 3072
    except Exception as e:
        print(f"Error generating embedding: {e}")
        # Return fallback zero vector
        return [0.0] * 3072

def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Computes cosine similarity between two float vectors, fallback to pure python if numpy fails."""
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    try:
        import numpy as np
        arr1 = np.array(v1)
        arr2 = np.array(v2)
        dot = np.dot(arr1, arr2)
        norm1 = np.linalg.norm(arr1)
        norm2 = np.linalg.norm(arr2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(dot / (norm1 * norm2))
    except Exception:
        # Pure Python fallback
        dot_product = sum(x * y for x, y in zip(v1, v2))
        mag1 = math.sqrt(sum(x ** 2 for x in v1))
        mag2 = math.sqrt(sum(x ** 2 for x in v2))
        if mag1 == 0 or mag2 == 0:
            return 0.0
        return dot_product / (mag1 * mag2)

def calculate_novelty(embedding: list[float], existing_ref_embeddings: list[list[float]]) -> float:
    """Novelty = Calibrated scaling mapping similarity [0.70, 0.95] to novelty [1.0, 0.0]."""
    if not existing_ref_embeddings:
        return 1.0  # Totally novel if there are no reference items in database yet
    
    max_sim = 0.0
    for ref_emb in existing_ref_embeddings:
        sim = cosine_similarity(embedding, ref_emb)
        if sim > max_sim:
            max_sim = sim
            
    # Calibrated novelty: maps similarity [0.70, 0.95] to novelty [1.0, 0.0]
    # This stretches the compressed cosine similarity scores of text-embedding-004 over the full spectrum.
    sim_min = 0.70
    sim_max = 0.95
    if max_sim <= sim_min:
        return 1.0
    if max_sim >= sim_max:
        return 0.0
    novelty = (sim_max - max_sim) / (sim_max - sim_min)
    return max(0.0, min(1.0, novelty))

def calculate_validation(source_type: str, citations: int = 0, is_reproduced: bool = False) -> float:
    """Validation Score: based on source authority and verification flags."""
    base_scores = {
        "arxiv": 0.8,
        "github": 0.5,
        "youtube": 0.2,
        "medium": 0.2,
        "reddit": 0.2,
        "hacker_news": 0.2,
        "idea": 0.1  # Raw user-submitted idea
    }
    score = base_scores.get(source_type.lower(), 0.1)
    
    # Validation boosts for papers with citations
    if source_type.lower() == "arxiv":
        score += min(0.15, citations * 0.01)
    
    # Validation boost for code with reproduction/implementation evidence
    if source_type.lower() == "github" and is_reproduced:
        score += 0.2
        
    return min(1.0, score)

def calculate_momentum(source_type: str, stars: int = 0, forks: int = 0, 
                       views: int = 0, upvotes: int = 0, cluster_size: int = 0,
                       citations: int = 0) -> float:
    """Momentum Score: based on growth/engagement metrics and the size of the cluster."""
    score = 0.0
    
    if source_type.lower() == "github":
        # Logarithmic scale for stars and forks
        activity = stars + (forks * 3)
        if activity > 0:
            score = min(0.8, math.log(activity + 1) / 10.0)
    elif source_type.lower() == "youtube":
        if views > 0:
            score = min(0.7, math.log(views + 1) / 15.0)
    elif source_type.lower() in ["reddit", "hacker_news"]:
        if upvotes > 0:
            score = min(0.6, math.log(upvotes + 1) / 8.0)
    elif source_type.lower() == "arxiv":
        score = 0.2
        if citations > 0:
            score = max(0.2, min(0.8, math.log(citations + 1) / 5.0))
    else:
        # Default baseline momentum for papers or ideas
        score = 0.2
        
    # Boost momentum according to cluster size (larger clusters = trending topics)
    if cluster_size > 0:
        cluster_boost = min(0.5, math.log(cluster_size + 1) / 9.0)
        score += cluster_boost
        
    return min(1.0, score)


def calculate_edge_entropy(node_id: str, edges: list[dict], node_topic_map: dict, cluster_map: dict) -> float:
    """Calculate Shannon entropy over the topic/domain distribution of a node's edges.
    
    Measures the diversity of a node's connections across different topics.
    Higher entropy = more diverse connections = higher structural novelty.
    Returns a value in [0.0, 1.0].
    """
    connected = []
    for e in edges:
        if e['source_id'] == node_id:
            connected.append(e['target_id'])
        elif e['target_id'] == node_id:
            connected.append(e['source_id'])

    if len(connected) < 2:
        return 0.0

    # Count topic distribution of connected nodes
    topic_counts = {}
    for cid in connected:
        topic_id = node_topic_map.get(cid)
        if topic_id:
            topic_counts[topic_id] = topic_counts.get(topic_id, 0) + 1

    total = sum(topic_counts.values())
    if total == 0 or len(topic_counts) <= 1:
        return 0.0

    # Shannon entropy
    entropy = 0.0
    for count in topic_counts.values():
        p = count / total
        if p > 0:
            entropy -= p * math.log2(p)

    max_entropy = math.log2(len(topic_counts))
    if max_entropy == 0:
        return 0.0

    normalized = entropy / max_entropy  # [0, 1]

    # Breadth bonus: reward having more unique topics (caps at 10)
    breadth_bonus = min(1.0, math.log2(len(topic_counts)) / math.log2(10))

    # Combined: 70% normalized entropy + 30% breadth
    combined = 0.7 * normalized + 0.3 * breadth_bonus
    return round(max(0.0, min(1.0, combined)), 3)


def calculate_structural_surprise(node_id: str, edges: list[dict], node_topic_map: dict) -> float:
    """Calculate structural surprise: mean(-log2(P(target_topic | source_topic))) across all edges.
    
    Measures how RARE the specific topic-to-topic edge types are globally.
    A node connecting AI→Physics has high surprise (rare edge type).
    A node connecting AI→AI has low surprise (common edge type).
    
    Returns raw surprise value (unbounded, typically 0-6).
    """
    # Build global edge-type counts: source_topic -> {target_topic: count}
    topic_edge_counts = {}
    topic_edge_totals = {}
    for e in edges:
        src_topic = node_topic_map.get(e['source_id'])
        tgt_topic = node_topic_map.get(e['target_id'])
        if not src_topic or not tgt_topic:
            continue
        # Count both directions
        for s, t in [(src_topic, tgt_topic), (tgt_topic, src_topic)]:
            if s not in topic_edge_counts:
                topic_edge_counts[s] = {}
            topic_edge_counts[s][t] = topic_edge_counts[s].get(t, 0) + 1
            topic_edge_totals[s] = topic_edge_totals.get(s, 0) + 1

    # Get this node's edges and compute surprise for each
    node_topic = node_topic_map.get(node_id)
    if not node_topic:
        return 0.0

    connected_topics = []
    for e in edges:
        if e['source_id'] == node_id:
            t = node_topic_map.get(e['target_id'])
            if t:
                connected_topics.append(t)
        elif e['target_id'] == node_id:
            t = node_topic_map.get(e['source_id'])
            if t:
                connected_topics.append(t)

    if not connected_topics:
        return 0.0

    surprises = []
    src_counts = topic_edge_counts.get(node_topic, {})
    src_total = topic_edge_totals.get(node_topic, 0)
    if src_total == 0:
        return 0.0

    for tgt_topic in connected_topics:
        count = src_counts.get(tgt_topic, 0)
        if count > 0:
            p = count / src_total
            surprises.append(-math.log2(p))
        else:
            surprises.append(6.0)  # Cap for unseen edge types

    return round(sum(surprises) / len(surprises), 3) if surprises else 0.0


def get_diverse_neighbors(node: dict, all_nodes: list[dict], cluster_map: dict, n_same: int = 3, n_diff: int = 2) -> list[dict]:
    """Get diverse neighbors: n_same from same topic + n_diff from different topics.
    
    This prevents the 'echo chamber' problem where all neighbors are from
    the same research area, giving the LLM no cross-topic reference frame.
    """
    embedding = node.get('embedding')
    if not embedding:
        return []

    node_topic = node.get('cluster_id', '')

    same_topic = []
    diff_topic = []

    for n in all_nodes:
        if n['id'] == node.get('id') or not n.get('embedding'):
            continue
        sim = cosine_similarity(embedding, n['embedding'])
        entry = (sim, n)
        if n.get('cluster_id') == node_topic:
            same_topic.append(entry)
        else:
            diff_topic.append(entry)

    same_topic.sort(key=lambda x: x[0], reverse=True)
    diff_topic.sort(key=lambda x: x[0], reverse=True)

    neighbors = []
    neighbors.extend([n for _, n in same_topic[:n_same]])
    neighbors.extend([n for _, n in diff_topic[:n_diff]])

    return neighbors
