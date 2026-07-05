"""
Shared Gemini API rate limiter.

Provides a global asyncio.Semaphore that limits concurrent Gemini API calls
across all user-facing and background paths to prevent 429 (RESOURCE_EXHAUSTED) errors.

Usage:
    from .rate_limiter import gemini_generate, gemini_semaphore

    # Async paths: use gemini_generate() as a drop-in wrapper
    response = await gemini_generate(prompt, model="gemini-2.5-flash")

    # Sync paths: acquire the semaphore manually (from async context)
    async with gemini_semaphore:
        response = client.models.generate_content(model=..., contents=prompt)
"""

import asyncio
import time

from google import genai

# Global semaphore: max 5 concurrent Gemini API calls across the entire application.
# Gemini Flash free tier: 30 RPM → 5 concurrent is safe with ~3-6s per call.
# Paid tier can increase this.
MAX_CONCURRENT_GEMINI_CALLS = 5
gemini_semaphore = asyncio.Semaphore(MAX_CONCURRENT_GEMINI_CALLS)

# Module-level reusable client
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = genai.Client()
    return _client


async def gemini_generate(
    prompt: str,
    model: str = "gemini-2.5-flash",
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> str:
    """
    Rate-limited Gemini API call with exponential backoff on 429/RESOURCE_EXHAUSTED.
    
    Returns the response text, or raises on persistent failure.
    """
    client = _get_client()
    
    for attempt in range(max_retries):
        async with gemini_semaphore:
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=model,
                    contents=prompt
                )
                if response and response.text:
                    return response.text.strip()
                return ""
            except Exception as ex:
                err_msg = str(ex)
                is_rate_limit = "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg
                
                if is_rate_limit and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # 2s, 4s, 8s
                    print(f"[RateLimiter] Gemini 429 on attempt {attempt+1}/{max_retries}. "
                          f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise
    
    raise RuntimeError(f"Gemini API call failed after {max_retries} retries")


def gemini_generate_sync(
    prompt: str,
    model: str = "gemini-2.5-flash",
    max_retries: int = 5,
    base_delay: float = 2.0,
) -> str:
    """
    Synchronous rate-limited Gemini call with retry.
    For use in synchronous functions (e.g. assign_cluster).
    Parses API-suggested retryDelay on 429 errors for longer waits.
    """
    client = _get_client()
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model,
                contents=prompt
            )
            if response and response.text:
                return response.text.strip()
            return ""
        except Exception as ex:
            err_msg = str(ex)
            is_rate_limit = "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg
            
            if is_rate_limit and attempt < max_retries - 1:
                # Try to parse API-suggested retry delay
                delay = base_delay * (2 ** attempt)
                import re as _re
                retry_match = _re.search(r'retryDelay.*?(\d+)', err_msg)
                if retry_match:
                    api_delay = int(retry_match.group(1))
                    delay = max(delay, api_delay + 5)  # Use API suggestion + 5s buffer
                
                print(f"[RateLimiter] Gemini 429 (sync) on attempt {attempt+1}/{max_retries}. "
                      f"Retrying in {delay:.0f}s...")
                time.sleep(delay)
                continue
            else:
                raise
    
    raise RuntimeError(f"Gemini API call (sync) failed after {max_retries} retries")

