# Fetcher: browser-harness

`BrowserHarnessFetcher` routes AWC's URL fetches through
[browser-harness](https://github.com/browser-use/browser-harness) — a minimal
CDP helper that attaches to **the user's own running Chrome**.

## Why

| | `HTTPFetcher` (default) | `PlaywrightFetcher` | **`BrowserHarnessFetcher`** |
|---|:-:|:-:|:-:|
| Logged-in sessions | ✗ | ✗ (fresh profile) | **✓** — reuses your cookies, SSO, SaaS auth |
| Fingerprint | Anonymous UA | "Automation" signal | **✓** — real user Chrome |
| Cold-start | — | ~1.5s/page | **0ms** — persistent daemon |
| Screenshot | ✗ | Full-page PNG | Full-page PNG |
| Handles SPAs | ✗ | ✓ | ✓ |

Use this fetcher whenever a target needs login state (LinkedIn, Gmail, Jira,
Shopify admin) or when you want the real browser fingerprint rather than a
clean-room Chromium.

## Install

```bash
pip install "agent-web-compiler[harness]"
```

Then follow the BH setup prompt to connect to your Chrome
(see the [BH README](https://github.com/browser-use/browser-harness#setup-prompt)).
On first `fetch_sync` BH's daemon will auto-start and attach over the CDP
websocket you approved.

## Three usage surfaces

### 1. Via `compile_url`

```python
from agent_web_compiler import compile_url

doc = compile_url(
    "https://app.linkedin.com/in/me",
    fetcher="browser_harness",
)
```

### 2. Via `PipelineBuilder`

```python
from agent_web_compiler import PipelineBuilder

pipeline = (
    PipelineBuilder()
    .with_fetcher("browser_harness", bu_name="awc", wait_after_load_ms=2000)
    .build()
)
doc = pipeline.compile_url("https://docs.stripe.com/api")
```

### 3. Directly

```python
from agent_web_compiler.sources.browser_harness_fetcher import BrowserHarnessFetcher
from agent_web_compiler.core.config import CompileConfig

fetcher = BrowserHarnessFetcher(bu_name="awc")
result = fetcher.fetch_sync("https://example.com", CompileConfig())

print(result.content[:200])
print(result.metadata["page_title"])
print(result.metadata["viewport"])         # {"w": 1280, "h": 720}
print(result.metadata["screenshot_png"])   # PNG bytes
```

### 4. CLI

```bash
awc compile https://app.linkedin.com/in/me --fetcher browser_harness
```

## Parameters

| Name | Default | Purpose |
|---|---|---|
| `bu_name` | `"awc"` | Maps to BH's `BU_NAME` env var — selects the daemon/browser session. Each distinct value is a separate isolated session. |
| `wait_after_load_ms` | `1500` | Extra wait after `wait_for_load()` returns — gives React/Vue SPAs time to hydrate past `readyState==complete`. |
| `capture_screenshot` | `True` | Attach PNG bytes to `result.metadata["screenshot_png"]`. Turn off for bulk crawls. |
| `activate_tab` | `False` | Call `Target.activateTarget` so the user sees which tab AWC operates on. |

## Returned metadata

`fetch_sync` returns a `FetchResult` whose `metadata` dict includes:

- `renderer`: `"browser-harness"`
- `bu_name`: the session name
- `response_time_s`: total wall time
- `ready_state_complete`: `True` if `document.readyState === "complete"` was reached
- `page_title`, `viewport`, `scroll`, `page_size`
- `screenshot_png`: PNG bytes (if `capture_screenshot=True`)
- `needs_rendering`: `False` — the HTML is already fully rendered

## Design constraints

1. **Lazy import** — BH is an *optional* dependency. `from
   agent_web_compiler.sources.browser_harness_fetcher import
   BrowserHarnessFetcher` never imports `browser_harness` itself; the first
   `fetch_sync` call is where we actually `from browser_harness import helpers`.
2. **No daemon management** — AWC never spawns/stops the BH daemon. BH's own
   `ensure_daemon()` handles this lazily. AWC is a pure consumer.
3. **Scheme guard** — only `http://` and `https://` are accepted. BH's
   `new_tab` would accept `about:` / `file:` but those would leak the user's
   active session in surprising ways.
4. **No global state** — we only `os.environ.setdefault("BU_NAME", ...)`, so an
   outer BH session that already set `BU_NAME` wins.

## Error model

- BH not installed → `FetchError("browser-harness is not installed. ...")`
- Unsupported URL scheme → `FetchError`
- Native dialog blocking the JS thread → `RenderError`
- Any other BH runtime failure → `RenderError` (wrapped, with context)

## Caveats

- BH does not expose HTTP status codes; `result.status_code` is always `200`
  on success. Non-2xx server responses still land on the page and the HTML
  still compiles — downstream consumers should check the rendered content,
  not the status.
- The tab is created with `new_tab`, **not** `goto_url`, on purpose:
  BH's `SKILL.md` warns that `goto_url` would clobber whatever the user is
  currently viewing.
