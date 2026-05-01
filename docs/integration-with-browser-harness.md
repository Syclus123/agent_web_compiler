# agent-web-compiler × browser-harness 深度融合方案

> 把"**理解网页**"和"**驱动浏览器**"这两件事接在一起，做成 Agent Web 时代的**双向基础设施**。

---

## 0. 一句话结论

- **`agent-web-compiler` (AWC)** 是一个**静态 + 结构化**的"**Agent Web 编译器**"：把人类网页 → Agent 原生对象（blocks / actions / state-machine / 证据 / llms.txt）。
- **`browser-harness` (BH)** 是一个**动态 + 最小化**的"**CDP 裸连接执行器**"：把 LLM 直接贴到用户真实 Chrome，按需手写 helper，在实战中自我进化。
- 两者并非竞品，而是**天然互补**：
  - **AWC 缺真实浏览器执行闭环** → BH 正好是最薄的那层。
  - **BH 缺页面语义理解和可验证证据链** → AWC 正好是最强的那层。
- 推荐策略：**不 fork、不兼并，做"桥接层 + 双向贡献"**。具体表现为：
  1. AWC 新增一个 `runtime/browser_harness/` 子包，让 AWC 的 `ActionGraph` / `HybridExecutor` / `BrowserMiddleware` 可以直接在真实浏览器里跑；
  2. 为 BH 生态贡献一个**由 AWC 自动生成的 domain-skill**（让 AWC 成为 BH 的"skill 编译器"，参考 BH 的 "Bitter Lesson" 思想）；
  3. 输出一个**全新的顶层入口** `awc.live` —— 把"Compile → Index → Act"从静态闭环升级为**在线闭环**。

---

## 1. 双方定位对比

| 维度 | agent-web-compiler | browser-harness |
|---|---|---|
| **核心抽象** | `AgentDocument`（blocks / actions / evidence） | `cdp(method, **params)` 原始 CDP 调用 |
| **哲学** | 预编译 + 可验证 + 可发布 | 运行时 + 最薄封装 + 自进化 |
| **代码规模** | ~40K LOC，77 模块，23 包 | ~592 行核心（`helpers.py` + `daemon.py` + `admin.py`） |
| **面向对象** | 开发者 / 数据管线 / 搜索引擎 | LLM Agent 自己（Claude Code、Codex） |
| **知识沉淀方式** | `SiteMemory` 在 Python 层（数据结构 + JSON 持久化） | `agent-workspace/domain-skills/*.md`（Markdown，由 agent 自己写） |
| **输入** | HTML / PDF / DOCX / URL / Playwright 渲染 | 用户真实 Chrome 的 CDP websocket |
| **输出** | `AgentDocument` + 7 种产物（llms.txt/agent.json/...） | 执行副作用（点击、填表、下载、截图） |
| **执行模型** | `HybridExecutor.decide()`：API > browser，仅"决策"不"执行" | 直接按像素点 `click_at_xy`，直接 `http_get`，直接 `js(...)` |
| **浏览器层** | 启动自己的 headless Playwright（隔离环境） | 连用户已登录的 Chrome（带身份、带 cookie） |
| **扩展机制** | `PipelineBuilder` 17 个扩展点 + 插件协议 | `agent-workspace/agent_helpers.py`（agent 直接改代码） |
| **典型缺失** | 无法真的去"点"一下；Playwright 环境与用户真实会话隔离 | 无语义块、无证据链、无跨页记忆、无 llms.txt 发布 |

关键洞察：**AWC 的 `HybridExecutor.decide()` 输出的是一个"怎么执行"的决策**，但它没有真正的执行引擎——文档里说 "API-first, browser-fallback"，可 browser-fallback 这条腿目前只能回退到 Playwright 隔离环境。**BH 正好是那条"真实浏览器腿"**，而且是零样板的。

---

## 2. 两者的根本差异（必须尊重的边界）

在做融合前，必须先理解对方为什么**刻意不做**某些东西。这关系到融合方案能不能被上游接受。

### 2.1 BH 的"Bitter Lesson"式设计约束（来自 `SKILL.md`）

BH 的 `Design constraints` 有一段非常强硬的声明：

> - Don't add a manager layer. No retries framework, session manager, daemon supervisor, config system, or logging framework.
> - Core helpers stay short. Put task-specific helper additions in `agent-workspace/agent_helpers.py`.
> - Screenshots first. Coordinate clicks default.

含义：**BH 拒绝"框架化"**。如果 AWC 想"接管" BH，把它包进一个 `CompilerAwareHarness(BrowserHarness)` 的大类里，**几乎一定不会被上游合并**。

**正确姿势**：AWC 只能"**使用** BH"，不能"**改造** BH"。所有的抽象和胶水都必须留在 AWC 这边；给 BH 的 PR 只能是**一个由 AWC 生成的 domain-skill**（markdown 文件）。

### 2.2 AWC 的"可验证 / 可发布"式设计约束

AWC 的 `ProvenanceEngine`、`llms.txt`、`agent-sitemap.xml` 明确把**可审计、可复用、可索引**作为一等公民。BH 则完全不在乎这些——它的口号是 "one websocket to Chrome, nothing between"。

**含义**：AWC 如果要用 BH 当执行层，**不能丢掉自己的证据链**。每一次通过 BH 执行的 action 都必须回写到 `EvidenceRecord`，把 BH 的截图、DOM 快照、网络调用包装成 AWC 的 `StateTransition`。

---

## 3. 结合点全景图

```
           ┌────────────────────────────────────────────────┐
           │             用户真实 Chrome (CDP)              │
           └───────────────────────┬────────────────────────┘
                                   │
                          ┌────────▼────────┐
                          │  browser-harness │  ← 执行层
                          │   (裸 CDP helper) │
                          └────────┬────────┘
                                   │ new_tab / click_at_xy / js / http_get / capture_screenshot
                                   │
  ┌────────────────────────────────▼──────────────────────────────────────┐
  │   AWC-BH Bridge  (awc.runtime.browser_harness) ← 新增                  │
  │                                                                        │
  │   ┌──────────────┐   ┌──────────────┐   ┌──────────────────────────┐ │
  │   │ LiveCompiler │   │ ActionRouter │   │  SkillCompiler           │ │
  │   │ (DOM→Doc)    │   │ (hybrid exec)│   │ (Doc→domain-skills/*.md) │ │
  │   └──────┬───────┘   └──────┬───────┘   └───────────┬──────────────┘ │
  └──────────┼──────────────────┼──────────────────────┼─────────────────┘
             │                  │                      │
         AgentDocument   ExecutionDecision          Markdown skill
             │                  │                      │
  ┌──────────▼──────────┐  ┌────▼────────────┐  ┌──────▼───────────┐
  │  AWC 现有 6 大能力   │  │ HybridExecutor   │  │ BH 的 domain-    │
  │  Compile/Index/Search│  │ （已有决策）     │  │ skills/ 生态     │
  │  Prove/Remember/Publish│ │                 │  │ （PR 贡献回上游）│
  └─────────────────────┘  └─────────────────┘  └──────────────────┘
```

---

## 4. 五个具体结合方案（按优先级）

### 方案 A ★★★★★｜`BrowserHarnessFetcher` —— 用真实浏览器做渲染源

**痛点**：AWC 当前的 `PlaywrightFetcher` 启动独立 headless Chrome，带来三个问题：
1. 没有用户的登录态 → 抓不到 LinkedIn、Gmail、SaaS 后台这类登录墙后的页面；
2. 指纹太干净 → 容易被反爬；
3. 冷启动开销大（每页都 launch/close）。

**方案**：新增一个 `agent_web_compiler/sources/browser_harness_fetcher.py`，实现 `FetchResult` 接口，底层调用 BH。

```python
# agent_web_compiler/sources/browser_harness_fetcher.py
from agent_web_compiler.core.interfaces import FetchResult
from agent_web_compiler.core.config import CompileConfig

class BrowserHarnessFetcher:
    """Fetch using user's real Chrome via browser-harness.

    Advantages over PlaywrightFetcher:
    - Uses user's actual logged-in session (SaaS, LinkedIn, Gmail).
    - No browser launch overhead (daemon persists).
    - Real user-agent / fingerprint — no bot detection.
    """

    def __init__(self, bu_name: str = "awc"):
        import os
        os.environ.setdefault("BU_NAME", bu_name)
        # Lazy import — BH is optional
        from browser_harness import helpers as bh
        self._bh = bh

    def fetch_sync(self, url: str, config: CompileConfig) -> FetchResult:
        bh = self._bh
        bh.new_tab(url)
        bh.wait_for_load(timeout=config.timeout_seconds)
        info = bh.page_info()
        html = bh.js("document.documentElement.outerHTML")
        screenshot_path = bh.capture_screenshot()
        with open(screenshot_path, "rb") as f:
            screenshot_png = f.read()
        return FetchResult(
            content=html,
            content_type="text/html",
            url=info["url"],
            status_code=200,
            headers={},
            metadata={
                "renderer": "browser-harness",
                "screenshot_png": screenshot_png,
                "page_title": info["title"],
                "viewport": {"w": info["w"], "h": info["h"]},
                "scroll": {"x": info["sx"], "y": info["sy"]},
                "page_size": {"w": info["pw"], "h": info["ph"]},
            },
        )
```

再注册到 `PipelineBuilder`：

```python
pipeline = (
    PipelineBuilder()
    .with_fetcher("browser_harness")  # 新增枚举值
    .build()
)
doc = pipeline.compile_url("https://linkedin.com/in/someone")
# 现在带着用户登录态拿到的 HTML 进了 AWC 的 8 阶段流水线
```

**价值**：一行配置，让 AWC 获得"真实用户会话"数据源。尤其在抓取 SaaS 后台生成 `llms.txt` 时极其关键。

---

### 方案 B ★★★★★｜`LiveActionExecutor` —— 让 HybridExecutor 真的能"按"下去

**痛点**：`HybridExecutor.decide()` 产出的 `ExecutionDecision` 只说"应该用 API" 或"应该用 browser"，但没有真的执行。当前 `mode=="browser"` 这条路没有后端。

**方案**：新增 `agent_web_compiler/runtime/browser_harness/live_executor.py`，把 Decision 翻译成 BH 的调用：

```python
# agent_web_compiler/runtime/browser_harness/live_executor.py
from __future__ import annotations
import time
from dataclasses import dataclass
from agent_web_compiler.actiongraph.hybrid_executor import ExecutionDecision
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument
from agent_web_compiler.actiongraph.models import StateTransition, NetworkRequest

@dataclass
class LiveExecutionResult:
    action_id: str
    mode_used: str   # "api" | "browser" | "skipped"
    success: bool
    transition: StateTransition | None
    network_calls: list[NetworkRequest]
    screenshot_path: str | None
    error: str | None = None

class LiveActionExecutor:
    """Executes HybridExecutor decisions against a real browser via BH.

    - mode=api       -> http_get/POST via bh.http_get
    - mode=browser   -> selector → coordinate click via bh.click_at_xy / js
    - mode=confirm   -> raise ConfirmationRequired unless auto_confirm
    - mode=skip      -> no-op, logs reason

    Every execution produces a StateTransition that feeds back into
    ActionGraphBuilder and ProvenanceEngine (evidence chain).
    """

    def __init__(self, *, bu_name: str = "awc", auto_confirm: bool = False):
        import os
        os.environ.setdefault("BU_NAME", bu_name)
        from browser_harness import helpers as bh
        self._bh = bh
        self.auto_confirm = auto_confirm

    def execute(
        self,
        decision: ExecutionDecision,
        action: Action,
        doc: AgentDocument,
    ) -> LiveExecutionResult:
        bh = self._bh
        state_before = self._snapshot(doc)
        t0 = time.time()

        if decision.mode == "skip":
            return LiveExecutionResult(action.id, "skipped", False, None, [], None,
                                       error=decision.reason)

        if decision.mode == "confirm" and not self.auto_confirm:
            return LiveExecutionResult(action.id, "skipped", False, None, [], None,
                                       error=f"confirm required: {decision.reason}")

        # ── API path ──────────────────────────────────────────────
        if decision.mode == "api" and decision.api_candidate:
            call = decision.api_candidate  # { method, endpoint, headers, params }
            try:
                if call.method == "GET":
                    body = bh.http_get(call.endpoint, headers=call.headers_pattern)
                else:
                    # delegate to bh.js fetch() for POST/PUT (BH doesn't wrap these)
                    body = bh.js(f"""
                        return fetch({call.endpoint!r}, {{method:{call.method!r},
                                                         headers:{call.headers_pattern!r},
                                                         body: {call.params_schema!r}}})
                               .then(r => r.text());
                    """)
                return LiveExecutionResult(
                    action.id, "api", True, None,
                    [NetworkRequest(url=call.endpoint, method=call.method,
                                    response_status=200, timestamp=t0,
                                    triggered_by_action=action.id)],
                    None,
                )
            except Exception as e:
                # graceful degradation to browser
                decision = ExecutionDecision(action.id, "browser",
                                             reason=f"API failed: {e}", confidence=0.3)

        # ── Browser path ──────────────────────────────────────────
        try:
            self._execute_in_browser(action)
            bh.wait_for_load(timeout=10.0)
            shot = bh.capture_screenshot()
            state_after = self._snapshot_from_live()
            transition = StateTransition(
                transition_id=f"t_{action.id}_{int(t0*1000)}",
                from_state_id=state_before.state_id,
                action_id=action.id,
                to_state_id=state_after["state_id"],
                effect_type=self._classify_effect(state_before, state_after),
                dom_changed=state_before.dom_hash != state_after["dom_hash"],
                url_changed=state_before.url != state_after["url"],
            )
            return LiveExecutionResult(action.id, "browser", True, transition, [], shot)
        except Exception as e:
            return LiveExecutionResult(action.id, "browser", False, None, [], None,
                                       error=str(e))

    # ── Action → BH call ──────────────────────────────────────────
    def _execute_in_browser(self, action: Action) -> None:
        bh = self._bh
        sel = action.selector

        if action.type == ActionType.NAVIGATE and action.state_effect:
            bh.new_tab(action.state_effect.target_url)
            return

        # Resolve selector → coordinates (BH's preferred mode)
        rect = bh.js(f"""
            const e = document.querySelector({sel!r});
            if (!e) return null;
            e.scrollIntoView({{block:'center'}});
            const r = e.getBoundingClientRect();
            return {{x: r.x + r.width/2, y: r.y + r.height/2}};
        """)
        if rect is None:
            raise RuntimeError(f"selector not found: {sel}")

        if action.type in (ActionType.CLICK, ActionType.SUBMIT,
                           ActionType.TOGGLE, ActionType.DOWNLOAD):
            bh.click_at_xy(rect["x"], rect["y"])
        elif action.type == ActionType.INPUT:
            bh.click_at_xy(rect["x"], rect["y"])
            bh.type_text(action.value_schema.get("default", "") if action.value_schema else "")
        elif action.type == ActionType.SELECT:
            bh.js(f"document.querySelector({sel!r}).value = "
                  f"{action.value_schema.get('default', '')!r}; "
                  f"document.querySelector({sel!r}).dispatchEvent(new Event('change'));")
        elif action.type == ActionType.UPLOAD:
            bh.upload_file(sel, action.value_schema.get("file_path", ""))
        else:
            # fallback: just click
            bh.click_at_xy(rect["x"], rect["y"])

    def _snapshot(self, doc: AgentDocument): ...   # 省略：复用 graph_builder 里的 PageState 构造
    def _snapshot_from_live(self): ...
    def _classify_effect(self, before, after) -> str: ...
```

**价值**：这是**真正把 AWC 从"编译器"升级成"可执行 Agent"**的关键一步。它让下面这行变成现实：

```python
from agent_web_compiler import AgentSearch, LiveRuntime

search = AgentSearch()
doc = search.ingest_url("https://app.linkedin.com/messaging")  # ← via BH（方案 A）
runtime = LiveRuntime(doc)  # ← 方案 B
runtime.run("reply to Alice with 'Thanks, will review today'")
# 内部：search.plan() → HybridExecutor.decide_all() → LiveActionExecutor.execute()
#      全程带 provenance，一切可审计
```

---

### 方案 C ★★★★☆｜`SkillCompiler` —— 让 AWC 成为 BH domain-skills 的"编译器"

这是最有影响力的一个点，直接呼应 BH 的 Bitter Lesson 博客："**Web Agents That Actually Learn**"。

**观察**：
- BH 的 domain-skill 是**由 agent 自己写的 markdown**，记录"这个网站的 API 形状、稳定选择器、框架怪癖、陷阱"。
- AWC 的 `SiteMemory` + `ActionGraphBuilder` + `APISynthesizer` **已经自动提取了这些信息**，只是以 Python 对象形式存着，没有输出成 markdown。

**方案**：给 AWC 加一个新的 publisher：`DomainSkillPublisher`。

```python
# agent_web_compiler/publisher/domain_skill.py
from agent_web_compiler.memory.site_memory import SiteInsight
from agent_web_compiler.actiongraph.models import APICandidate

class DomainSkillPublisher:
    """Generate a browser-harness-compatible domain-skill markdown from AWC artifacts.

    Output layout mirrors agent-workspace/domain-skills/<site>/<task>.md.
    """

    def __init__(self, site_insight: SiteInsight,
                 api_candidates: list[APICandidate],
                 action_graph):
        self.insight = site_insight
        self.apis = api_candidates
        self.graph = action_graph

    def generate(self, task: str = "scraping") -> str:
        lines = [f"# {self.insight.domain} — {task.replace('-', ' ').title()}", ""]
        lines += [f"`https://{self.insight.domain}` — "
                  f"{self.insight.pages_observed} pages observed, "
                  f"{'auth required' if self.insight.login_required else 'public'}.", ""]

        # Do this first — prefer APIs
        if self.apis:
            lines += ["## Do this first", "",
                      "**Use these APIs discovered by awc — no browser needed.**", "", "```python"]
            for api in self.apis[:5]:
                lines += [f"# {api.derived_from_action_id} (confidence={api.confidence:.2f})",
                          f"data = http_get({api.endpoint!r})"]
            lines += ["```", ""]

        # Stable selectors from site memory
        if self.insight.main_content_selector:
            lines += ["## Stable selectors", "",
                      f"- main content: `{self.insight.main_content_selector}`"]
            for sel in self.insight.noise_selectors[:10]:
                lines += [f"- noise (skip): `{sel}`"]
            lines += [""]

        # URL patterns
        if self.insight.entry_points:
            lines += ["## URL patterns", ""]
            for ep in self.insight.entry_points:
                lines.append(f"- `{ep}`")
            lines += [""]

        # Common actions
        if self.insight.common_actions:
            lines += ["## Common workflows", ""]
            for act in self.insight.common_actions[:5]:
                lines += [f"### {act.get('label')}", "```python",
                          f"# {act.get('selector')} — {act.get('type')}", "```", ""]

        # Gotchas from quality.warnings aggregated across pages
        lines += ["## Gotchas", "",
                  "<!-- filled in by agent after a successful live run -->", ""]
        return "\n".join(lines)

    def write_pr(self, bh_repo: str, site_slug: str, task: str = "scraping") -> Path:
        """Write to agent-workspace/domain-skills/<site>/<task>.md, ready for PR."""
        import pathlib
        p = pathlib.Path(bh_repo) / "agent-workspace" / "domain-skills" / site_slug / f"{task}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.generate(task))
        return p
```

用法：

```bash
awc publish bh-skill https://docs.stripe.com/api --out ~/code/browser-harness
# → 在 BH 仓库里生成 agent-workspace/domain-skills/stripe/scraping.md
```

**战略价值**（这是让你项目"被看见"的最关键一招）：
1. **把 AWC 塞进 BH 的核心生态位**：BH 的 README 明确写 "The best way to help: contribute a new domain skill"。AWC 可以**自动给 BH 生成 skill PR**。
2. **每一个 AWC 用户都可能给 BH 贡献代码**，AWC 的 logo / 署名自然出现在 BH 的 PR 列表里。
3. **反向也成立**：BH 的 80 多个 domain-skills 是**免费的监督信号**——AWC 可以拿这些 markdown 去反向训练/校验自己的 `SiteMemory`（"我自动生成的 skill 和人写的差距多大？"）。

---

### 方案 D ★★★★☆｜`BrowserMiddleware` 直接把 BH 当执行器

AWC 已经有 `BrowserMiddleware`，目前只是个**抽象的 translate_action**（返回 dict），没有真正执行。直接把它的 `translate_action` 升级成 `execute_action`：

```python
# agent_web_compiler/middleware/browser_middleware.py （补丁）
class BrowserMiddleware:
    def __init__(self, *, executor: LiveActionExecutor | None = None, ...):
        self.executor = executor  # optional live backend

    def execute_action(self, action_id: str) -> dict:
        cmd = self.translate_action(action_id)
        if self.executor is None:
            return cmd  # backwards-compatible: just return the plan
        action = self._find_action(action_id)
        # build a one-off decision that forces browser mode
        from agent_web_compiler.actiongraph.hybrid_executor import ExecutionDecision
        dec = ExecutionDecision(action_id=action_id, mode="browser",
                                reason="middleware direct", confidence=action.confidence)
        return self.executor.execute(dec, action, self._current_doc).__dict__
```

**价值**：OpenAI CUA / Claude Computer Use / Browser Use 这些外部 agent 框架在 AWC 里已有 adapter，它们 LLM 选好 `action_id` 后，**中间件可以直接用 BH 落地**。对上层看不出来差别，对下层 BH 贡献了一个真实的、带证据链的用户。

---

### 方案 E ★★★☆☆｜双向跨文件格式支持（llms.txt ⇄ domain-skills）

现在 BH 的 agent 启动时会在 `goto_url` 里检查 `domain-skills/<host>/*.md` 并列给 LLM（见 `helpers.py` 的 `goto_url` 末尾）。这是一个**可以双向利用的钩子**：

1. **AWC 读 BH 的 domain-skill**：当 `AgentSearch.ingest_url` 的目标域名在 BH 有 skill 时，把 markdown 注入到 `CompileConfig.hints`，用来指导 `boilerplate_remover` 和 `action_extractor`（比如 github/scraping.md 提到 `article.Box-row`，AWC 就直接把它加入"高价值选择器"白名单）。
2. **BH 读 AWC 的 llms.txt**：BH 的 agent 本来就要读 markdown；`awc publish` 产出的 `llms.txt` + `actions.json` 是现成的、结构化的喂养。`goto_url` 改成：优先查 `domain-skills/`，没有就 fetch 目标网站的 `/llms.txt`。

这在两边都是很小的改动，但**把 llms.txt 标准真正送进一个活跃的 agent 生态**。这是 AWC 对 llms.txt 社区最有说服力的使用案例。

---

## 5. 重要：两者**不应**被融合的地方

为避免走偏，列出几条红线：

1. **不要试图把 BH 的 `helpers.py` 重写成"优雅"的类**。BH 的"简陋"是特性，不是 bug。
2. **AWC 的 core / pipeline / provenance 不应依赖 BH**。BH 必须是 optional extra：`pip install "agent-web-compiler[harness]"`。
3. **不要在 AWC 里复刻 BH 的 daemon/IPC/CDP 逻辑**——那是 BH 的专属领域。AWC 只从 `browser_harness.helpers` import 用户级函数。
4. **不要把 `SiteMemory` 持久化到 BH 的 `agent-workspace/`**。SiteMemory 是 AWC 用户的数据，应该保留在 AWC 的 cache dir；只有在显式 `awc publish bh-skill` 时才流向 BH 仓库，且输出的是**脱敏的 markdown**（BH 明确说 skills are public and must not contain secrets/cookies）。

---

## 6. 落地路线图（建议 4 个里程碑）

### M1｜2 周：`BrowserHarnessFetcher`（方案 A）
- 新增 `agent_web_compiler/sources/browser_harness_fetcher.py`
- `pyproject.toml` 增加 extras：`harness = ["browser-harness"]`
- `PipelineBuilder.with_fetcher("browser_harness")`
- 3 个冒烟测试：公网页、SPA 页（React）、登录墙后的页（跳过 CI，本地手测）
- 文档：`docs/fetchers/browser-harness.md`

**交付物**：一个对用户无感但能力倍增的新数据源。

### M2｜3 周：`LiveActionExecutor` + `LiveRuntime`（方案 B + D）
- 新建 `agent_web_compiler/runtime/browser_harness/`
  - `live_executor.py` — 上面给的骨架
  - `live_runtime.py` — 把 search→plan→execute 串起来的便利类
  - `evidence_adapter.py` — 把 BH 的截图/网络/DOM 快照翻译成 `EvidenceRecord`
- 把 `BrowserMiddleware.execute_action` 接上
- 新 CLI 命令：`awc live "reply to Alice with ..." --on https://linkedin.com/messaging`
- 集成测试：录制一个小型本地 HTML 的 CI fixture，跑点击+表单+验证 provenance

**交付物**：AWC 完成"从编译器到可执行 agent"的身份升级。

### M3｜3 周：`DomainSkillPublisher` + BH 反向贡献（方案 C）
- 新建 `agent_web_compiler/publisher/domain_skill.py`
- 新增命令 `awc publish bh-skill <url> --out <bh-repo>`
- 先人肉给 3 个站点跑：github、hackernews、stackoverflow
- 给 BH 提 3 个 PR（小、聚焦、标注"auto-generated by agent-web-compiler v0.8"）
- BH 合并任何一个 PR，AWC 主页就能挂 "powers domain-skills in browser-use/browser-harness" 徽章

**交付物**：生态位锚定，品牌被动曝光。

### M4｜持续：互读格式（方案 E）
- `CompileConfig.hints_from_skills_dir(Path)` —— 读 BH 的 domain-skills 作为编译提示
- 给 BH 提 PR：`helpers.py` 的 `goto_url` 增加 `llms_txt=True` 可选，自动 fetch `/llms.txt`
- 把这个联动写进一篇博客：《从 llms.txt 到可执行的 agent skill》

**交付物**：行业技术影响力。

---

## 7. 给项目影响力放大的战术建议

1. **贴上 BH 的 README "Related / Used by"**：M3 的 3 个 PR 合并后，主动 issue + PR README，加一行 "works great with agent-web-compiler for auto-skill-generation"。
2. **同时贴上 llms.txt 官网的示例**：AWC 目前已经 支持 llms.txt，M4 落地后再补一个示例 repo，用 BH 做运行时、AWC 做编译器、llms.txt 做协议——**一个能跑通的"Agent Web 三件套"参考实现**。
3. **"Bitter Lesson 续集"博客**：BH 的立项博客叫 "Bitter Lesson of Agent Harnesses"。AWC 可以写一篇 "The Second Bitter Lesson: Compilers for the Agent Web"，论点是"harness 需要极薄，但**前一步的理解层**需要极厚"。这既贴合 BH 的知识分发网络，又把 AWC 定位为"harness 的上游必需品"而不是 "另一个 browser automation"。
4. **把 `awc live` 做成一个 MCP server 工具**：AWC 已经有 MCP serving，只需把 `live_run` 注册进去。任何用 Claude Desktop / Cursor 的人，连一次 MCP，就能同时拿到 AWC 的理解力 + BH 的执行力。这是最小成本的 viral 路径。

---

## 8. 总结一句话

> **BH 是"手"，AWC 是"眼和脑"。把手借过来，眼和脑就能跟世界发生关系；而手只要在你的眼脑指导下做出一次漂亮的动作，它就会记在自己的笔记本（domain-skill）里，下次替你教别人。**

具体到代码动作：**新增 `awc.runtime.browser_harness` 子包 + `DomainSkillPublisher` + 一个 `awc live` CLI + 向 BH 仓库提第一个 auto-generated domain-skill PR**。其余一切从这四件事自然生长出来。
