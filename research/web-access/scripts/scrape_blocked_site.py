"""Scrape a DNS-blocked / geo-restricted website with Playwright.

Usage: python3 /tmp/scrape_blocked_site.py

This script:
1. Auto-resolves real IPs for the target domain via DNS-over-HTTPS
2. Fetches page HTML with curl --resolve to discover CDN dependencies
3. Checks if data is server-rendered (embedded JSON) — extracts and exits early if so
4. Resolves CDN domains for full rendering
5. Renders the SPA with Playwright + --host-resolver-rules (only if needed)
6. Extracts page title, full text content, and a screenshot

To adapt: change URL and DOMAIN at the top of the file.
"""
import asyncio
import json
import re
import subprocess
import sys
import urllib.request
from playwright.async_api import async_playwright

# ========== CONFIGURATION — EDIT THESE ==========
URL = "https://www.tianyancha.com/data/recharge/1"
DOMAIN = "www.tianyancha.com"  # the bare hostname (no https://)
# ================================================

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

DOH_SERVERS = [
    ("https://dns.google/resolve?name={domain}&type=A", "application/json"),
    ("https://cloudflare-dns.com/dns-query?name={domain}&type=A", "application/dns-json"),
]

# Patterns that indicate server-rendered data — BUT beware false positives.
# Google pages (Gemini/Bard) ALWAYS embed WIZ_global_data with DEMO content,
# not the actual page data. Those are false positives.
SSR_TRUSTED_PATTERNS = [
    r'__NEXT_DATA__',           # Next.js SSR — usually real data
    r'window\.__INITIAL_STATE__',  # React/Redux SSR — usually real
    r'window\.__NUXT__',        # Nuxt.js — usually real
    r'<script id="server-app-state"',  # Generic SSR
]

# Google pages: detected but NOT trusted (demo data, not real content)
SSR_DEMO_PATTERNS = [
    r'WIZ_global_data',         # Google pages — ALWAYS demo/preview data
]


def has_real_embedded_data(html: str) -> bool:
    """Check if the HTML contains server-rendered data that is LIKELY real.

    WIZ_global_data is excluded because Google pages embed demo content there.
    """
    return any(re.search(p, html) for p in SSR_TRUSTED_PATTERNS)


def is_google_page(html: str) -> bool:
    """Detect Google pages where WIZ_global_data is demo content."""
    return bool(re.search(r'WIZ_global_data', html))
        url = url_template.format(domain=domain)
        req = urllib.request.Request(url, headers={"Accept": accept})
        try:
            data = json.loads(urllib.request.urlopen(req, timeout=10).read())
            ips = [
                a["data"]
                for a in data.get("Answer", [])
                if a.get("type") == 1
            ]
            if ips:
                print(f"  {domain}: {ips}", file=sys.stderr)
                return ips
        except Exception as e:
            print(f"  {domain}: DoH failed ({type(e).__name__})", file=sys.stderr)
    return []


def extract_hostnames_from_html(html: str) -> set[str]:
    """Pull external hostnames from <script src>, <link href>, and <link rel=preconnect> tags."""
    hosts = set()
    # Standard absolute URLs in src/href
    for pattern in [
        r'(?:src|href)="https?://([^/"]+)',
        r"(?:src|href)='https?://([^/']+)",
    ]:
        hosts.update(re.findall(pattern, html))
    # Protocol-relative URLs (e.g. //www.gstatic.com)
    for pattern in [
        r'(?:src|href)="//([^/"]+)',
        r"(?:src|href)='//([^/']+)",
    ]:
        hosts.update(re.findall(pattern, html))
    # Keep only subdomains of the same base domain
    base_parts = DOMAIN.split(".")
    base_root = ".".join(base_parts[-2:]) if len(base_parts) >= 2 else DOMAIN
    related = {h for h in hosts if h.endswith(base_root)}
    return related


def curl_test(domain: str, ip: str, path: str) -> str:
    """Quick test: fetch HTML with curl --resolve."""
    url = f"https://{domain}{path}"
    cmd = [
        "curl", "-sL", "--max-time", "20",
        "--resolve", f"{domain}:443:{ip}",
        "-H", f"User-Agent: {UA}",
        "-H", "Accept-Language: zh-CN,zh;q=0.9",
        "-H", "Accept: text/html,application/xhtml+xml",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
    return result.stdout


def has_embedded_data(html: str) -> bool:
    """Check if the HTML already contains server-rendered structured data."""
    return any(re.search(p, html) for p in SSR_PATTERNS)


def extract_from_html(html: str) -> str:
    """Best-effort extraction of visible text content from HTML."""
    # Strip script/style tags
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL)
    # Extract title
    title_m = re.search(r'<title>(.+?)</title>', cleaned)
    title = title_m.group(1).strip() if title_m else "N/A"
    # Extract meta description
    desc_m = re.search(r'<meta\s+name="description"\s+content="([^"]*)"', cleaned)
    desc = desc_m.group(1) if desc_m else ""
    # Get body text
    body_m = re.search(r'<body[^>]*>(.*?)</body>', cleaned, flags=re.DOTALL)
    body = body_m.group(1) if body_m else cleaned
    # Remove remaining HTML tags
    text = re.sub(r'<[^>]+>', ' ', body)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return f"TITLE: {title}\nDESC: {desc}\n\nCONTENT:\n{text}"


async def main():
    # ---- Phase 1: Resolve main domain ----
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"Phase 1: Resolving {DOMAIN} via DoH...", file=sys.stderr)
    ips = resolve_domain(DOMAIN)
    if not ips:
        print("ERROR: Could not resolve main domain. Aborting.", file=sys.stderr)
        return
    main_ip = ips[0]

    # ---- Phase 2: Curl test + CDN discovery + SSR check ----
    print(f"\nPhase 2: Curl test with {main_ip}...", file=sys.stderr)
    path = URL.split(DOMAIN, 1)[1] if DOMAIN in URL else "/"
    html = curl_test(DOMAIN, main_ip, path)
    if not html:
        print("ERROR: curl returned empty. Check --resolve syntax or IP.", file=sys.stderr)
        return
    print(f"  Got {len(html)} bytes of HTML", file=sys.stderr)

    # ---- Phase 2.5: SSR fast path (only for trusted SSR, NOT Google) ----
    if is_google_page(html):
        print(f"\n  Google page detected — WIZ_global_data is demo data, not real content.", file=sys.stderr)
        print(f"  Proceeding with Playwright for actual data...", file=sys.stderr)
    elif has_real_embedded_data(html):
        print(f"\n  SSR DETECTED (trusted) — data embedded in HTML, skipping Playwright.", file=sys.stderr)
        content = extract_from_html(html)
        print(f"\n{'='*60}")
        print(content[:20000])
        if len(content) > 20000:
            print(f"\n... ({len(content) - 20000} more chars truncated)")
        print(f"\n{'='*60}", file=sys.stderr)
        print("Done (SSR fast path).", file=sys.stderr)
        return

    # Find CDN hostnames
    cdn_hosts = extract_hostnames_from_html(html)
    print(f"  CDN hosts found: {cdn_hosts if cdn_hosts else '(none)'}", file=sys.stderr)

    # ---- Phase 3: Resolve CDN domains ----
    print(f"\nPhase 3: Resolving CDN domains...", file=sys.stderr)
    host_rules = [f"MAP {DOMAIN} {main_ip}"]
    for cdn in cdn_hosts:
        cdn_ips = resolve_domain(cdn)
        if cdn_ips:
            host_rules.append(f"MAP {cdn} {cdn_ips[0]}")
        else:
            print(f"  WARNING: Could not resolve {cdn}", file=sys.stderr)

    print(f"  Host rules: {host_rules}", file=sys.stderr)

    # ---- Phase 4: Playwright render ----
    print(f"\nPhase 4: Playwright render...", file=sys.stderr)
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                f"--host-resolver-rules={','.join(host_rules)}",
            ],
        )
        context = await browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
        )
        page = await context.new_page()
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => false });
        """)

        print(f"  Navigating to {URL}...", file=sys.stderr)
        response = await page.goto(
            URL, wait_until="domcontentloaded", timeout=30000
        )
        print(f"  HTTP {response.status}", file=sys.stderr)
        print("  Waiting for SPA hydration (8s)...", file=sys.stderr)
        await asyncio.sleep(8)

        # ---- Phase 5: Extract content ----
        title = await page.title()
        text = await page.evaluate("() => document.body?.innerText || ''")
        print(f"\n{'='*60}")
        print(f"TITLE: {title}")
        print(f"\nPAGE CONTENT ({len(text)} chars):")
        print(text[:20000])
        if len(text) > 20000:
            print(f"\n... ({len(text) - 20000} more chars truncated)")

        try:
            await page.screenshot(
                path="/tmp/scraped_page.png", full_page=False, timeout=15000
            )
            print(f"\nSCREENSHOT: /tmp/scraped_page.png")
        except Exception as e:
            print(f"\nSCREENSHOT SKIPPED ({type(e).__name__}: {e})")

        await browser.close()

    print(f"\n{'='*60}", file=sys.stderr)
    print("Done.", file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
