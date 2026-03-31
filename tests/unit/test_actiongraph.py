"""Tests for the actiongraph package: models, graph_builder, api_synthesizer, hybrid_executor."""

from __future__ import annotations

from agent_web_compiler.actiongraph.api_synthesizer import APISynthesizer
from agent_web_compiler.actiongraph.graph_builder import ActionGraphBuilder
from agent_web_compiler.actiongraph.hybrid_executor import (
    ExecutionDecision,
    HybridExecutor,
)
from agent_web_compiler.actiongraph.models import (
    ActionGraphModel,
    APICandidate,
    NetworkRequest,
    PageState,
    StateTransition,
)
from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.core.document import AgentDocument, SourceType

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_action(
    id: str = "a_001_click",
    type: ActionType = ActionType.CLICK,
    label: str = "Click me",
    role: str | None = None,
    target_url: str | None = None,
    may_navigate: bool = False,
    may_download: bool = False,
    may_open_modal: bool = False,
    confidence: float = 0.8,
    value_schema: dict | None = None,
    required_fields: list[str] | None = None,
) -> Action:
    se = None
    if target_url or may_navigate or may_download or may_open_modal:
        se = StateEffect(
            may_navigate=may_navigate,
            may_download=may_download,
            may_open_modal=may_open_modal,
            target_url=target_url,
        )
    return Action(
        id=id,
        type=type,
        label=label,
        role=role,
        state_effect=se,
        confidence=confidence,
        value_schema=value_schema,
        required_fields=required_fields or [],
    )


def _make_doc(
    actions: list[Action] | None = None,
    source_url: str | None = "https://example.com",
    doc_id: str = "sha256:abc123",
) -> AgentDocument:
    return AgentDocument(
        doc_id=doc_id,
        source_type=SourceType.HTML,
        source_url=source_url,
        title="Test Page",
        actions=actions or [],
    )


# ===========================================================================
# Models tests
# ===========================================================================


class TestPageState:
    def test_to_dict(self):
        state = PageState(
            state_id="s1",
            url="https://example.com",
            dom_hash="hash123",
            visible_block_ids=["b1", "b2"],
            available_action_ids=["a1"],
        )
        d = state.to_dict()
        assert d["state_id"] == "s1"
        assert d["url"] == "https://example.com"
        assert d["visible_block_ids"] == ["b1", "b2"]
        assert d["available_action_ids"] == ["a1"]

    def test_defaults(self):
        state = PageState(state_id="s1")
        assert state.url is None
        assert state.visible_block_ids == []
        assert state.timestamp == 0.0


class TestStateTransition:
    def test_to_dict(self):
        t = StateTransition(
            transition_id="t1",
            from_state_id="s1",
            action_id="a1",
            to_state_id="s2",
            effect_type="navigate",
            url_changed=True,
        )
        d = t.to_dict()
        assert d["transition_id"] == "t1"
        assert d["effect_type"] == "navigate"
        assert d["url_changed"] is True
        assert d["dom_changed"] is False

    def test_defaults(self):
        t = StateTransition(
            transition_id="t1",
            from_state_id="s1",
            action_id="a1",
            to_state_id="s2",
        )
        assert t.effect_type == "unknown"
        assert t.network_calls == []


class TestNetworkRequest:
    def test_to_dict_minimal(self):
        req = NetworkRequest(url="https://api.example.com/data")
        d = req.to_dict()
        assert d["url"] == "https://api.example.com/data"
        assert d["method"] == "GET"
        assert "body" not in d
        assert "triggered_by_action" not in d

    def test_to_dict_full(self):
        req = NetworkRequest(
            url="https://api.example.com/data",
            method="POST",
            body='{"key": "value"}',
            triggered_by_action="a1",
            response_status=200,
            response_content_type="application/json",
        )
        d = req.to_dict()
        assert d["body"] == '{"key": "value"}'
        assert d["triggered_by_action"] == "a1"
        assert d["response_status"] == 200


class TestAPICandidate:
    def test_is_safe_to_call_true(self):
        api = APICandidate(
            api_id="api1",
            safety_level="read_only",
            confidence=0.8,
        )
        assert api.is_safe_to_call() is True

    def test_is_safe_to_call_false_low_confidence(self):
        api = APICandidate(
            api_id="api1",
            safety_level="read_only",
            confidence=0.5,
        )
        assert api.is_safe_to_call() is False

    def test_is_safe_to_call_false_write(self):
        api = APICandidate(
            api_id="api1",
            safety_level="write",
            confidence=0.9,
        )
        assert api.is_safe_to_call() is False

    def test_to_dict(self):
        api = APICandidate(
            api_id="api1",
            endpoint="https://api.example.com/search",
            method="GET",
            params_schema={"q": "string"},
            confidence=0.85,
            safety_level="read_only",
        )
        d = api.to_dict()
        assert d["api_id"] == "api1"
        assert d["params_schema"] == {"q": "string"}
        assert d["confidence"] == 0.85


class TestActionGraphModel:
    def test_empty_graph(self):
        graph = ActionGraphModel()
        assert graph.states == []
        assert graph.transitions == []
        assert graph.api_candidates == []
        assert graph.to_dict() == {
            "states": [],
            "transitions": [],
            "api_candidates": [],
        }

    def test_get_state(self):
        s1 = PageState(state_id="s1")
        s2 = PageState(state_id="s2")
        graph = ActionGraphModel(states=[s1, s2])
        assert graph.get_state("s1") is s1
        assert graph.get_state("s2") is s2
        assert graph.get_state("s3") is None

    def test_get_transitions_from(self):
        t1 = StateTransition(
            transition_id="t1", from_state_id="s1", action_id="a1", to_state_id="s2"
        )
        t2 = StateTransition(
            transition_id="t2", from_state_id="s1", action_id="a2", to_state_id="s3"
        )
        t3 = StateTransition(
            transition_id="t3", from_state_id="s2", action_id="a3", to_state_id="s1"
        )
        graph = ActionGraphModel(transitions=[t1, t2, t3])
        from_s1 = graph.get_transitions_from("s1")
        assert len(from_s1) == 2
        assert t1 in from_s1
        assert t2 in from_s1
        assert len(graph.get_transitions_from("s2")) == 1

    def test_get_reachable_states(self):
        t1 = StateTransition(
            transition_id="t1", from_state_id="s1", action_id="a1", to_state_id="s2"
        )
        t2 = StateTransition(
            transition_id="t2", from_state_id="s1", action_id="a2", to_state_id="s3"
        )
        t3 = StateTransition(
            transition_id="t3", from_state_id="s1", action_id="a3", to_state_id="s2"
        )
        graph = ActionGraphModel(transitions=[t1, t2, t3])
        reachable = graph.get_reachable_states("s1")
        assert set(reachable) == {"s2", "s3"}
        # Order: s2 first (seen first)
        assert reachable[0] == "s2"

    def test_get_safe_apis(self):
        safe = APICandidate(api_id="a1", safety_level="read_only", confidence=0.8)
        unsafe = APICandidate(api_id="a2", safety_level="write", confidence=0.9)
        low = APICandidate(api_id="a3", safety_level="read_only", confidence=0.3)
        graph = ActionGraphModel(api_candidates=[safe, unsafe, low])
        safe_apis = graph.get_safe_apis()
        assert len(safe_apis) == 1
        assert safe_apis[0].api_id == "a1"


# ===========================================================================
# Graph builder tests
# ===========================================================================


class TestActionGraphBuilder:
    def test_empty_document(self):
        builder = ActionGraphBuilder()
        doc = _make_doc(actions=[])
        graph = builder.build_from_document(doc)
        assert len(graph.states) == 1  # just the current page state
        assert len(graph.transitions) == 0

    def test_navigate_action(self):
        builder = ActionGraphBuilder()
        action = _make_action(
            id="a_nav",
            type=ActionType.NAVIGATE,
            label="Next page",
            target_url="https://example.com/page2",
            may_navigate=True,
        )
        doc = _make_doc(actions=[action])
        graph = builder.build_from_document(doc)

        # Should have source state + target state
        assert len(graph.states) >= 2
        assert len(graph.transitions) == 1
        t = graph.transitions[0]
        assert t.effect_type == "navigate"
        assert t.action_id == "a_nav"
        assert t.url_changed is True
        assert t.metadata.get("target_url") == "https://example.com/page2"

    def test_submit_action(self):
        builder = ActionGraphBuilder()
        action = _make_action(
            id="a_submit",
            type=ActionType.SUBMIT,
            label="Search",
            role="submit_search",
            target_url="https://example.com/search",
        )
        doc = _make_doc(actions=[action])
        graph = builder.build_from_document(doc)

        assert len(graph.transitions) == 1
        t = graph.transitions[0]
        assert t.effect_type == "submit"
        assert t.dom_changed is True

    def test_download_action(self):
        builder = ActionGraphBuilder()
        action = _make_action(
            id="a_dl",
            type=ActionType.DOWNLOAD,
            label="Download PDF",
            target_url="https://example.com/file.pdf",
            may_download=True,
        )
        doc = _make_doc(actions=[action])
        graph = builder.build_from_document(doc)

        t = graph.transitions[0]
        assert t.effect_type == "download"

    def test_toggle_action(self):
        builder = ActionGraphBuilder()
        action = _make_action(
            id="a_toggle",
            type=ActionType.TOGGLE,
            label="Show details",
        )
        doc = _make_doc(actions=[action])
        graph = builder.build_from_document(doc)

        t = graph.transitions[0]
        assert t.effect_type == "expand"
        assert t.dom_changed is True

    def test_modal_action(self):
        builder = ActionGraphBuilder()
        action = _make_action(
            id="a_modal",
            type=ActionType.CLICK,
            label="Open settings",
            may_open_modal=True,
        )
        doc = _make_doc(actions=[action])
        graph = builder.build_from_document(doc)

        t = graph.transitions[0]
        assert t.effect_type == "modal"

    def test_multiple_actions(self):
        builder = ActionGraphBuilder()
        actions = [
            _make_action(
                id="a_nav",
                type=ActionType.NAVIGATE,
                label="About",
                target_url="https://example.com/about",
                may_navigate=True,
            ),
            _make_action(
                id="a_search",
                type=ActionType.SUBMIT,
                label="Search",
                target_url="https://example.com/search",
            ),
            _make_action(
                id="a_toggle",
                type=ActionType.TOGGLE,
                label="Expand",
            ),
        ]
        doc = _make_doc(actions=actions)
        graph = builder.build_from_document(doc)

        assert len(graph.transitions) == 3
        effects = {t.effect_type for t in graph.transitions}
        assert "navigate" in effects
        assert "submit" in effects
        assert "expand" in effects

    def test_build_from_documents_cross_linking(self):
        builder = ActionGraphBuilder()
        action_a = _make_action(
            id="a_to_b",
            type=ActionType.NAVIGATE,
            label="Go to B",
            target_url="https://example.com/b",
            may_navigate=True,
        )
        doc_a = _make_doc(
            actions=[action_a],
            source_url="https://example.com/a",
            doc_id="sha256:aaa",
        )
        doc_b = _make_doc(
            actions=[],
            source_url="https://example.com/b",
            doc_id="sha256:bbb",
        )

        graph = builder.build_from_documents([doc_a, doc_b])

        # Should have 2 document states (no extra placeholder needed)
        # The transition from A should point to B's state
        assert len(graph.transitions) == 1
        t = graph.transitions[0]
        assert t.metadata.get("cross_document") is True

        # Target state should be B's state
        b_state = None
        for s in graph.states:
            if s.url == "https://example.com/b":
                b_state = s
                break
        assert b_state is not None
        assert t.to_state_id == b_state.state_id

    def test_build_from_empty_list(self):
        builder = ActionGraphBuilder()
        graph = builder.build_from_documents([])
        assert len(graph.states) == 0
        assert len(graph.transitions) == 0

    def test_state_has_block_and_action_ids(self):
        builder = ActionGraphBuilder()
        from agent_web_compiler.core.block import Block, BlockType

        action = _make_action(id="a_1", type=ActionType.CLICK, label="Click")
        doc = AgentDocument(
            doc_id="sha256:test",
            source_type=SourceType.HTML,
            source_url="https://example.com",
            title="Test",
            blocks=[
                Block(id="b_1", type=BlockType.PARAGRAPH, text="Hello", order=0),
            ],
            actions=[action],
        )
        graph = builder.build_from_document(doc)
        source_state = graph.states[0]
        assert "b_1" in source_state.visible_block_ids
        assert "a_1" in source_state.available_action_ids


# ===========================================================================
# API synthesizer tests
# ===========================================================================


class TestAPISynthesizer:
    def test_synthesize_from_submit_search(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_search",
            type=ActionType.SUBMIT,
            label="Search",
            role="submit_search",
            target_url="https://example.com/search",
            required_fields=["q"],
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.method == "GET"  # search forms are GET
        assert c.endpoint == "https://example.com/search"
        assert "q" in c.params_schema
        assert c.safety_level == "read_only"
        assert c.derived_from_action_id == "a_search"

    def test_synthesize_from_submit_post(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_contact",
            type=ActionType.SUBMIT,
            label="Send message",
            role="contact",
            target_url="https://example.com/contact",
            value_schema={"name": "text", "email": "email", "message": "text"},
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.method == "POST"
        assert c.safety_level == "write"
        assert "name" in c.params_schema

    def test_synthesize_from_navigate_api_url(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_api",
            type=ActionType.NAVIGATE,
            label="API data",
            target_url="https://example.com/api/v1/items?page=1",
            may_navigate=True,
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.method == "GET"
        assert c.safety_level == "read_only"
        assert "page" in c.params_schema

    def test_synthesize_from_navigate_non_api_url(self):
        """Navigate to a regular page URL should not produce an API candidate."""
        synth = APISynthesizer()
        action = _make_action(
            id="a_about",
            type=ActionType.NAVIGATE,
            label="About",
            target_url="https://example.com/about",
            may_navigate=True,
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)
        assert len(candidates) == 0

    def test_synthesize_from_download(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_dl",
            type=ActionType.DOWNLOAD,
            label="Download report",
            target_url="https://example.com/report.pdf",
            may_download=True,
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)

        assert len(candidates) == 1
        c = candidates[0]
        assert c.method == "GET"
        assert c.safety_level == "read_only"
        assert c.confidence == 0.8
        assert c.recommended_mode == "api"

    def test_synthesize_deduplicates(self):
        synth = APISynthesizer()
        # Two download actions to the same URL
        actions = [
            _make_action(
                id="a_dl1",
                type=ActionType.DOWNLOAD,
                label="Download 1",
                target_url="https://example.com/file.zip",
                may_download=True,
            ),
            _make_action(
                id="a_dl2",
                type=ActionType.DOWNLOAD,
                label="Download 2",
                target_url="https://example.com/file.zip",
                may_download=True,
            ),
        ]
        doc = _make_doc(actions=actions)
        candidates = synth.synthesize_from_document(doc)
        assert len(candidates) == 1

    def test_synthesize_from_action_no_url(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_click",
            type=ActionType.CLICK,
            label="Toggle",
        )
        doc = _make_doc()
        result = synth.synthesize_from_action(action, doc)
        assert result is None

    def test_synthesize_from_network_trace(self):
        synth = APISynthesizer()
        requests = [
            NetworkRequest(
                url="https://api.example.com/v1/search?q=test",
                method="GET",
                response_status=200,
                response_content_type="application/json",
                response_size=1024,
            ),
            NetworkRequest(
                url="https://example.com/style.css",
                method="GET",
                response_status=200,
                response_content_type="text/css",
            ),
        ]
        candidates = synth.synthesize_from_network_trace(requests)

        # Should only pick up the API-like request, not the CSS
        assert len(candidates) == 1
        c = candidates[0]
        assert "search" in c.endpoint
        assert c.method == "GET"
        assert "q" in c.params_schema
        assert c.safety_level == "read_only"

    def test_synthesize_from_network_trace_post(self):
        synth = APISynthesizer()
        requests = [
            NetworkRequest(
                url="https://api.example.com/v1/submit",
                method="POST",
                headers={"Authorization": "Bearer token123"},
                response_status=201,
                response_content_type="application/json",
            ),
        ]
        candidates = synth.synthesize_from_network_trace(requests)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.safety_level == "auth_required"
        assert c.recommended_mode == "confirm"
        # Authorization header should be stripped from pattern
        assert "Authorization" not in c.headers_pattern

    def test_synthesize_from_network_trace_empty(self):
        synth = APISynthesizer()
        candidates = synth.synthesize_from_network_trace([])
        assert candidates == []

    def test_login_action_auth_required(self):
        synth = APISynthesizer()
        action = _make_action(
            id="a_login",
            type=ActionType.SUBMIT,
            label="Log in",
            role="login",
            target_url="https://example.com/auth/login",
            required_fields=["username", "password"],
        )
        doc = _make_doc(actions=[action])
        candidates = synth.synthesize_from_document(doc)
        assert len(candidates) == 1
        assert candidates[0].safety_level == "auth_required"


# ===========================================================================
# Hybrid executor tests
# ===========================================================================


class TestExecutionDecision:
    def test_to_dict_without_candidate(self):
        d = ExecutionDecision(
            action_id="a1",
            mode="browser",
            reason="No API",
            confidence=0.5,
        )
        result = d.to_dict()
        assert result["action_id"] == "a1"
        assert result["mode"] == "browser"
        assert "api_candidate" not in result

    def test_to_dict_with_candidate(self):
        api = APICandidate(api_id="api1", endpoint="https://example.com/api")
        d = ExecutionDecision(
            action_id="a1",
            mode="api",
            api_candidate=api,
            confidence=0.8,
        )
        result = d.to_dict()
        assert "api_candidate" in result
        assert result["api_candidate"]["api_id"] == "api1"


class TestHybridExecutor:
    def test_decide_api_mode_safe(self):
        executor = HybridExecutor()
        action = _make_action(id="a_search", type=ActionType.SUBMIT, label="Search")
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a_search",
            safety_level="read_only",
            confidence=0.85,
        )
        decision = executor.decide(action, [api])
        assert decision.mode == "api"
        assert decision.api_candidate is api

    def test_decide_confirm_mode_write(self):
        executor = HybridExecutor()
        action = _make_action(id="a_post", type=ActionType.SUBMIT, label="Submit")
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a_post",
            safety_level="write",
            confidence=0.9,
        )
        decision = executor.decide(action, [api])
        assert decision.mode == "confirm"

    def test_decide_confirm_mode_auth(self):
        executor = HybridExecutor()
        action = _make_action(id="a_login", type=ActionType.SUBMIT, label="Login")
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a_login",
            safety_level="auth_required",
            confidence=0.8,
        )
        decision = executor.decide(action, [api])
        assert decision.mode == "confirm"

    def test_decide_browser_mode_no_candidates(self):
        executor = HybridExecutor()
        action = _make_action(id="a_click", type=ActionType.CLICK, label="Click me")
        decision = executor.decide(action, [])
        assert decision.mode == "browser"
        assert decision.api_candidate is None

    def test_decide_browser_mode_no_match(self):
        executor = HybridExecutor()
        action = _make_action(id="a_click", type=ActionType.CLICK, label="Click me")
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a_other",
            safety_level="read_only",
            confidence=0.9,
        )
        decision = executor.decide(action, [api])
        assert decision.mode == "browser"

    def test_decide_matches_by_target_url(self):
        executor = HybridExecutor()
        action = _make_action(
            id="a_nav",
            type=ActionType.NAVIGATE,
            label="API page",
            target_url="https://example.com/api/data",
            may_navigate=True,
        )
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a_unrelated",
            endpoint="https://example.com/api/data",
            safety_level="read_only",
            confidence=0.8,
        )
        decision = executor.decide(action, [api])
        assert decision.mode == "api"
        assert decision.api_candidate is api

    def test_decide_all(self):
        executor = HybridExecutor()
        actions = [
            _make_action(id="a1", type=ActionType.CLICK, label="Click"),
            _make_action(id="a2", type=ActionType.SUBMIT, label="Search"),
        ]
        doc = _make_doc(actions=actions)
        api = APICandidate(
            api_id="api1",
            derived_from_action_id="a2",
            safety_level="read_only",
            confidence=0.85,
        )
        decisions = executor.decide_all(doc, [api])
        assert len(decisions) == 2
        assert decisions[0].mode == "browser"  # a1 has no API match
        assert decisions[1].mode == "api"  # a2 matches

    def test_generate_api_call_get(self):
        executor = HybridExecutor()
        api = APICandidate(
            api_id="api1",
            endpoint="https://api.example.com/search",
            method="GET",
            params_schema={"q": "string", "page": "int"},
            headers_pattern={"Accept": "application/json"},
        )
        call = executor.generate_api_call(api, {"q": "hello", "page": "1"})
        assert call["method"] == "GET"
        assert "q=hello" in call["url"]
        assert "page=1" in call["url"]
        assert call["headers"] == {"Accept": "application/json"}

    def test_generate_api_call_post(self):
        executor = HybridExecutor()
        api = APICandidate(
            api_id="api1",
            endpoint="https://api.example.com/submit",
            method="POST",
            params_schema={"name": "string"},
            headers_pattern={"Content-Type": "application/json"},
        )
        call = executor.generate_api_call(api, {"name": "test", "extra": "value"})
        assert call["method"] == "POST"
        assert call["url"] == "https://api.example.com/submit"
        assert call["body"]["name"] == "test"
        assert call["body"]["extra"] == "value"

    def test_generate_api_call_no_params(self):
        executor = HybridExecutor()
        api = APICandidate(
            api_id="api1",
            endpoint="https://api.example.com/data",
            method="GET",
        )
        call = executor.generate_api_call(api)
        assert call["method"] == "GET"
        assert call["url"] == "https://api.example.com/data"

    def test_generate_api_call_get_with_existing_query(self):
        executor = HybridExecutor()
        api = APICandidate(
            api_id="api1",
            endpoint="https://api.example.com/search?format=json",
            method="GET",
            params_schema={"q": "string"},
        )
        call = executor.generate_api_call(api, {"q": "test"})
        assert "?" in call["url"]
        # Should use & since endpoint already has ?
        assert "&q=test" in call["url"]


# ===========================================================================
# Integration: builder + synthesizer + executor together
# ===========================================================================


class TestIntegration:
    def test_full_pipeline(self):
        """Build graph, synthesize APIs, decide execution for a search page."""
        # Step 1: Build the document
        actions = [
            _make_action(
                id="a_search",
                type=ActionType.SUBMIT,
                label="Search",
                role="submit_search",
                target_url="https://example.com/api/search",
                required_fields=["q"],
            ),
            _make_action(
                id="a_about",
                type=ActionType.NAVIGATE,
                label="About",
                target_url="https://example.com/about",
                may_navigate=True,
            ),
            _make_action(
                id="a_dl",
                type=ActionType.DOWNLOAD,
                label="Export CSV",
                target_url="https://example.com/export.csv",
                may_download=True,
            ),
        ]
        doc = _make_doc(actions=actions)

        # Step 2: Build action graph
        builder = ActionGraphBuilder()
        graph = builder.build_from_document(doc)
        assert len(graph.states) >= 2
        assert len(graph.transitions) == 3

        # Step 3: Synthesize APIs
        synth = APISynthesizer()
        candidates = synth.synthesize_from_document(doc)
        # Should find API for search (API path) and download
        assert len(candidates) >= 2

        # Step 4: Decide execution
        executor = HybridExecutor()
        decisions = executor.decide_all(doc, candidates)
        assert len(decisions) == 3

        # Search should be API (submit with API URL)
        search_decision = next(d for d in decisions if d.action_id == "a_search")
        assert search_decision.mode == "api"

        # About page should be browser (no API candidate)
        about_decision = next(d for d in decisions if d.action_id == "a_about")
        assert about_decision.mode == "browser"

        # Download should be API
        dl_decision = next(d for d in decisions if d.action_id == "a_dl")
        assert dl_decision.mode == "api"

    def test_graph_serialization_roundtrip(self):
        """Ensure the graph can be serialized to dict cleanly."""
        actions = [
            _make_action(
                id="a_nav",
                type=ActionType.NAVIGATE,
                label="Next",
                target_url="https://example.com/page2",
                may_navigate=True,
            ),
        ]
        doc = _make_doc(actions=actions)

        builder = ActionGraphBuilder()
        graph = builder.build_from_document(doc)

        synth = APISynthesizer()
        graph.api_candidates = synth.synthesize_from_document(doc)

        d = graph.to_dict()
        assert "states" in d
        assert "transitions" in d
        assert "api_candidates" in d
        assert isinstance(d["states"], list)
        assert all(isinstance(s, dict) for s in d["states"])
