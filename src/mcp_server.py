import mcp
from mcp.types import SamplingCapability
mcp.SamplingCapability = SamplingCapability

import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import os
import ssl
import sys
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("ConceptRadarServer")

# Create a permissive SSL context for urllib calls in case of local network/cert issues
ssl_context = ssl._create_unverified_context()

@mcp.tool()
def search_arxiv(query: str, max_results: int = 5) -> str:
    """
    Search arXiv for research papers.
    
    Args:
        query: The search terms (e.g., 'embodied cognition self-healing agents').
        max_results: Maximum number of papers to return (default 5).
        
    Returns:
        JSON string representing list of found papers.
    """
    print(f"MCP Tool 'search_arxiv' called with query: {query}", file=sys.stderr)
    try:
        encoded_query = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded_query}&max_results={max_results}"
        
        req = urllib.request.Request(
            url, 
            headers={"User-Agent": "ConceptRadar-Ingestion-Agent/1.0"}
        )
        
        with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
            xml_data = response.read()
            
        root = ET.fromstring(xml_data)
        
        # Namespace mapping for arXiv feed
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        
        papers = []
        for entry in root.findall('atom:entry', ns):
            paper_id = entry.find('atom:id', ns).text.strip() if entry.find('atom:id', ns) is not None else ""
            title = entry.find('atom:title', ns).text.strip() if entry.find('atom:title', ns) is not None else ""
            summary = entry.find('atom:summary', ns).text.strip() if entry.find('atom:summary', ns) is not None else ""
            published = entry.find('atom:published', ns).text.strip() if entry.find('atom:published', ns) is not None else ""
            
            # Clean up newlines in title and summary
            title = " ".join(title.split())
            summary = " ".join(summary.split())
            
            papers.append({
                "id": f"arxiv:{paper_id.split('/abs/')[-1].split('v')[0]}", # clean ID e.g. arxiv:2403.12345
                "title": title,
                "summary": summary,
                "url": paper_id,
                "source_type": "arxiv",
                "published_at": published,
                "metrics": {
                    "citations": 0 # Default citations for MVP
                }
            })
            
        return json.dumps(papers, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to search arXiv: {str(e)}"})

@mcp.tool()
def search_github(query: str, max_results: int = 5) -> str:
    """
    Search GitHub for code repositories.
    
    Args:
        query: The search terms (e.g., 'agent framework').
        max_results: Maximum number of repositories to return (default 5).
        
    Returns:
        JSON string representing list of found repositories.
    """
    print(f"MCP Tool 'search_github' called with query: {query}", file=sys.stderr)
    try:
        # Search query format, adding topics or qualifier if needed
        encoded_query = urllib.parse.quote(query)
        url = f"https://api.github.com/search/repositories?q={encoded_query}&per_page={max_results}"
        
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ConceptRadar-Ingestion-Agent/1.0")
        
        # Support optional GITHUB_TOKEN to prevent rate limiting
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            req.add_header("Authorization", f"token {github_token}")
            
        with urllib.request.urlopen(req, context=ssl_context, timeout=15) as response:
            json_data = json.loads(response.read().decode('utf-8'))
            
        repos = []
        items = json_data.get("items", [])
        for item in items:
            repo_id = f"github:{item.get('full_name')}"
            title = item.get("name")
            desc = item.get("description") or ""
            html_url = item.get("html_url")
            stars = item.get("stargazers_count", 0)
            forks = item.get("forks_count", 0)
            created_at = item.get("created_at")
            
            repos.append({
                "id": repo_id,
                "title": f"{item.get('full_name')} - {title}",
                "summary": desc,
                "url": html_url,
                "source_type": "github",
                "published_at": created_at,
                "metrics": {
                    "stars": stars,
                    "forks": forks
                }
            })
            
        return json.dumps(repos, indent=2)
    except Exception as e:
        return json.dumps({"error": f"Failed to search GitHub: {str(e)}"})

if __name__ == "__main__":
    mcp.run()
