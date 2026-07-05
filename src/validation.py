import urllib.parse

from google import genai

from .db import get_reputable_domain, insert_reputable_domain
from .agent import evaluate_publisher_authority


REPUTABLE_SEED_DOMAINS = {
    "cloudsecurityalliance.org": {"artifact": 0.65, "blog": 0.35, "general": 0.50},
    "openai.com": {"artifact": 0.75, "blog": 0.40, "general": 0.55},
    "deepmind.google": {"artifact": 0.75, "blog": 0.45, "general": 0.60},
    "deepmind.com": {"artifact": 0.75, "blog": 0.45, "general": 0.60},
    "anthropic.com": {"artifact": 0.75, "blog": 0.40, "general": 0.55},
    "ai.meta.com": {"artifact": 0.70, "blog": 0.40, "general": 0.50},
    "research.google": {"artifact": 0.75, "blog": 0.45, "general": 0.60},
    "microsoft.com": {"artifact": 0.65, "blog": 0.35, "general": 0.45},
    "arxiv.org": {"artifact": 0.80, "blog": 0.80, "general": 0.80},
    "github.com": {"artifact": 0.50, "blog": 0.50, "general": 0.50},
    "ieee.org": {"artifact": 0.80, "blog": 0.45, "general": 0.75},
    "acm.org": {"artifact": 0.80, "blog": 0.45, "general": 0.75},
    "nature.com": {"artifact": 0.85, "blog": 0.50, "general": 0.80},
    "science.org": {"artifact": 0.85, "blog": 0.50, "general": 0.80},
    "mit.edu": {"artifact": 0.75, "blog": 0.40, "general": 0.60},
    "stanford.edu": {"artifact": 0.75, "blog": 0.40, "general": 0.60},
    "berkeley.edu": {"artifact": 0.75, "blog": 0.40, "general": 0.60},
    "cmu.edu": {"artifact": 0.75, "blog": 0.40, "general": 0.60},
    "ox.ac.uk": {"artifact": 0.75, "blog": 0.40, "general": 0.60},
    "cam.ac.uk": {"artifact": 0.75, "blog": 0.40, "general": 0.60}
}


def get_publication_path_type(url: str) -> str:
    """Classifies URL path as 'artifact' (whitepaper/peer-reviewed paper), 'blog' (opinion/commentary), or 'general'."""
    if not url:
        return "general"
    path = urllib.parse.urlparse(url).path.lower()
    
    blog_keywords = ["/blog/", "/blogs/", "/post/", "/posts/", "/article/", "/articles/", "/opinion/", "/opinions/", "/news/"]
    if any(k in path for k in blog_keywords):
        return "blog"

    artifact_keywords = ["/artifact/", "/artifacts/", "/paper/", "/papers/", "/pdf/", "/publication/", "/publications/", "/whitepaper/", "/whitepapers/", "/doc/", "/docs/", "/research/"]
    if any(k in path for k in artifact_keywords):
        return "artifact"

    return "general"


async def get_smart_validation_score(url: str, title: str = "", summary: str = "", source_type: str = "web") -> float:
    """
    Computes validation score using seed domains (differentiating blogs vs artifacts),
    SQLite reputable_domains cache, or dynamic LLM publisher authority evaluation.
    """
    if source_type == "arxiv":
        return 0.80
    if source_type == "github":
        return 0.50

    if not url:
        return 0.10

    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower().split(':')[0]
    if netloc.startswith("www."):
        netloc = netloc[4:]

    if not netloc:
        return 0.10

    path_type = get_publication_path_type(url)

    # 1. Check Seed List with path differentiation (blog vs artifact)
    for seed_domain, seed_cfg in REPUTABLE_SEED_DOMAINS.items():
        if netloc == seed_domain or netloc.endswith("." + seed_domain):
            score = seed_cfg.get(path_type, seed_cfg.get("general", 0.50))
            print(f"[Smart Validation] Seed list match for '{netloc}' ({path_type}): {score}")
            return score

    # 2. Check SQLite Cache (apply 0.75x multiplier if path is blog)
    cached_score = get_reputable_domain(netloc)
    if cached_score is not None:
        final_score = cached_score * 0.70 if path_type == "blog" else cached_score
        print(f"[Smart Validation] SQLite cache match for '{netloc}' ({path_type}): {final_score:.2f}")
        return max(0.10, min(1.0, final_score))

    # Check root domain in SQLite cache
    parts = netloc.split(".")
    if len(parts) > 2:
        root_domain = ".".join(parts[-2:])
        root_cached = get_reputable_domain(root_domain)
        if root_cached is not None:
            final_score = root_cached * 0.70 if path_type == "blog" else root_cached
            print(f"[Smart Validation] SQLite cache root match for '{root_domain}' ({path_type}): {final_score:.2f}")
            return max(0.10, min(1.0, final_score))

    # 3. Dynamic LLM publisher evaluation with path_type context
    print(f"[Smart Validation] Domain '{netloc}' unknown. Evaluating publisher authority via Gemini for type '{path_type}'...")
    val_score = await evaluate_publisher_authority(netloc, title, summary, path_type)
    if val_score >= 0.40:
        insert_reputable_domain(netloc, val_score)
        print(f"[Smart Validation] Auto-learned & cached reputable domain '{netloc}' with score {val_score}")
    return val_score


def is_duplicate_match(title1: str, summary1: str, title2: str, summary2: str, embedding1, embedding2) -> bool:
    """Multi-stage duplicate detection: exact title match, embedding similarity, LLM reranking."""
    from .scoring import cosine_similarity
    
    # 1. Exact title check (case-insensitive, normalized spacing)
    t1_clean = " ".join(title1.strip().lower().split())
    t2_clean = " ".join(title2.strip().lower().split())
    if t1_clean == t2_clean:
        print(f"[Duplicate Check] Exact title match found: '{title1}'")
        return True
        
    # 2. Embedding similarity check
    sim = cosine_similarity(embedding1, embedding2)
    print(f"[Duplicate Check] Similarity for '{title2}': {sim:.3f}")
    if sim >= 0.93:
        print("[Duplicate Check] High similarity duplicate detected (>= 0.93).")
        return True
    elif 0.88 <= sim < 0.93:
        print(f"[Duplicate Check] Staggered threshold check (0.88 - 0.93). Reranking with LLM...")
        try:
            client = genai.Client()
            prompt = f"""
            You are a prior-art validation agent.
            Determine if the following two entries represent the EXACT same publication, article, blog post, or repository.
            Even if the summaries are phrased slightly differently, if they are describing the same work, classify them as identical.
            
            Entry A:
            Title: {title1}
            Summary: {summary1}
            
            Entry B:
            Title: {title2}
            Summary: {summary2}
            
            Are these the exact same publication/work?
            Return ONLY 'yes' or 'no' in lowercase.
            """
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            ans = response.text.strip().lower()
            is_dup = "yes" in ans
            print(f"[Duplicate Check] LLM Reranker answer: {ans} -> Duplicate: {is_dup}")
            return is_dup
        except Exception as ex:
            print(f"[Duplicate Check] LLM Reranking failed: {ex}")
            return False
            
    return False
