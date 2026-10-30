"""Fetch pages from an explicit allowlist of official documentation domains.

This is a conservative documentation fetcher, not an unrestricted web crawler.
It uses robots.txt, a per-request delay, same-domain links, and a page cap.
"""
from __future__ import annotations
import json, os, re, time, hashlib
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urldefrag
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "knowledge_base/sources.json"
OUTPUT = ROOT / "knowledge_base/raw/external"
TIMEOUT = float(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))
DELAY = float(os.getenv("DOC_FETCH_DELAY_SECONDS", "1.0"))
USER_AGENT = "BlessingAIKnowledgeBot/0.1 (+documentation indexing; contact site owner before production crawling)"


def safe_name(url: str) -> str:
    parsed = urlparse(url)
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", parsed.path).strip("-")[:90] or "index"
    return f"{parsed.netloc}-{slug}".lower()


def allowed_url(url: str, domains: set[str]) -> bool:
    parsed = urlparse(url)
    return parsed.scheme == "https" and parsed.hostname in domains and not parsed.username and not parsed.password


def get_robots(client: httpx.Client, domain: str) -> RobotFileParser:
    robots_url = f"https://{domain}/robots.txt"
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        response = client.get(robots_url, timeout=TIMEOUT)
        if response.status_code == 200:
            rp.parse(response.text.splitlines())
        else:
            # Fail closed when robots policy cannot be determined.
            rp.parse(["User-agent: *", "Disallow: /"])
    except httpx.HTTPError:
        rp.parse(["User-agent: *", "Disallow: /"])
    return rp


def main():
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "pages": [], "errors": []}
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    with httpx.Client(follow_redirects=True, headers=headers) as client:
        robots_cache = {}
        for source in registry:
            if not source.get("enabled", False):
                continue
            domains = set(source.get("allowed_domains", []))
            if not domains or not allowed_url(source["url"], domains):
                manifest["errors"].append({"source": source.get("id"), "error": "URL/domain not on HTTPS allowlist"})
                continue
            queue, seen = [source["url"]], set()
            max_pages = min(max(int(source.get("max_pages", 1)), 1), 20)
            fetched = 0
            while queue and fetched < max_pages:
                url = urldefrag(queue.pop(0))[0]
                if url in seen or not allowed_url(url, domains):
                    continue
                seen.add(url)
                domain = urlparse(url).hostname
                if domain not in robots_cache:
                    robots_cache[domain] = get_robots(client, domain)
                if not robots_cache[domain].can_fetch(USER_AGENT, url):
                    manifest["errors"].append({"url": url, "error": "Disallowed by robots.txt or robots policy unavailable"})
                    continue
                try:
                    response = client.get(url, timeout=TIMEOUT)
                    time.sleep(DELAY)
                    response.raise_for_status()
                except httpx.HTTPError as exc:
                    manifest["errors"].append({"url": url, "error": str(exc)[:300]})
                    continue
                if "text/html" not in response.headers.get("content-type", "").lower():
                    continue
                final_url = str(response.url)
                if not allowed_url(final_url, domains):
                    manifest["errors"].append({"url": url, "error": "Redirected outside approved domain"})
                    continue
                soup = BeautifulSoup(response.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "svg"]):
                    tag.decompose()
                title = soup.title.get_text(" ", strip=True) if soup.title else source.get("title", source["id"])
                main = soup.find("main") or soup.find("article") or soup.body or soup
                text = "\n".join(line.strip() for line in main.get_text("\n").splitlines() if line.strip())
                if not text:
                    continue
                digest = hashlib.sha256(text.encode()).hexdigest()
                file = OUTPUT / f"{safe_name(final_url)}.md"
                file.write_text(
                    f"---\nsource: external-official-docs\nservice: {source.get('service')}\n"
                    f"source_id: {source.get('id')}\ntitle: {title}\nurl: {final_url}\n"
                    f"fetched_at: {datetime.now(timezone.utc).isoformat()}\n"
                    f"content_sha256: {digest}\n---\n\n# {title}\n\nSource: {final_url}\n\n{text}\n",
                    encoding="utf-8",
                )
                manifest["pages"].append({"source_id": source.get("id"), "title": title, "url": final_url, "file": file.name, "sha256": digest})
                fetched += 1
                for link in main.find_all("a", href=True):
                    next_url = urldefrag(urljoin(final_url, link["href"]))[0]
                    if next_url not in seen and allowed_url(next_url, domains):
                        # Avoid obvious non-document endpoints and fragments/query spam.
                        parsed = urlparse(next_url)
                        if not re.search(r"\.(pdf|png|jpg|jpeg|zip|svg|gif|woff2?)$", parsed.path, re.I):
                            queue.append(next_url)
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Fetched {len(manifest['pages'])} pages; {len(manifest['errors'])} skipped/errors.")
    print(f"Output: {OUTPUT}")
    if manifest["errors"]:
        print("Review knowledge_base/raw/external/manifest.json before indexing.")


if __name__ == "__main__":
    main()
