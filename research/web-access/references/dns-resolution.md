# DNS-over-HTTPS Resolution Reference

## One-liner: resolve a single domain

```bash
python3 -c "
import urllib.request, json
domain = 'www.tianyancha.com'  # CHANGE THIS
req = urllib.request.Request(
    f'https://dns.google/resolve?name={domain}&type=A',
    headers={'Accept': 'application/json'}
)
data = json.loads(urllib.request.urlopen(req, timeout=10).read())
for a in data.get('Answer', []):
    if a.get('type') == 1:
        print(a['data'])
"
```

## One-liner: resolve multiple domains at once

```bash
python3 -c "
import urllib.request, json

domains = ['www.tianyancha.com', 'tyc-fe-cdn.tianyancha.com', 'sensorsapi.tianyancha.com']

for domain in domains:
    req = urllib.request.Request(
        f'https://dns.google/resolve?name={domain}&type=A',
        headers={'Accept': 'application/json'}
    )
    try:
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())
        ips = [a['data'] for a in data.get('Answer', []) if a.get('type') == 1]
        print(f'{domain}: {ips}')
    except Exception as e:
        print(f'{domain}: ERROR - {e}')
"
```

## DNS-over-HTTPS providers

| Provider | URL | Accept header | Notes |
|----------|-----|---------------|-------|
| Google | `https://dns.google/resolve?name=<domain>&type=A` | `application/json` | Most reliable |
| Cloudflare | `https://cloudflare-dns.com/dns-query?name=<domain>&type=A` | `application/dns-json` | Good fallback |

## Curl --resolve quick test

```bash
curl -sL --max-time 20 \
  --resolve "www.tianyancha.com:443:116.205.76.100" \
  -H "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36" \
  -H "Accept-Language: zh-CN,zh;q=0.9" \
  "https://www.tianyancha.com/path" 2>&1 | head -200
```

**Key detail:** `--resolve "host:PORT:ip"` — the port is REQUIRED. For HTTPS it's `443`.
Omitting the port silently fails (curl connects to the old DNS-resolved IP).

## Discovering CDN domains from HTML

After getting HTML from curl, grep for external resource hosts.
**Important:** modern sites use protocol-relative URLs (`//cdn.example.com`),
not just `https://`. Use both patterns:

```bash
# Absolute URLs
grep -oP '(?:src|href)="https?://[^/"]+' html_output
# Protocol-relative URLs (e.g. //www.gstatic.com)
grep -oP '(?:src|href)="//[^/"]+' html_output
```

## SSR / embedded data: check before launching Playwright

Many pages ship data in the initial HTML. But **detection alone is not enough** —
verify that the embedded data is REAL, not demo/placeholder content.

| Pattern | Framework | Trust? | Notes |
|---------|-----------|--------|-------|
| `WIZ_global_data` | Google (Gemini, Bard) | ❌ NO | Always demo/preset data. Use Playwright. |
| `__NEXT_DATA__` | Next.js | ✅ Usually | Verify by checking data keys |
| `window.__INITIAL_STATE__` | React/Redux | ✅ Usually | Verify by checking data keys |
| `window.__NUXT__` | Nuxt.js | ✅ Usually | Verify by checking data keys |

**Verification trick:** Extract the `<title>` and `<meta name="description">` from
HTML. If the title says "Gemini - 直接体验 Google AI 黑科技" but the embedded
data talks about Barcelona parks — that's demo content, not your page.

## DNS poisoning red flags

| Symptom | Cause |
|---------|-------|
| IP in `198.18.0.0/15` | IANA Benchmarking reserved — DNS hijacked |
| IP in `127.0.0.0/8` | Loopback — DNS hijacked |
| Ping RTT < 1ms to a remote host | Local intercept, not real Internet |
| Ping works (200ms RTT) but HTTPS fails | SNI-based blocking or geo-IP firewall |

## Known CDN domain patterns (snapshot — always re-resolve)

**tianyancha.com:**
| Domain | Role |
|--------|------|
| `www.tianyancha.com` | Main site |
| `tyc-fe-cdn.tianyancha.com` | Frontend CDN (Next.js bundles, CSS) |
| `sensorsapi.tianyancha.com` | Analytics (Sensors Data) |
| `open.tianyancha.com` | API platform |

**Google (gemini.google.com, *.google.com):**
| Domain | Role |
|--------|------|
| `www.gstatic.com` | Static assets (fonts, images, icons) |
| `fonts.gstatic.com` / `fonts.googleapis.com` | Web fonts |
| `ssl.gstatic.com` | Secure static assets |
| `lh3.googleusercontent.com` | User content / images |
| `gemini.gstatic.com` | Gemini-specific bundles |
| `www.googletagmanager.com` | GTM / analytics |
| `waa-pa.clients6.google.com` | Google internal RPC |
| `ogads-pa.clients6.google.com` | Google Ads RPC |
