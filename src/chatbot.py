"""
ConceptRadar Chatbot Agent — Read-only research assistant using Google ADK Skills.

Provides 3 skills (graph_explorer, concept_analyzer, concept_comparator)
and 3 function tools (search_concepts, get_concept_details, get_domain_overview).

Privacy: No temporal data exposed. No topic-level breakdowns. Defense in depth.
"""
import os
import sys
import json
import time
import pathlib
import asyncio

from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import InMemoryRunner
from google.adk.skills import load_skill_from_dir
from google.adk.tools.skill_toolset import SkillToolset
from google import genai

from .db import get_all_nodes, get_all_clusters, get_all_edges, get_node
from .scoring import get_embedding, cosine_similarity

# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------
_sessions: dict[str, tuple[InMemoryRunner, float]] = {}
MAX_SESSION_AGE = 1800  # 30 minutes


def _cleanup_stale_sessions():
    """Remove sessions older than MAX_SESSION_AGE."""
    now = time.time()
    stale = [sid for sid, (_, ts) in _sessions.items() if now - ts > MAX_SESSION_AGE]
    for sid in stale:
        try:
            runner, _ = _sessions.pop(sid)
            # InMemoryRunner doesn't need explicit close for non-MCP usage
        except Exception:
            pass
    if stale:
        print(f"[Chatbot] Cleaned up {len(stale)} stale sessions.")


# ---------------------------------------------------------------------------
# Read-only function tools (what the agent can call)
# ---------------------------------------------------------------------------

def search_concepts(query: str, sort_by: str = "relevance") -> str:
    """Search for concepts in the ConceptRadar knowledge graph by keyword.
    Returns the top 5 semantically matching papers with their scores and taxonomy.
    Use this when the user asks to find papers about a topic.

    Args:
        query: The search query (topic, keyword, or domain name).
        sort_by: How to sort results. Options: "relevance" (default, by semantic similarity),
                 "novelty" (by novelty score — use when user asks what's new/innovative/cutting-edge).

    Returns:
        A formatted string with the top 5 matching concepts.
    """
    nodes = get_all_nodes()
    clusters = get_all_clusters()
    cluster_map = {c['id']: c for c in clusters}

    try:
        embedding = get_embedding(query)
    except Exception as e:
        return f"Error generating search embedding: {e}"

    # Calculate reach on the fly (taxonomic diversity of connections)
    edges = get_all_edges()
    adjacency = {}
    for e in edges:
        adjacency.setdefault(e['source_id'], []).append(e['target_id'])
        adjacency.setdefault(e['target_id'], []).append(e['source_id'])

    node_taxonomy = {}
    for n in nodes:
        cid = n.get('cluster_id', '')
        l3 = cid
        l2 = cluster_map.get(cid, {}).get('parent_cluster_id')
        l1 = cluster_map.get(l2 or '', {}).get('parent_cluster_id') if l2 else None
        node_taxonomy[n['id']] = (l3, l2, l1)

    import math
    def calc_reach(nid):
        neighbors = adjacency.get(nid, [])
        if not neighbors:
            return 0.0
        total_w = 0.0
        l3, l2, l1 = node_taxonomy.get(nid, (None, None, None))
        for nb in neighbors:
            n_l3, n_l2, n_l1 = node_taxonomy.get(nb, (None, None, None))
            if l1 != n_l1:
                total_w += 1.0
            elif l2 != n_l2:
                total_w += 0.6
            elif l3 != n_l3:
                total_w += 0.3
            else:
                total_w += 0.1
        raw = total_w / max(len(neighbors), 1)
        count_factor = math.sqrt(min(len(neighbors), 20) / 20)
        return round(min(1.0, raw * count_factor), 2)

    # Calculate similarity to all nodes, with domain/category boost
    query_lower = query.lower()
    scored = []
    for n in nodes:
        if not n.get('embedding'):
            continue
        sim = cosine_similarity(embedding, n['embedding'])
        # Resolve taxonomy (domain + category only, no topics)
        topic = cluster_map.get(n.get('cluster_id', ''), {})
        area = cluster_map.get(topic.get('parent_cluster_id', ''), {})
        domain = cluster_map.get(area.get('parent_cluster_id', ''), {})
        domain_name = domain.get('name', 'Unknown')
        category_name = area.get('name', 'Unknown')

        # Boost papers whose domain or category matches the query text
        boost = 0.0
        if domain_name.lower() in query_lower or query_lower in domain_name.lower():
            boost = 0.15
        elif category_name.lower() in query_lower or query_lower in category_name.lower():
            boost = 0.10

        scored.append({
            'title': n['title'],
            'url': n.get('url', ''),
            'source_type': n.get('source_type', ''),
            'summary': (n.get('summary', '') or '')[:200],
            'novelty': n.get('novelty_score', 0),
            'validation': n.get('validation_score', 0),
            'momentum': n.get('momentum_score', 0),
            'reach': calc_reach(n['id']),
            'domain': domain_name,
            'category': category_name,
            'xd': 'Yes' if n.get('is_cross_disciplinary') else 'No',
            'similarity': round(sim, 3),
            'rank_score': round(sim + boost, 3),
        })

    # First filter by relevance (minimum threshold), then sort by chosen metric
    scored.sort(key=lambda x: x['rank_score'], reverse=True)

    if sort_by == "novelty":
        # Take top 20 relevant, then sort by novelty to get the most novel within relevant results
        candidates = scored[:20]
        candidates.sort(key=lambda x: x['novelty'], reverse=True)
        top = candidates[:5]
    else:
        top = scored[:5]

    if not top:
        return f"No concepts found in the database matching '{query}'."

    # Count domain matches vs. cross-domain results for transparent explanation
    direct_count = sum(1 for c in top
                       if query_lower in c['domain'].lower()
                       or query_lower in c['category'].lower()
                       or c['domain'].lower() in query_lower
                       or c['category'].lower() in query_lower)
    cross_domain_count = len(top) - direct_count

    lines = []
    if cross_domain_count == 0:
        lines.append(f"Found {len(top)} concepts in '{query}':")
    elif direct_count == 0:
        lines.append(f"No concepts directly classified under '{query}'. Showing the {len(top)} semantically closest concepts in the database:")
    else:
        lines.append(f"Found {direct_count} concept{'s' if direct_count > 1 else ''} in '{query}'. Showing {cross_domain_count} additional semantically related concept{'s' if cross_domain_count > 1 else ''} from other domains to complete the overview:")



    for i, c in enumerate(top, 1):
        src_tag = f" ({c['source_type']})" if c.get('source_type') else ''
        if c['url']:
            lines.append(f"{i}. **[{c['title']}]({c['url']})**{src_tag}")
        else:
            lines.append(f"{i}. **{c['title']}**{src_tag}")
        lines.append(f"   - Novelty: {c['novelty']:.2f} | Validation: {c['validation']:.2f} | Momentum: {c['momentum']:.2f} | Reach: {c['reach']:.2f}")
        lines.append(f"   - Domain: {c['domain']} | Category: {c['category']}")
        lines.append(f"   - Cross-disciplinary: {c['xd']}")
        lines.append(f"   - Relevance: {c['similarity']:.1%}")
        if c['summary']:
            lines.append(f"   - Summary: {c['summary']}")
        lines.append("")

    return "\n".join(lines)


def get_concept_details(title: str) -> str:
    """Get detailed information about a specific concept by its title.
    Returns all scores, novelty component breakdown, edges, and taxonomy.
    Use this when the user asks about a specific paper or concept.

    Args:
        title: The title (or partial title) of the concept to look up.

    Returns:
        A formatted string with full concept details.
    """
    nodes = get_all_nodes()
    clusters = get_all_clusters()
    edges = get_all_edges()
    cluster_map = {c['id']: c for c in clusters}

    # Find by title (case-insensitive partial match)
    title_lower = title.lower()
    matches = [n for n in nodes if title_lower in n['title'].lower()]

    if not matches:
        return f"No concept found matching '{title}'. Try using the search_concepts tool to find it first."

    n = matches[0]  # Best match

    # Resolve taxonomy (domain + category only)
    topic_cluster = cluster_map.get(n.get('cluster_id', ''), {})
    area = cluster_map.get(topic_cluster.get('parent_cluster_id', ''), {})
    domain = cluster_map.get(area.get('parent_cluster_id', ''), {})

    # Find edges for this node
    node_edges = [e for e in edges if e['source_id'] == n['id'] or e['target_id'] == n['id']]
    node_map = {nn['id']: nn['title'] for nn in nodes}

    edge_descriptions = []
    for e in node_edges[:8]:  # Limit to 8 edges
        other_id = e['target_id'] if e['source_id'] == n['id'] else e['source_id']
        other_title = node_map.get(other_id, 'Unknown')
        rel = e.get('relationship_type', 'related')
        edge_descriptions.append(f"  - [{rel}] → {other_title}")

    url = n.get('url', '')
    title_line = f"## [{n['title']}]({url})\n" if url else f"## {n['title']}\n"
    lines = [
        title_line,
        f"**Summary:** {n.get('summary', 'No summary available.')}\n",
        f"### Scores",
        f"- **Novelty:** {n.get('novelty_score', 0):.2f}",
        f"- **Validation:** {n.get('validation_score', 0):.2f}",
        f"- **Momentum:** {n.get('momentum_score', 0):.2f}",
        f"",
        f"### Novelty Breakdown (3 Components)",
        f"- **LLM Information Gain (raw):** {n.get('llm_novelty_raw', 0):.2f}",
        f"- **Shannon Entropy (raw):** {n.get('entropy_score', 0):.2f}",
        f"- **Structural Surprise (raw):** {n.get('structural_surprise', 0):.2f}",
        f"",
        f"### Taxonomy",
        f"- **Domain:** {domain.get('name', 'Unknown')}",
        f"- **Category:** {area.get('name', 'Unknown')}",
        f"- **Cross-disciplinary:** {'Yes' if n.get('is_cross_disciplinary') else 'No'}",
        f"- **Document type:** {n.get('document_type', 'Unknown')}",
        f"- **Source:** {n.get('source_type', 'Unknown')}",
        f"",
    ]

    if edge_descriptions:
        lines.append(f"### Connections ({len(node_edges)} total)")
        lines.extend(edge_descriptions)
    else:
        lines.append("### Connections\nNo connections found.")

    return "\n".join(lines)


def get_domain_overview() -> str:
    """Get an overview of all domains and categories in the ConceptRadar knowledge graph.
    Returns domain names, category names, paper counts, and average scores.
    Use this when the user asks about the overall landscape or wants to browse domains.

    Returns:
        A formatted string with domain and category statistics.
    """
    nodes = get_all_nodes()
    clusters = get_all_clusters()
    cluster_map = {c['id']: c for c in clusters}

    # Build taxonomy tree
    domains = [c for c in clusters if c.get('level') == 0]
    areas = [c for c in clusters if c.get('level') == 1]

    result_lines = [f"## ConceptRadar Landscape Overview\n"]
    result_lines.append(f"**Total concepts:** {len(nodes)}\n")

    for domain in sorted(domains, key=lambda d: d.get('name', '')):
        # Find areas in this domain
        domain_areas = [a for a in areas if a.get('parent_cluster_id') == domain['id']]

        # Count papers in domain
        domain_node_count = 0
        domain_novelty_sum = 0
        domain_validation_sum = 0

        area_lines = []
        for area in sorted(domain_areas, key=lambda a: a.get('name', '')):
            # Find topics in area, then nodes in those topics
            area_topics = [c for c in clusters if c.get('parent_cluster_id') == area['id'] and c.get('level') == 2]
            area_topic_ids = {t['id'] for t in area_topics}
            area_nodes = [n for n in nodes if n.get('cluster_id') in area_topic_ids]

            count = len(area_nodes)
            if count > 0:
                avg_nov = sum(n.get('novelty_score', 0) for n in area_nodes) / count
                avg_val = sum(n.get('validation_score', 0) for n in area_nodes) / count
                area_lines.append(f"  - **{area['name']}**: {count} papers (avg novelty: {avg_nov:.2f}, avg validation: {avg_val:.2f})")
                domain_node_count += count
                domain_novelty_sum += sum(n.get('novelty_score', 0) for n in area_nodes)
                domain_validation_sum += sum(n.get('validation_score', 0) for n in area_nodes)

        if domain_node_count > 0:
            avg_n = domain_novelty_sum / domain_node_count
            avg_v = domain_validation_sum / domain_node_count
            result_lines.append(f"### {domain['name']} ({domain_node_count} papers)")
            result_lines.append(f"Average novelty: {avg_n:.2f} | Average validation: {avg_v:.2f}\n")
            result_lines.extend(area_lines)
            result_lines.append("")

    return "\n".join(result_lines)



# ---------------------------------------------------------------------------
# Agent + SkillToolset setup
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """You are the ConceptRadar Research Assistant — a helpful, knowledgeable AI that helps users explore the ConceptRadar knowledge graph.

ConceptRadar is an AI research discovery platform that maps concepts on a 2D radar:
- X-axis: Novelty (how unique is the contribution)
- Y-axis: Validation (how well-verified/peer-reviewed)
- Circle size: Momentum (engagement, stars, citations)
- Cross-disciplinary badge: concepts bridging multiple research domains

You have 3 skills and 3 function tools:
- search_concepts — find papers by topic (includes summary excerpts)
- get_concept_details — get scores, taxonomy, edges, and full summary for a specific paper
- get_domain_overview — browse all domains and categories

RESPONSE FORMATTING RULES (ALWAYS FOLLOW):
- Tool results contain paper titles formatted as markdown links like [Title](URL). You MUST preserve this exact format in your response. Do NOT separate the URL into a different line. The title itself must be the clickable link.
- ALWAYS preserve the match quality explanation from tool results. When showing search results, the tool provides context about whether results are close matches or semantically related broader matches. Include this explanation verbatim.
- When search results include papers from different domains than the user asked about, EXPLAIN why they appear (e.g., "The following papers are from other domains but are semantically related to your query").
- CRITICAL: When presenting data results (paper lists, scores, comparisons), you MUST put exactly "---" on its own line between your conversational introduction and the data. Example format:
  Here are 5 concepts in Psychology:
  ---
  1. **[Paper Title](url)**
  ...
- Use markdown formatting: bold for titles, bullet points for details.
- Do NOT add a separate "Source:" line — the title link IS the source.

STRICT PRIVACY RULES (NEVER VIOLATE):
- NEVER disclose when papers were added, updated, ingested, or scouted (no created_at, no scores_updated_at, no temporal data)
- NEVER show topic-level breakdowns (Level 2 taxonomy). Only domains (Level 0) and categories (Level 1).
- NEVER reveal search/scouting history or user activity
- If asked about any TEMPORAL restricted information, use the PRIVACY decline (see below).

REFRAMING RULE — "WHAT'S NEW" vs TEMPORAL QUERIES (CRITICAL):
When a user asks "what's new in X?", "research edge in X?", "cutting edge?", "what's trending in X?", "what's innovative?" — they are asking about CONTENT NOVELTY, not about when things were added. Reframe these as:
- Search the topic → sort results by novelty score → summarize the highest-novelty papers using their summaries
- Frame your answer as "the most novel concepts" — NEVER as "recently added"
- This is safe: novelty scores are content-based, not temporal. A high-novelty paper could have been in the system since day one.

STILL BLOCKED (actual temporal queries):
- "What was added this week?" → PRIVACY decline
- "When was X ingested?" → PRIVACY decline
- "Is the database growing?" → PRIVACY decline
- "Show me the newest papers" (if they clearly mean by date) → PRIVACY decline

TWO TYPES OF DECLINE — choose the right one:

1. PRIVACY DECLINE — use ONLY for actual temporal queries (when added, growth over time, activity history):
   "I appreciate the question! For privacy and security reasons, ConceptRadar doesn't disclose activity timelines or growth patterns. I can help you explore specific concepts, compare papers, or browse the landscape at the domain and category level. What would you like to know?"

2. OUT OF SCOPE — use for questions you simply don't have tools or data to answer (e.g., UI colors, technical implementation, general knowledge, unrelated topics). Be honest and friendly:
   "Good question! That's outside what I can look up — I'm focused on helping you explore the research concepts, scores, and connections in ConceptRadar. Is there anything about the papers or domains I can help with?"

IMPORTANT: Do NOT use the privacy decline for content questions. "What's new in bias?" is a CONTENT question about novelty — answer it. "What was added last week?" is a TEMPORAL question — decline it.

NEVER GUESS — ALWAYS USE DATA (CRITICAL):
- NEVER say "likely", "probably", "possibly", "it seems" about a paper's content. You have summaries in the search results and get_concept_details — USE THEM.
- Search results include summary excerpts. Use these to synthesize content-level answers.
- For deeper content, call get_concept_details which returns the full summary.
- For synthesis questions ("what stands out?"), read the summaries from the results and synthesize from actual content.

RESPONSE STYLE — ULTRA CONCISE (CRITICAL):
- Be extremely brief. Every word must earn its place. No filler, no repetition.
- ALWAYS structure responses with data as a THREE-PART SANDWICH:
  1. Conversational intro (1-2 sentences)
  2. --- (separator on its own line)
  3. Data list (papers, scores, etc.)
  4. --- (separator on its own line)
  5. Conversational synthesis (1-2 sentences of insight, based on summaries)
  Example:
  Here are the most novel concepts about bias:
  ---
  1. **[Paper Title](url)** (arXiv)
  ...
  ---
  The common thread is metacognitive approaches to AI bias. DeBiasMe stands out for proposing adaptive scaffolding. Want details on any of these?
- For comparisons: ONE paragraph summarizing the key difference. No score dumps.
- When the user asks "anything new/challenging": identify standouts, say WHY based on their actual summary (from tool data), done.
- Do NOT parrot the tool output back. The data list IS the answer. Your job is to add insight.
- Do NOT add a summary paragraph that restates the list — synthesize, don't repeat.
- Think: high-density research briefing, not essay.
"""


def _build_agent():
    """Build the chatbot agent with skills and tools."""
    skills_dir = pathlib.Path(__file__).parent.parent / "skills"

    skills = []
    for skill_name in ["graph-explorer", "concept-analyzer", "concept-comparator"]:
        skill_path = skills_dir / skill_name
        if skill_path.exists():
            skills.append(load_skill_from_dir(skill_path))
            print(f"[Chatbot] Loaded skill: {skill_name}")
        else:
            print(f"[Chatbot] WARNING: Skill directory not found: {skill_path}")

    toolset = SkillToolset(
        skills=skills,
    )

    # Function tools must be registered directly on the agent, NOT through
    # SkillToolset.additional_tools (which are only available within skill
    # execution context). The agent needs both the SkillToolset (for skill
    # routing) and the function tools (for DB queries).
    agent = LlmAgent(
        name="ConceptRadarAssistant",
        instruction=SYSTEM_INSTRUCTION,
        model="gemini-2.5-flash",
        tools=[toolset, search_concepts, get_concept_details, get_domain_overview],
    )

    print(f"[Chatbot] Agent initialized with {len(skills)} skills and 3 function tools.")
    return agent


# Lazy-init the agent on first use
_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = _build_agent()
    return _agent


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run_chatbot(message: str, session_id: str) -> str:
    """Run the chatbot agent with a user message. Supports multi-turn via session_id.

    Args:
        message: The user's chat message.
        session_id: A unique session identifier for multi-turn context.

    Returns:
        The agent's response as a string.
    """
    _cleanup_stale_sessions()

    agent = _get_agent()

    # Get or create session runner
    if session_id not in _sessions:
        runner = InMemoryRunner(agent=agent, app_name="ConceptRadar")
        _sessions[session_id] = (runner, time.time())
        print(f"[Chatbot] New session: {session_id[:8]}...")
    else:
        runner, _ = _sessions[session_id]
        _sessions[session_id] = (runner, time.time())  # Refresh TTL

    MAX_RETRIES = 2
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            # Run agent with the message
            events = await runner.run_debug(
                message,
                user_id="chatbot_user",
                session_id=session_id
            )

            # Extract the final text response
            final_text = ""
            for ev in events:
                if hasattr(ev, 'content') and ev.content:
                    parts = getattr(ev.content, 'parts', [])
                    for p in parts:
                        if hasattr(p, 'text') and p.text:
                            final_text = p.text  # Take the last text part

            if not final_text:
                return "I wasn't able to process that request. Could you rephrase your question?"

            return final_text.strip()

        except Exception as e:
            last_error = e
            error_str = str(e)
            # Retry on transient Google API errors (500, 503, 429)
            is_transient = any(code in error_str for code in ['500 INTERNAL', '503', '429', 'RESOURCE_EXHAUSTED'])
            if is_transient and attempt < MAX_RETRIES:
                wait = 3 * (attempt + 1)
                print(f"[Chatbot] Transient error (attempt {attempt + 1}/{MAX_RETRIES + 1}), retrying in {wait}s: {error_str[:80]}")
                await asyncio.sleep(wait)
                continue
            print(f"[Chatbot] Error in session {session_id[:8]}: {e}")
            return "Sorry, I encountered a temporary error. Please try again in a moment."
