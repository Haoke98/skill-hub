---
name: web-access
description: "Use when accessing web content from geo-blocked/DNS-poisoned environments, especially Chinese sites (tianyancha.com etc.) or JS-heavy SPAs that browser_navigate or curl can't reach."
version: 2.0.0
author: Hermes Agent
license: MIT
tags: [web, scraping, dns, china, playwright, curl, geo-blocking, spa, anti-bot]
---

# Web Access Skill

Access web resources from environments where DNS is poisoned, sites are
geo-blocked, or heavy JavaScript rendering is required. Covers the full
pipeline: DNS-over-HTTPS resolution → shell-level test with curl --resolve →
full SPA rendering with Playwright + host-resolver-rules.

Core insight: sites like tianyancha.com, baidu.com, and most Chinese SaaS
platforms operate behind DNS-based blocking. Bypassing DNS on the host machine
is the key — no proxy, no VPN, just accurate DNS.

## When to Use

- `browser_navigate` returns `net::ERR_TIMED_OUT` or `CDP command timed out`
- `curl` returns `HTTP_CODE 000` / exit code 28 (connection timeout)
- DNS resolves the target to `198.18.0.0/15` (benchmark reserved), `127.0.0.0/8`, or any IP with sub-1ms ping
- The page is a React/Next.js/Vue SPA that requires JavaScript to render content
- The page has anti-bot measures (webdriver detection, etc.)

**Do NOT use for:**
- Plain-text endpoints (`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`, `.xml`) — use `curl` directly
- APIs that return JSON — use `curl` or the `web_extract` tools
- Sites that work fine via `browser_navigate` — this skill is a fallback, not a default

## Prerequisites

- `playwright` Python package installed
- Chromium browser installed: `python3 -m playwright install chromium`
- Check: `ls ~/.cache/ms-playwright/chromium-*/chrome-linux` should succeed

## Procedure

### Step 1: Diagnose — is DNS poisoned?

When a site is unreachable, start with ping:

```bash
ping -c 3 -W 3 www.tianyancha.com
```

**Red flags (DNS is tampered):**
| Symptom | Meaning |
|---------|---------|
| IP in `198.18.0.0/15` | Benchmark testing reserved — DNS hijack |
| IP in `127.0.0.0/8` | Loopback — DNS hijack |
| RTT < 1ms to a remote site | Local intercept, not real Internet |
| RTT 150-300ms but curl times out | Geo-blocking at IP level, not DNS |

### Step 2: Resolve real IPs via DoH

Use DNS-over-HTTPS to get real IPs. Both Google and Cloudflare DoH work:

```bash
python3 -c "
import urllib.request, json

domain = 'www.tianyancha.com'  # CHANGE THIS
for doh_url in [
    'https://dns.google/resolve?name={d}&type=A',
    'https://cloudflare-dns.com/dns-query?name={d}&type=A',
]:
    headers = {'Accept': 'application/json'} if 'cloudflare' in doh_url else {'Accept': 'application/json'}
    req = urllib.request.Request(doh_url.format(d=domain), headers=headers)
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        ips = [a['data'] for a in data.get('Answer', []) if a.get('type') == 1]
        if ips:
            print(f'{domain}: {ips}')
            break
    except Exception as e:
        print(f'  {doh_url[:30]}... failed: {e}')
"
```

Always resolve a pool of CDN domains too. From the page's HTML `<script src="...">` and
`<link href="...">` tags, extract external hostnames. Common patterns:
- `cdn.example.com` — static assets (JS/CSS/images)
- `static.example.com` — same role
- `api.example.com` — backend API
- `sensorsapi.example.com` — analytics

Resolve each one with the same DoH snippet above.

### Step 3: Quick test with curl --resolve

Before the full browser, test whether the IP works:

```bash
curl -sL --max-time 20 \
  --resolve "www.tianyancha.com:443:116.205.76.100" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36" \
  -H "Accept-Language: zh-CN,zh;q=0.9" \
  -H "Accept: text/html,application/xhtml+xml" \
  "https://www.tianyancha.com/path" 2>&1 | head -200
```

**Interpreting the result:**
- **Empty output** — DNS still failing; double-check the `--resolve` syntax (must be `host:port:ip`)
- **HTML with actual text content** — server-rendered page, curl might be enough
- **HTML that's an SPA shell** (`<div id="app"></div>`, `<chat-app-orchestrator>`, etc.) — FIRST check for embedded data before going to Playwright:
  ```bash
  # Check if data is server-side rendered into the HTML
  curl ... | grep -oP '(WIZ_global_data|__NEXT_DATA__|window\.__INITIAL_STATE__|__NUXT__|id="__NEXT_DATA__")'
  ```
  If any of these patterns match, the data is embedded JSON in the HTML — extract it without Playwright.
  Only if no embedded data is found, proceed to Step 4.
- **401/403** — auth required or anti-bot blocking; Playwright is needed
- **Still timeout** — the real IP may also be geo-blocked at firewall level; this approach won't work

### Step 4: Check for embedded data vs. real content

Before launching Playwright, check if the HTML already contains the REAL data:

```bash
# Check for SSR markers
curl ... | grep -oP '(WIZ_global_data|__NEXT_DATA__|window\.__INITIAL_STATE__|__NUXT__)'
```

**BUT — detection alone is NOT enough.** Google pages (Gemini, Bard) always
embed `WIZ_global_data` in the HTML, but it contains default/demo content, NOT
the actual page data. The real conversation/share content is loaded dynamically.

**How to tell real data from demo data:**
1. After detecting SSR markers, extract the embedded text and compare against
   the `<title>` / `<meta name="description">` — if the extracted text doesn't
   match the page topic, it's placeholder/demo data.
2. For **Gemini share pages** specifically: `WIZ_global_data` is ALWAYS demo
   content. Always use Playwright.
3. For **Next.js pages**: `__NEXT_DATA__` usually IS the real data — but verify
   by checking if the data keys match the expected page content.

**Decision tree:**
| Page type | SSR marker | Contains real data? | Action |
|-----------|-----------|---------------------|--------|
| Gemini/Bard share | `WIZ_global_data` | ❌ Demo data always | Use Playwright |
| Next.js content pages | `__NEXT_DATA__` | ✅ Usually real | Extract from HTML |
| React/Redux apps | `__INITIAL_STATE__` | ✅ Usually real | Extract from HTML |
| Nuxt pages | `__NUXT__` | ✅ Usually real | Extract from HTML |

1. **Build `--host-resolver-rules`** from all resolved IPs (main domain + CDN domains)
2. **Launch Chromium** in headless mode with anti-detection flags
3. **Set realistic browser context**: Chinese locale, modern Chrome UA, 1080p viewport
4. **Navigate with `domcontentloaded`**, NOT `networkidle`
5. **Wait 8-15 seconds** for SPA hydration (React/Vue/Next.js)
6. **Extract `document.body.innerText`** for content
7. **Skip screenshot if external fonts block** (w3.org, Google Fonts)

Critical: **always use `wait_until="domcontentloaded"`**, never `"networkidle"`.
Chinese sites universally load analytics WebSocket/beacon connections (Baidu
Tongji, 7moor, Sensors Analytics) that never close, making `networkidle`
timeout every time at 30-45 seconds. Use `domcontentloaded` + a fixed
`asyncio.sleep(8)` for React hydration.

### Step 5: Extract and present

After the script runs, you'll have:
- Page title
- Full text content (up to 20,000 chars)
- Optionally a screenshot (if fonts loaded)

Parse the content and present the user a structured summary. For data-heavy
pages (pricing tables, API catalogs, search results), organize into sections
with headers, bullet points, or markdown tables.

## Anti-Bot Evasion

For sites with aggressive bot detection, stack these techniques:

```python
# 1. Hide webdriver flag
await page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
""")

# 2. Realistic browser context
context = await browser.new_context(
    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    viewport={"width": 1920, "height": 1080},
    locale="zh-CN",
    timezone_id="Asia/Shanghai",
)

# 3. Chromium launch flags
args=[
    "--no-sandbox",
    "--disable-blink-features=AutomationControlled",
    "--disable-dev-shm-usage",
]
```

If the site still blocks, try:
- Randomize viewport dimensions slightly (1910-1930 × 1060-1100)
- Add `--disable-gpu` flag
- Add a random delay (1-3s) before interacting
- Set `headless=False` if a display is available (rare in server environments)

## Common Pitfalls

1. **`wait_until="networkidle"` will ALWAYS timeout** on Chinese sites due to analytics
   beacons. Use `domcontentloaded` + fixed sleep. This is the #1 mistake.

2. **`WIZ_global_data` on Google pages is DEMO data, not real content.** Gemini and
   Bard pages embed default/example conversations in the HTML. Detecting `WIZ_global_data`
   tells you the page IS a Google page — but the actual conversation/share data is loaded
   dynamically. Always use Playwright for Gemini share pages.

3. **Missing CDN domains in host-resolver-rules.** The page's HTML loads JS/CSS from
   3-5 subdomains. If ANY of them are DNS-poisoned, the page won't render. Always
   `grep -oP '(?:src|href)="(?:https?:)?//[^/"]+'` the HTML from Step 3 to find them all.

4. **Font loading times out screenshots.** Chinese sites often load fonts from
   `w3.org` or Google Fonts. `page.screenshot()` waits for fonts to load and will
   timeout (~30s) when those domains are unreachable. Skip the screenshot if it
   fails — the `innerText` extraction is independent.

5. **`--resolve` requires port number.** `--resolve "host:443:ip"` not
   `--resolve "host:ip"`. Forgetting the port silently fails.

6. **IP addresses change.** The IPs in this skill and reference docs are snapshots
   from July 2026. Always run DoH resolution fresh — don't hardcode IPs from old
   sessions.

7. **curl with direct IP doesn't set SNI.** Using `https://<ip>/path` sends the
   wrong TLS SNI (the IP, not the hostname). Always use `--resolve` instead of
   replacing the hostname with the IP — `--resolve` keeps SNI intact.

8. **Don't waste time on `browser_navigate` retries.** If it fails once with
   `ERR_TIMED_OUT`, the DNS is poisoned. Switch to this skill immediately rather
   than retrying with different timeouts or headers.

9. **SSR markers ≠ guaranteed real data.** Google pages are a known false positive.
   For any SSR marker, verify: does the extracted content match the page's stated
   purpose (title, URL)? If not, treat as demo data and use Playwright.

## Support Files

- `scripts/scrape_blocked_site.py` — full Playwright script with auto DoH resolution.
  Copy to `/tmp/`, edit URL and host rules, run with `python3`.
- `references/dns-resolution.md` — DoH one-liners, common CDN domain IPs, red flags.

## Verification Checklist

- [ ] DNS poisoning confirmed via ping (wrong IP or sub-ms RTT)
- [ ] Real IPs resolved via DoH for main domain
- [ ] CDN domains identified from HTML and resolved
- [ ] curl `--resolve` test passes (HTTP 200, HTML returned)
- [ ] Playwright script runs with `domcontentloaded` (not `networkidle`)
- [ ] `document.body.innerText` contains rendered content (not just the SPA shell)
- [ ] Page title matches expected page
