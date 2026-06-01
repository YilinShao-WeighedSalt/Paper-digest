#!/usr/bin/env python3
"""Fetch top papers from Semantic Scholar and arXiv, output as JSON."""

import json
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

import httpx

TOP_CONFERENCES = [
    "NeurIPS", "ICML", "ICLR", "AAAI", "CVPR", "ICCV", "ECCV",
    "ACL", "EMNLP", "NAACL", "SIGKDD",
    "ICRA", "IROS", "RSS", "CoRL", "HRI",
    "DATE", "DAC", "EMSOFT", "ICCAD", "RTSS",
]

ARXIV_CATEGORIES = [
    "cs.RO", "cs.AI", "cs.LG", "cs.CV", "cs.AR", "cs.SY", "eess.SY",
]

PAPERS_PER_WEEK = 5


def fetch_semantic_scholar(weeks_back=4):
    base = "https://api.semanticscholar.org/graph/v1"
    papers = []
    cutoff = (datetime.now() - timedelta(weeks=weeks_back)).strftime("%Y-%m-%d")

    queries = [
        "robotics learning control",
        "large language model",
        "deep learning neural network",
        "embedded systems real-time",
        "computer vision transformer",
        "reinforcement learning robot",
    ]

    for query in queries:
        try:
            resp = httpx.get(
                f"{base}/paper/search",
                params={
                    "query": query,
                    "limit": 20,
                    "fields": "title,authors,abstract,venue,year,citationCount,externalIds,url,fieldsOfStudy,publicationDate",
                    "publicationDateOrYear": f"{cutoff}:",
                    "sort": "citationCount:desc",
                },
                timeout=30,
            )
            if resp.status_code == 429:
                time.sleep(3)
                continue
            if resp.status_code != 200:
                continue

            for item in resp.json().get("data", []):
                if not item.get("abstract"):
                    continue

                authors = [a.get("name", "?") for a in (item.get("authors") or [])[:5]]
                arxiv_id = (item.get("externalIds") or {}).get("ArXiv", "")
                url = item.get("url") or (f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else "")

                papers.append({
                    "title": item["title"],
                    "authors": authors,
                    "abstract": item["abstract"],
                    "venue": item.get("venue") or "Preprint",
                    "year": item.get("year") or datetime.now().year,
                    "citations": item.get("citationCount") or 0,
                    "url": url,
                    "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}" if arxiv_id else "",
                    "source": "Semantic Scholar",
                })

            time.sleep(1)
        except httpx.HTTPError:
            continue

    return papers


def fetch_arxiv(max_results=30):
    search_query = " OR ".join(f"cat:{c}" for c in ARXIV_CATEGORIES)
    try:
        resp = httpx.get(
            "https://export.arxiv.org/api/query",
            params={
                "search_query": search_query,
                "start": 0,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            },
            timeout=60,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.TimeoutException):
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(resp.text)
    papers = []

    for entry in root.findall("atom:entry", ns):
        title = entry.findtext("atom:title", "", ns).replace("\n", " ").strip()
        abstract = entry.findtext("atom:summary", "", ns).strip()
        authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)][:5]

        url, pdf_url = "", ""
        for link in entry.findall("atom:link", ns):
            if link.get("type") == "text/html":
                url = link.get("href", "")
            elif link.get("title") == "pdf":
                pdf_url = link.get("href", "")
        if not url:
            url = entry.findtext("atom:id", "", ns)

        papers.append({
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "venue": "arXiv Preprint",
            "year": datetime.now().year,
            "citations": 0,
            "url": url,
            "pdf_url": pdf_url,
            "source": "arXiv",
        })

    return papers


def classify(paper):
    text = (paper["title"] + " " + paper["abstract"]).lower()
    if any(kw in text for kw in ["robot", "manipulation", "locomotion", "grasp", "navigation", "slam"]):
        return "Robotics"
    if any(kw in text for kw in ["embedded", "fpga", "real-time", "iot", "edge computing", "microcontroller"]):
        return "Embedded Systems"
    return "AI/ML"


def rank_and_select(papers, n=PAPERS_PER_WEEK):
    seen = set()
    unique = []
    for p in papers:
        key = p["title"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(p)

    def score(p):
        s = min(p["citations"] * 2, 200)
        venue = p["venue"].upper()
        if any(c.upper() in venue for c in TOP_CONFERENCES):
            s += 100
        if p["venue"] not in ("arXiv Preprint", "Preprint"):
            s += 30
        if p["pdf_url"]:
            s += 10
        return s

    unique.sort(key=score, reverse=True)

    selected = []
    domain_count = {}
    for p in unique:
        if len(selected) >= n:
            break
        d = classify(p)
        if domain_count.get(d, 0) >= 3:
            continue
        p["domain"] = d
        selected.append(p)
        domain_count[d] = domain_count.get(d, 0) + 1

    return selected


def main():
    print("Fetching from Semantic Scholar...", file=sys.stderr)
    s2 = fetch_semantic_scholar()
    print(f"  {len(s2)} papers", file=sys.stderr)

    print("Fetching from arXiv...", file=sys.stderr)
    arxiv = fetch_arxiv()
    print(f"  {len(arxiv)} papers", file=sys.stderr)

    selected = rank_and_select(s2 + arxiv)
    print(f"Selected {len(selected)} papers", file=sys.stderr)

    json.dump(selected, sys.stdout, indent=2)


if __name__ == "__main__":
    main()
