import sys
import os
import json
import asyncio

# Apply mcp monkeypatches
import mcp
from mcp.types import SamplingCapability
mcp.SamplingCapability = SamplingCapability

from mcp import ClientSession
original_init = ClientSession.__init__
def patched_init(self, *args, **kwargs):
    kwargs.pop('sampling_capabilities', None)
    return original_init(self, *args, **kwargs)
ClientSession.__init__ = patched_init

# Monkeypatch genai.Client to always use retry config for robustness against transient 429s
try:
    from google import genai
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
    print("[ConceptRadar] Applied genai.Client retry monkeypatches: SUCCESS.")
except Exception as patch_ex:
    print(f"Failed to patch genai.Client with retry config: {patch_ex}")

from mcp import StdioServerParameters
from google.adk.agents.llm_agent import LlmAgent
from google.adk.runners import InMemoryRunner
from google import genai
from .db import get_all_nodes
from .scoring import get_embedding, cosine_similarity
from .rate_limiter import gemini_semaphore
from .patches import apply_patches
apply_patches()

# Ingestion Agent setup
async def run_ingestion_agent(query: str, max_results: int = 5) -> list[dict]:
    """Runs the Ingestion Agent using the custom MCP Server tools to discover papers and code."""
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset, StdioConnectionParams
    from mcp import StdioServerParameters
    
    # Configure toolset pointing to our local stdio-based MCP server using StdioConnectionParams to set custom timeout
    toolset = McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,  # Uses the active environment's Python interpreter to avoid import crashes
                args=["src/mcp_server.py"]
            ),
            timeout=30.0  # Set tool execution timeout to 30 seconds
        )
    )
    
    # Set up ingestion instructions with built-in query optimization guidelines
    instruction = f"""
    You are the Ingestion Agent for ConceptRadar. 
    Your goal is to scout the AI research and code landscape for the topic: '{query}'.
    
    CRITICAL QUERY OPTIMIZATION RULES:
    1. The query '{query}' might contain conversational words, prepositions, or templates (e.g. "compliance of AI", "a framework for X").
    2. Before calling the search tools, optimize the query. Strip out stop-words ("of", "the", "a", "framework", "library for") and extract clean, keyword-dense search terms (e.g. "AI compliance", "LLM compliance", "compliance AI").
    3. Use these refined keywords when calling search_arxiv and search_github.
    4. If a search returns 0 results, refine the query again with another variation (e.g. "AI safety governance", "AI policy compliance") and retry, to ensure you discover relevant resources.
    
    Use the available search tools:
    1. Call 'search_arxiv' to find relevant preprints (limit search to {max_results} results).
    2. Call 'search_github' to find relevant repositories (limit search to {max_results} results).
    
    CRITICAL INGESTION ENFORCEMENT:
    You MUST call BOTH 'search_arxiv' and 'search_github' for the topic (or its optimized keyword variations) to ensure you discover both papers and code. Combine results from both sources in your final JSON output. Do not lazily return results from only one tool.
    
    After calling these tools, combine and format the results.
    Return ONLY a raw JSON array of objects. Do not include markdown code block backticks (like ```json).
    Each object in the array must strictly match this schema:
    {{
      "id": "arxiv:..." or "github:...",
      "title": "Title of the paper or repository",
      "summary": "A concise 2-3 sentence summary of the core concept and contribution",
      "url": "URL link",
      "source_type": "arxiv" or "github",
      "published_at": "ISO timestamp or publication date",
      "metrics": {{
         "stars": 123 (if github, else 0),
         "forks": 45 (if github, else 0),
         "citations": 0 (default 0 for arxiv)
      }}
    }}
    """
    
    agent = LlmAgent(
        name="IngestionAgent",
        instruction=instruction,
        model="gemini-2.5-flash",
        tools=[toolset]
    )
    
    runner = InMemoryRunner(agent=agent)
    try:
        print(f"Starting ingestion agent for topic: '{query}'...")
        events = await runner.run_debug(f"Search for AI startups, papers, and repositories on: '{query}'")
        
        # Find the final text response from the model
        final_text = ""
        for ev in events:
            if hasattr(ev, 'content') and ev.content:
                parts = getattr(ev.content, 'parts', [])
                for p in parts:
                    if hasattr(p, 'text') and p.text:
                        final_text += p.text
        
        # Parse the JSON response
        final_text = final_text.strip()
        # Strip markdown formatting block if present
        if final_text.startswith("```"):
            lines = final_text.splitlines()
            if lines[0].startswith("```json") or lines[0] == "```":
                lines = lines[1:-1]
            final_text = "\n".join(lines)
            
        try:
            items = json.loads(final_text.strip())
            if isinstance(items, list):
                print(f"Ingested {len(items)} items successfully!")
                return items
            elif isinstance(items, dict) and "items" in items:
                return items["items"]
            else:
                print("Unexpected JSON structure:", final_text)
                return []
        except json.JSONDecodeError as ex:
            print("Failed to parse JSON output from agent. Output was:", final_text)
            print("Parsing error:", ex)
            return []
    finally:
        await runner.close()

# Contradiction Agent setup
async def run_contradiction_agent(new_node: dict, candidate_nodes: list[dict], max_sim: float = 0.0, base_novelty: float = 1.0, model_name: str = "gemini-2.5-flash", taxonomy_context: dict = None) -> dict:
    """
    Runs a senior research alignment agent to check if the new node contradicts, 
    implements, or duplicates any existing node.
    
    taxonomy_context (optional): {
        "domain_name": str, "area_name": str, "topic_name": str,
        "peer_count": int, "is_cross_disciplinary": bool, "tag_names": list[str]
    }
    """
    if not candidate_nodes:
        # Construct N/A report if no candidates exist
        analysis_na = (
            "### Novelty & Literature Alignment\n"
            "This is the first concept mapped in this segment. No semantic matches exist yet.\n"
        )
        return {
            "summary": new_node.get("summary", ""),
            "novelty_statement": "Highly novel concept (no semantic matches found in database).",
            "contradiction_statement": "No conflicts detected (empty segment).",
            "keywords": None,
            "novelty_score": 1.0,
            "novelty_penalty": 0.0,
            "analysis": analysis_na,
            "edges": []
        }
        
    client = genai.Client()
    
    # Format candidates list for prompt (with topic metadata if available)
    candidates_text = ""
    for idx, c in enumerate(candidate_nodes):
        c_topic = c.get('_topic_name', '')
        c_domain = c.get('_domain_name', '')
        topic_info = f" | Domain: {c_domain} | Topic: {c_topic}" if c_topic else ""
        candidates_text += f"\nReference [{idx}] ({c['id']}) - Type: {c['source_type']}{topic_info}\n"
        candidates_text += f"Title: {c['title']}\n"
        summary_text = c.get('summary', '')[:250]
        candidates_text += f"Summary: {summary_text}\n"
        candidates_text += f"URL: {c.get('url', '')}\n"
        candidates_text += "-" * 40 + "\n"
        
    max_sim_text = f"{int(max_sim * 100)}%" if max_sim > 0.0 else "N/A"
    closest_candidate_name = candidate_nodes[0]['title'] if candidate_nodes else "None"
    
    # Build taxonomy context section
    tax_section = ""
    if taxonomy_context:
        tc = taxonomy_context
        tax_section = f"""
    Taxonomy Position:
    Domain: {tc.get('domain_name', 'Unknown')} | Area: {tc.get('area_name', 'Unknown')} | Topic: {tc.get('topic_name', 'Unknown')}
    Peers in same topic: {tc.get('peer_count', 0)}
    Cross-disciplinary: {'Yes — this paper bridges multiple research domains' if tc.get('is_cross_disciplinary') else 'No'}
    Secondary tags: {', '.join(tc.get('tag_names', [])) if tc.get('tag_names') else 'none'}
    """
        
    prompt = f"""
    You are the Senior Research & Novelty Alignment Agent for ConceptRadar.
    Your task is to perform a rigorous comparative analysis of a new scientific/technical concept against reference literature.
    
    NOTE: The reference list includes BOTH same-topic AND cross-topic papers to give you a broad perspective.
    
    New Concept to Analyze:
    ID: {new_node['id']}
    Title: {new_node['title']}
    Description: {new_node['summary']}
    {tax_section}
    Reference Literature (mix of same-topic and cross-topic):
    {candidates_text}
    
    Your task is to generate a comprehensive, highly professional, and insightful comparative analysis.
    Analyze the concept across these dimensions:
    1. Executive Summary: A concise, clear 3-4 sentence summary of the concept. Do NOT copy the input text verbatim.
    2. Novelty Assessment: A single-sentence qualitative assessment detailing what is novel, to what degree, and how it differs from closest matches. Do NOT include raw numbers/decimals.
    3. Feasibility & Validation: A 1-2 sentence statement explaining if there are any conflicts, or confirming validation/alignment with existing research.
    4. Scouting Keywords: 1-2 highly descriptive search keywords/phrases suitable for literature scouting.
    
    CRITICAL: For the "novelty_score" rating (0.0 to 1.0), evaluate CONCEPTUAL NOVELTY using these guidelines:
    
    IMPORTANT: Novelty is NOT just semantic distance from references. Consider:
    - Does it introduce a novel FRAMING or COMBINATION of known concepts?
    - Does it bridge concepts across different research areas or domains?
    - Does it propose a new architectural pattern, methodology, or perspective?
    - Is it an incremental extension, or a creative recombination?
    
    Scoring scale:
    - 0.0 to 0.20 (Duplicate): Direct duplicate or trivial repackaging of existing work
    - 0.20 to 0.40 (Low Novelty): Minor variation of well-established ideas with no new mechanisms
    - 0.40 to 0.60 (Moderate): Meaningful extension or application to a new domain
    - 0.60 to 0.80 (High): Novel framing, creative integration, or unique bridge across areas
    - 0.80 to 1.0 (Breakthrough): Paradigm-defining breakthrough or first-of-its-kind concept
    
    A paper that connects ideas from different domains or proposes a new governance model for an emerging area is at LEAST 0.60, even if individual concepts are familiar.
    
    Return ONLY a raw JSON object (do not include markdown code block ticks). Schema:
    {{
      "summary": "3-4 sentence summary of the concept.",
      "novelty_statement": "Single sentence novelty assessment.",
      "contradiction_statement": "1-2 sentence contradiction/feasibility assessment.",
      "keywords": "search keywords (e.g. 'preference optimization reward model')",
      "novelty_score": 0.0 to 1.0,
      "novelty_penalty": 0.0 to 1.0 (0.0 means no penalty, 1.0 means complete duplicate/identical),
      "edges": [
         {{
           "target_id": "ID of the matched candidate",
           "relationship_type": "contradicts" | "implements" | "inspired_by" | "extends" | "duplicates" | "cites",
           "similarity": 0.0 to 1.0,
           "reasoning": "A 1-sentence explanation of this relationship"
         }}
      ]
    }}
    """
    
    try:
        async with gemini_semaphore:
            response = await asyncio.to_thread(
                client.models.generate_content,
                model=model_name,
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
        t = response.text.strip()
        if not t:
            raise ValueError("Empty text from LLM model.")
        if "```" in t:
            import re
            t = re.sub(r'^```(?:json)?\s*', '', t, flags=re.MULTILINE)
            t = re.sub(r'\s*```$', '', t, flags=re.MULTILINE)
        t = t.strip()
        # Clean trailing commas
        import re
        t = re.sub(r',(\s*[}\]])', r'\1', t)
        data = json.loads(t)
        
        # Build combined analysis report
        nov_stmt = data.get("novelty_statement", "Highly novel concept.").strip()
        con_stmt = data.get("contradiction_statement", "No conflicts detected.").strip()
        analysis_md = f"{nov_stmt} {con_stmt}"
        
        return {
            "summary": data.get("summary", new_node.get("summary", "")[:250] + "..."),
            "novelty_statement": nov_stmt,
            "contradiction_statement": con_stmt,
            "keywords": data.get("keywords"),
            "novelty_score": float(data.get("novelty_score", 0.5)),
            "novelty_penalty": float(data.get("novelty_penalty", 0.0)),
            "analysis": analysis_md,
            "edges": data.get("edges", [])
        }
    except Exception as e:
        print(f"Contradiction agent failed: {e}")
        if model_name == "gemini-2.5-pro":
            raise e
        return {
            "summary": new_node.get("summary", "")[:250] + "...",
            "novelty_statement": "Novelty evaluation unavailable due to API rate limits.",
            "contradiction_statement": "Validation check unavailable.",
            "keywords": None,
            "novelty_score": 0.5,
            "novelty_penalty": 0.0,
            "analysis": "### Novelty & Literature Alignment\nEvaluation unavailable due to API rate limits.",
            "edges": []
        }

async def evaluate_publisher_authority(domain: str, title: str = "", summary: str = "", path_type: str = "general") -> float:
    """Evaluates dynamic publisher authority for unknown web domains using Gemini 2.5 Flash."""
    try:
        from google import genai
        client = genai.Client()
        prompt = f"""
You are an expert academic and technical publisher authority evaluator.
Evaluate whether the following web domain/publisher is a reputable research institution, industry standards organization, university, reputable tech blog, or peer-reviewed publication venue.

Domain: {domain}
Publication Type: {path_type} (e.g. 'blog' = informal commentary/post, 'artifact' = peer-reviewed whitepaper/research paper)
Publication Title: {title}
Publication Summary: {summary}

Respond ONLY with a JSON object in this exact format:
{{
  "is_reputable": true,
  "validation_score": 0.40,
  "reasoning": "Brief explanation"
}}

Validation Score guidelines:
- Peer-reviewed research papers / official standards artifacts (PDFs/whitepapers): 0.60 - 0.75
- Official blog posts / opinion articles from recognized institutions: 0.30 - 0.45
- Generic personal blogs / unverified forums: 0.10 - 0.25
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        data = json.loads(response.text.strip())
        score = float(data.get("validation_score", 0.10))
        return max(0.10, min(0.80, score))
    except Exception as ex:
        print(f"[Smart Validation] Dynamic LLM publisher authority evaluation failed for '{domain}': {ex}")
        return 0.10

