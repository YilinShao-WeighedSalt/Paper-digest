#!/usr/bin/env python3
"""Build and send the weekly digest email from a JSON file of analyzed papers.

Usage:
    python send_digest.py digest.json                    # Send email
    python send_digest.py digest.json --preview          # Save HTML locally
    python send_digest.py digest.json --preview --open   # Save and open in browser

Expected JSON format (list of objects):
    [
        {
            "title": "...",
            "authors": ["..."],
            "venue": "...",
            "year": 2025,
            "citations": 42,
            "url": "...",
            "pdf_url": "...",
            "domain": "AI/ML",
            "analysis": "### The Problem\\n..."
        }
    ]
"""

import json
import os
import re
import smtplib
import subprocess
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

DOMAIN_COLORS = {
    "Robotics": "#e74c3c",
    "Embedded Systems": "#27ae60",
    "AI/ML": "#3498db",
}


def md_to_html(text):
    lines = text.split("\n")
    out = []
    in_list = False

    for line in lines:
        s = line.strip()
        if s.startswith("### ") or s.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            heading = re.sub(r"^#{2,3}\s+", "", s)
            out.append(
                f'<h3 style="color:#2c3e50;font-size:16px;margin:20px 0 8px;'
                f'border-bottom:1px solid #eee;padding-bottom:4px;">{heading}</h3>'
            )
        elif s.startswith("- "):
            if not in_list:
                out.append('<ul style="margin:8px 0;padding-left:20px;">')
                in_list = True
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s[2:])
            out.append(f'<li style="margin-bottom:6px;">{content}</li>')
        elif s == "":
            if in_list:
                out.append("</ul>")
                in_list = False
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            content = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
            content = re.sub(r"\*(.+?)\*", r"<em>\1</em>", content)
            out.append(f"<p style='margin:8px 0;'>{content}</p>")

    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def build_html(papers):
    date_str = datetime.now().strftime("%B %d, %Y")
    sections = []

    for i, p in enumerate(papers, 1):
        domain = p.get("domain", "AI/ML")
        color = DOMAIN_COLORS.get(domain, "#3498db")
        analysis_html = md_to_html(p.get("analysis", "[No analysis]"))
        authors_str = ", ".join(p.get("authors", []))
        pdf_link = (
            f' &nbsp;|&nbsp; <a href="{p["pdf_url"]}" style="color:{color};">PDF</a>'
            if p.get("pdf_url") else ""
        )

        sections.append(f"""
        <div style="background:#fff;border-radius:8px;padding:28px;margin-bottom:24px;border-left:4px solid {color};box-shadow:0 1px 3px rgba(0,0,0,0.08);">
            <div style="margin-bottom:8px;">
                <span style="background:{color};color:#fff;padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;">{domain.upper()}</span>
                <span style="color:#888;font-size:13px;margin-left:12px;">Paper #{i}</span>
            </div>
            <h2 style="color:#1a1a2e;margin:12px 0 8px;font-size:20px;line-height:1.3;">
                <a href="{p.get('url','')}" style="color:#1a1a2e;text-decoration:none;">{p['title']}</a>
            </h2>
            <p style="color:#666;font-size:14px;margin:0 0 4px;">
                <strong>Authors:</strong> {authors_str}
            </p>
            <p style="color:#666;font-size:14px;margin:0 0 16px;">
                <strong>Venue:</strong> {p.get('venue','')} ({p.get('year','')}) &nbsp;|&nbsp;
                <strong>Citations:</strong> {p.get('citations',0)} &nbsp;|&nbsp;
                <a href="{p.get('url','')}" style="color:{color};">Read Paper</a>{pdf_link}
            </p>
            <hr style="border:none;border-top:1px solid #eee;margin:16px 0;">
            <div style="color:#333;font-size:15px;line-height:1.7;">
                {analysis_html}
            </div>
        </div>""")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f4f4f8;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<div style="max-width:700px;margin:0 auto;padding:24px;">
    <div style="text-align:center;padding:32px 0 24px;">
        <h1 style="color:#1a1a2e;font-size:28px;margin:0 0 8px;">Weekly Research Digest</h1>
        <p style="color:#888;font-size:15px;margin:0;">Week of {date_str} &bull; {len(papers)} papers</p>
        <p style="color:#aaa;font-size:13px;margin:8px 0 0;">Top papers in AI, Robotics & Embedded Systems</p>
    </div>
    <div style="background:#e8f4f8;border-radius:8px;padding:16px 20px;margin-bottom:24px;font-size:14px;color:#2c6e7e;">
        <strong>This week's highlights:</strong> {len(papers)} papers from top venues, analyzed and summarized for quick reading. Each report is written to be understood without specialized knowledge.
    </div>
    {''.join(sections)}
    <div style="text-align:center;padding:24px 0;color:#aaa;font-size:12px;">
        <p>Generated by Paper Digest &bull; Powered by Claude</p>
    </div>
</div>
</body></html>"""


def send_email(html, papers):
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    recipient = os.getenv("EMAIL_RECIPIENT", "")
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))

    if not all([sender, password, recipient]):
        print("ERROR: Email credentials not configured in .env", file=sys.stderr)
        return False

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"Weekly Research Digest — {date_str}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Paper Digest <{sender}>"
    msg["To"] = recipient

    plain = "\n\n".join(
        f"#{i} {p['title']}\n{p.get('analysis', '')}"
        for i, p in enumerate(papers, 1)
    )
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)

    print(f"Email sent to {recipient}", file=sys.stderr)
    return True


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", help="Path to digest JSON")
    parser.add_argument("--preview", action="store_true", help="Save HTML locally")
    parser.add_argument("--open", action="store_true", help="Open preview in browser")
    args = parser.parse_args()

    with open(args.json_file) as f:
        papers = json.load(f)

    html = build_html(papers)
    date_str = datetime.now().strftime("%Y%m%d")

    if args.preview:
        out = Path(__file__).parent / f"preview_{date_str}.html"
        out.write_text(html)
        print(f"Preview saved: {out}", file=sys.stderr)
        if args.open:
            subprocess.run(["open", str(out)])
        return

    if send_email(html, papers):
        log_dir = Path(__file__).parent / "logs"
        log_dir.mkdir(exist_ok=True)
        (log_dir / f"digest_{date_str}.html").write_text(html)
        (log_dir / f"digest_{date_str}.json").write_text(json.dumps(papers, indent=2))


if __name__ == "__main__":
    main()
