"""
DATA-260 Homework 3 -- Corpus builder
Downloads 4 real public community-sports-league documents (one per sport
in DOMAIN_SCHEMA.md: soccer, basketball, volleyball, cricket), extracts
their text with pypdf, saves them as local .txt "snapshots", and
auto-generates CORPUS_MANIFEST.json (filename, byte size, SHA-256 hash)
plus a draft SOURCES.md.

We run this file from the repo root then the Output goes to reports/hw03/corpus/ (the local .txt snapshots) and
reports/hw03/ (CORPUS_MANIFEST.json, SOURCES.md draft).
"""

import hashlib
import json
from datetime import date
from pathlib import Path

import requests
from pypdf import PdfReader

# ---------------------------------------------------------------------
# Sources - verified real, public, fetchable PDFs, one per sport in
# your domain schema. Feel free to swap any of these for a different
# source if you prefer, as long as it's genuinely public and relevant.
# ---------------------------------------------------------------------
SOURCES = [
    {
        "sport": "soccer",
        "title": "AYSO Basic Soccer Rules (2009-2010 Edition)",
        "url": "https://dt5602vnjxv0c.cloudfront.net/portals/14501/docs/ayso_basic_soccer_rules.pdf",
        "local_name": "soccer_ayso_basic_rules.txt",
    },
    {
        "sport": "soccer",
        "title": "AYSO National Rules & Regulations (06/2018)",
        "url": "https://dt5602vnjxv0c.cloudfront.net/portals/14715/docs/national-rules-regulations-2018-0616-marked.pdf",
        "local_name": "soccer_ayso_national_rules.txt",
    },
    {
        "sport": "basketball",
        "title": "City of Las Vegas Youth Recreation Basketball Rules & Regulations",
        "url": "https://files.lasvegasnevada.gov/parks-recreation/CLV-Youth-Basketball-Rules.pdf",
        "local_name": "basketball_las_vegas_youth_rules.txt",
    },
    {
        "sport": "volleyball",
        "title": "City of Fort Collins Adult Volleyball Manual",
        "url": "https://www.fcgov.com/sports/pdf/2008vbmanagermanual.pdf",
        "local_name": "volleyball_fort_collins_manual.txt",
    },
    {
        "sport": "cricket",
        "title": "US Premier League (USPL) Twenty20 League Rules",
        "url": "https://www.cricuspl.com/wp-content/uploads/2022/05/twenty-20-rulebook-uspl.pdf",
        "local_name": "cricket_uspl_t20_rules.txt",
    },
    {
        "sport": "multi-sport (general community league policy)",
        "title": "Douglas County Parks & Recreation Adult Sports Leagues Rules & Guidelines",
        "url": "https://cdnsm5-hosted.civiclive.com/UserFiles/Servers/Server_12493019/File/Community%20Services/Recreation/Sports%20Leagues%20&%20Programs/Adult%20Sports/Valley/Volleyball/All%20Sports%20Rules%20and%20Guidlines.pdf",
        "local_name": "general_douglas_county_all_sports_rules.txt",
    },
]

REPO_ROOT = Path(__file__).resolve().parent
CORPUS_DIR = REPO_ROOT / "reports" / "hw03" / "corpus"
CORPUS_DIR.mkdir(parents=True, exist_ok=True)

TMP_DIR = REPO_ROOT / "reports" / "hw03" / "_tmp_pdfs"
TMP_DIR.mkdir(parents=True, exist_ok=True)


def download_pdf(url, dest_path):
    print(f"  Downloading {url} ...")
    resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    with open(dest_path, "wb") as f:
        f.write(resp.content)
    return len(resp.content)


def extract_text(pdf_path):
    reader = PdfReader(str(pdf_path))
    text_parts = []
    for page in reader.pages:
        text_parts.append(page.extract_text() or "")
    return "\n".join(text_parts)


def sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    manifest = []
    sources_lines = [
        "# SOURCES.md - HW3 Domain Corpus Sources\n",
        f"All sources accessed on {date.today().isoformat()}.\n",
        "Local text snapshots were extracted from the original PDFs using pypdf.\n\n",
    ]

    total_bytes = 0

    for src in SOURCES:
        print(f"\nProcessing: {src['title']}")
        pdf_path = TMP_DIR / (src["local_name"].replace(".txt", ".pdf"))
        download_pdf(src["url"], pdf_path)

        text = extract_text(pdf_path)
        txt_path = CORPUS_DIR / src["local_name"]
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)

        byte_size = txt_path.stat().st_size
        sha256 = sha256_of_file(txt_path)
        total_bytes += byte_size

        print(f"  Saved: {txt_path} ({byte_size:,} bytes)")
        print(f"  SHA-256: {sha256}")

        manifest.append({
            "filename": f"reports/hw03/corpus/{src['local_name']}",
            "sport": src["sport"],
            "title": src["title"],
            "source_url": src["url"],
            "byte_size": byte_size,
            "sha256": sha256,
        })

        sources_lines.append(f"## {src['title']}\n")
        sources_lines.append(f"- Sport: {src['sport']}\n")
        sources_lines.append(f"- Source URL: {src['url']}\n")
        sources_lines.append(f"- Access date: {date.today().isoformat()}\n")
        sources_lines.append(f"- Local file: reports/hw03/corpus/{src['local_name']}\n\n")

    manifest_path = REPO_ROOT / "reports" / "hw03" / "CORPUS_MANIFEST.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_corpus_bytes": total_bytes,
            "meets_200kb_requirement": total_bytes >= 200_000,
            "documents": manifest,
        }, f, indent=2)

    sources_path = REPO_ROOT / "reports" / "hw03" / "SOURCES.md"
    with open(sources_path, "w", encoding="utf-8") as f:
        f.writelines(sources_lines)

    print(f"\n{'='*60}")
    print(f"Total corpus size: {total_bytes:,} bytes ({total_bytes/1024:.1f} KB)")
    print(f"Meets 200KB requirement: {total_bytes >= 200_000}")
    print(f"CORPUS_MANIFEST.json written to: {manifest_path}")
    print(f"SOURCES.md written to: {sources_path}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()