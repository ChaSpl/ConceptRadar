import re
import os
from datetime import datetime
import urllib.request
import urllib.parse
import urllib.error
import time
import xml.etree.ElementTree as ET
import json
from google import genai

# Create a permissive SSL context for urllib calls in case of local network/cert issues
import ssl
ssl_context = ssl._create_unverified_context()

def clean_html(html_content: str) -> str:
    """Removes HTML tags, scripts, and styles to get clean raw text."""
    text = re.sub(r'<(script|style).*?>.*?</\1>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]*>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def scrape_source_url(url: str) -> dict:
    """
    Parses the URL to extract metadata.
    Supports dedicated arXiv and GitHub endpoints, with a general fallback.
    Returns:
        dict: {
            "title": str,
            "summary": str,
            "url": str,
            "source_type": str,  # "arxiv", "github", or "web"
            "metrics": dict
        }
    """
    # Clean URL whitespace
    url = url.strip()
    
    # 1. Check for arXiv URL
    arxiv_match = re.search(r'arxiv\.org/(abs|pdf)/([0-9\.]+)', url)
    if arxiv_match:
        arxiv_id = arxiv_match.group(2)
        print(f"[Scraper] Detected arXiv ID: {arxiv_id}")
        query_url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
        req = urllib.request.Request(
            query_url, 
            headers={"User-Agent": "ConceptRadar-Scraper/1.0"}
        )
        xml_data = None
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, context=ssl_context, timeout=12) as response:
                    xml_data = response.read()
                break
            except urllib.error.HTTPError as he:
                if he.code == 429 and attempt == 0:
                    print("[Scraper] arXiv returned 429. Waiting 2.5 seconds to retry...")
                    time.sleep(2.5)
                    continue
                raise he
            
        root = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom'}
        entry = root.find('atom:entry', ns)
        if entry is not None:
            title = entry.find('atom:title', ns).text.strip() if entry.find('atom:title', ns) is not None else "Unknown arXiv Paper"
            summary = entry.find('atom:summary', ns).text.strip() if entry.find('atom:summary', ns) is not None else ""
            title = " ".join(title.split())
            summary = " ".join(summary.split())
            published = entry.find('atom:published', ns).text.strip() if entry.find('atom:published', ns) is not None else ""
            
            return {
                "title": title,
                "summary": summary,
                "url": f"https://arxiv.org/abs/{arxiv_id}",
                "source_type": "arxiv",
                "published_at": published,
                "metrics": {"citations": 0}
            }
        raise Exception(f"Paper {arxiv_id} not found in arXiv database.")

    # 2. Check for GitHub URL
    github_match = re.search(r'github\.com/([^/]+)/([^/]+?)(?:\.git|/)?$', url)
    if github_match:
        owner = github_match.group(1)
        repo = github_match.group(2)
        print(f"[Scraper] Detected GitHub repository: {owner}/{repo}")
        query_url = f"https://api.github.com/repos/{owner}/{repo}"
        
        req = urllib.request.Request(query_url)
        req.add_header("User-Agent", "ConceptRadar-Scraper/1.0")
        
        github_token = os.getenv("GITHUB_TOKEN")
        if github_token:
            req.add_header("Authorization", f"token {github_token}")
            
        with urllib.request.urlopen(req, context=ssl_context, timeout=12) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        title = data.get("name", repo)
        desc = data.get("description", "") or ""
        
        # Build a clean title: prefer description if it's meaningful, else humanize repo name
        repo_name_clean = title.replace("-", " ").replace("_", " ").strip().title()
        if desc and len(desc) > 10 and desc.lower() != title.lower():
            clean_title = desc.split(".")[0].strip()  # Use first sentence of description
            if len(clean_title) > 80:
                clean_title = clean_title[:77] + "..."
        else:
            clean_title = repo_name_clean
        
        stars = data.get("stargazers_count", 0)
        forks = data.get("forks_count", 0)
        created_at = data.get("created_at")
        
        return {
            "title": clean_title,
            "summary": desc,
            "url": data.get("html_url"),
            "source_type": "github",
            "published_at": created_at,
            "metrics": {
                "stars": stars,
                "forks": forks
            }
        }

    # 3. Check for Medium URL
    # Match medium.com/@username/post-slug or username.medium.com/post-slug
    medium_match = re.search(r'medium\.com/(@[a-zA-Z0-9_\-\.]+)/([a-zA-Z0-9_\-\.]+)', url)
    if not medium_match:
        medium_match = re.search(r'([a-zA-Z0-9_\-\.]+)\.medium\.com/([a-zA-Z0-9_\-\.]+)', url)
        
    if medium_match:
        username = medium_match.group(1)
        post_slug = medium_match.group(2)
        if not username.startswith("@"):
            username = f"@{username}"
            
        print(f"[Scraper] Detected Medium article: {username}/{post_slug}")
        feed_url = f"https://medium.com/feed/{username}"
        
        req = urllib.request.Request(
            feed_url, 
            headers={"User-Agent": "ConceptRadar-Scraper/1.0"}
        )
        
        try:
            with urllib.request.urlopen(req, context=ssl_context, timeout=12) as response:
                xml_data = response.read()
                
            root = ET.fromstring(xml_data)
            namespaces = {'content': 'http://purl.org/rss/1.0/modules/content/'}
            
            matched_item = None
            for item in root.findall(".//item"):
                link_el = item.find("link")
                link_text = link_el.text.split("?")[0] if link_el is not None else ""
                if post_slug in link_text or post_slug in link_el.text:
                    matched_item = item
                    break
                    
            if matched_item is not None:
                title_text = matched_item.find("title").text
                content_encoded = matched_item.find("content:encoded", namespaces)
                if content_encoded is not None:
                    body_html = content_encoded.text
                    body_text = clean_html(body_html)
                else:
                    body_text = clean_html(matched_item.find("description").text or "")
                    
                # Use Gemini to summarize the feed content
                client = genai.Client()
                prompt = f"""
                You are an expert academic cataloger and AI researcher. 
                Generate a clean, high-quality, professional 3-sentence summary of the core concept, methodology, and contributions of this publication.
                
                Title: {title_text}
                Content:
                {body_text[:12000]}
                
                Return ONLY the raw 3-sentence summary. Do not include any headers or meta text.
                """
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt
                )
                summary_text = response.text.strip()
                
                pub_date_el = matched_item.find("pubDate")
                pub_date = pub_date_el.text if pub_date_el is not None else None
                
                return {
                    "title": title_text,
                    "summary": summary_text,
                    "url": url,
                    "source_type": "web",
                    "published_at": pub_date,
                    "metrics": {}
                }
            else:
                print(f"[Scraper] Could not find slug '{post_slug}' in Medium RSS feed for {username}. Falling back to general web scraper.")
        except Exception as e_rss:
            print(f"[Scraper] Medium RSS scraping failed for feed '{feed_url}': {e_rss}. Falling back to general web scraper.")

    # 4. Fallback to General Web Scraping
    
    # 4a. Reject direct PDF/binary file URLs upfront (can't be scraped as HTML)
    url_path_lower = urllib.parse.urlparse(url).path.lower()
    binary_extensions = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.zip', '.gz', '.tar', '.exe', '.bin')
    if url_path_lower.endswith(binary_extensions):
        ext = url_path_lower.rsplit('.', 1)[-1]
        raise Exception(f"Direct .{ext} file links cannot be scraped. Please use the manual entry form to add this source with a title and summary.")
    
    print(f"[Scraper] Falling back to general web scraper for: {url}")
    html_content = ""
    try:
        import requests
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        r = requests.get(url, headers=headers, timeout=5, verify=False)
        if r.status_code == 200:
            html_content = r.text
    except Exception as e_req:
        print(f"[Scraper] Fast requests fetch failed for '{url}': {e_req}. Trying urllib fallback...")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, context=ssl_context, timeout=6) as response:
                html_content = response.read().decode('utf-8', errors='ignore')
        except Exception as e_url:
            print(f"[Scraper] urllib fetch also failed for '{url}': {e_url}.")
            
    body_text = clean_html(html_content) if html_content else ""
    
    # Strictly enforce quality: If webpage blocks scrapers or returns insufficient text, reject mapping
    if len(body_text) < 100:
        raise Exception("This webpage blocks automated scrapers or returned unreadable content and cannot be mapped.")
    
    # Detect binary/PDF content that passed as text (e.g. raw PDF streams decoded as UTF-8)
    if body_text[:20].startswith('%PDF') or 'endobj' in body_text[:2000] or 'endstream' in body_text[:2000]:
        raise Exception("Content appears to be raw PDF binary data, not human-readable text. Use manual entry instead.")
    
    # Check for high ratio of non-printable/garbage characters (binary content detection)
    sample = body_text[:3000]
    non_printable = sum(1 for c in sample if ord(c) < 32 and c not in '\n\r\t')
    if len(sample) > 0 and (non_printable / len(sample)) > 0.05:
        raise Exception("Content contains too many non-printable characters, likely binary data. Use manual entry instead.")
        
    # Use Gemini to clean and extract structured metadata
    client = genai.Client()
    prompt = f"""You are an expert academic cataloger. You have TWO tasks.

=== TASK A: EXTRACT METADATA ===
From the webpage content below, extract:
- "title": The core title of the paper, tool, article, or project. Be concise, no site names.
- "summary": A clean 3-sentence summary of the concept, methodology, and conclusions. Professional tone.

=== TASK B: CLASSIFY DOCUMENT TYPE ===
Based on the content AND the URL, classify this document into EXACTLY ONE type.

Think step-by-step:
1. Who published this? (government, standards body, company, individual, academic?)
2. What is the purpose? (law, standard, guidance, research, opinion, software?)
3. Pick the BEST match below:

Types (pick ONE):
- "legislation" = Official law, act, directive (EU AI Act, GDPR, national AI laws)
- "regulation" = Binding rules from a regulatory authority
- "standard" = Published standard from recognized body (NIST, ISO, IEEE, IEC, OECD, DIN)
- "framework_official" = Official framework from government/standards body (NIST AI RMF, MITRE ATT&CK)
- "best_practice" = Industry best practice or guidance from recognized authority (CSA CCSK, OWASP Top 10)
- "research_paper" = Academic paper, preprint, study, or think-tank analysis
- "blog_post" = Blog, opinion piece, news article, tutorial, commentary, or vendor marketing
- "tool" = Software tool, library, SDK, platform, or open-source project
- "youtube" = YouTube video content (talks, demos, tutorials, presentations)
- "idea" = Original idea, concept proposal, or speculative design (no formal publication)
- "other" = Only if NONE of the above fit at all

RULES:
- Research papers PROPOSING a framework = "research_paper", NOT "framework_official"
- Vendor marketing pages = "blog_post", NOT "best_practice"
- Medium/Substack/dev.to posts = "blog_post"
- YouTube videos = "youtube"
- GitHub repos = "tool"
- Try hard to avoid "other" — one of the above types almost always fits.

URL: {url}

Webpage Content:
{body_text[:8000]}

Return ONLY a raw JSON object (no markdown backticks):
{{
  "title": "Clean concise title",
  "summary": "The 3-sentence summary",
  "document_type": "one of the types above"
}}
"""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    
    response_text = response.text.strip()
    if response_text.startswith("```"):
        lines = response_text.splitlines()
        if lines[0].startswith("```json") or lines[0] == "```":
            lines = lines[1:-1]
        response_text = "\n".join(lines)
        
    extracted = json.loads(response_text.strip())
    
    # Post-LLM quality gate: reject if Gemini flagged the content as unreadable/binary
    title = extracted.get("title", "")
    summary = extracted.get("summary", "")
    document_type = extracted.get("document_type", "other")
    garbage_indicators = ["unreadable", "binary data", "raw pdf", "cannot be extracted",
                          "not human-readable", "prevents direct extraction", "cannot be generated"]
    combined_lower = (title + " " + summary).lower()
    if any(g in combined_lower for g in garbage_indicators):
        raise Exception(f"LLM flagged content as unreadable: '{title}'. Rejecting to maintain data quality.")
    
    # Validate document_type against allowed values
    valid_types = {"legislation", "regulation", "standard", "framework_official", 
                   "best_practice", "research_paper", "blog_post", "tool", "youtube", "idea", "other"}
    if document_type not in valid_types:
        document_type = "other"
    
    return {
        "title": title or f"Web Resource ({url})",
        "summary": summary or "Web resource summary.",
        "url": url,
        "source_type": "web",
        "document_type": document_type,
        "published_at": datetime.utcnow().isoformat(),
        "metrics": {}
    }
