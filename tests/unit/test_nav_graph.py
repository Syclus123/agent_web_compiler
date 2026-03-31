"""Tests for NavGraphBuilder and NavigationGraph."""

from __future__ import annotations

from agent_web_compiler.core.action import Action, ActionType, StateEffect
from agent_web_compiler.extractors.nav_graph import (
    NavEdge,
    NavGraphBuilder,
    NavigationGraph,
    NavNode,
)


def _make_action(
    id: str,
    type: ActionType,
    label: str,
    role: str | None = None,
    target_url: str | None = None,
    may_open_modal: bool = False,
    required_fields: list[str] | None = None,
) -> Action:
    """Helper to create an Action with minimal boilerplate."""
    state_effect = None
    if target_url or may_open_modal:
        state_effect = StateEffect(
            may_navigate=(type == ActionType.NAVIGATE),
            may_open_modal=may_open_modal,
            target_url=target_url,
        )
    return Action(
        id=id,
        type=type,
        label=label,
        role=role,
        state_effect=state_effect,
        required_fields=required_fields or [],
    )


class TestNavGraphBuilder:
    def test_empty_actions_returns_current_page_only(self):
        builder = NavGraphBuilder()
        graph = builder.build([], source_url="https://example.com")

        assert graph.current_page is not None
        assert graph.current_page.url == "https://example.com"
        assert graph.current_page.node_type == "page"
        assert len(graph.nodes) == 1
        assert len(graph.edges) == 0

    def test_navigate_action_creates_page_node_and_edge(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action(
                "a_about",
                ActionType.NAVIGATE,
                "About Us",
                target_url="https://example.com/about",
            ),
        ]
        graph = builder.build(actions, source_url="https://example.com")

        assert len(graph.nodes) == 2
        assert len(graph.edges) == 1

        target_node = [n for n in graph.nodes if n.node_type == "page" and n.url == "https://example.com/about"]
        assert len(target_node) == 1

        edge = graph.edges[0]
        assert edge.action_id == "a_about"
        assert edge.action_type == "navigate"
        assert edge.requires_input is False

    def test_submit_action_creates_form_result_node(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action(
                "a_search",
                ActionType.SUBMIT,
                "Search",
                required_fields=["query"],
            ),
        ]
        graph = builder.build(actions)

        form_nodes = [n for n in graph.nodes if n.node_type == "form_result"]
        assert len(form_nodes) == 1
        assert "Search" in form_nodes[0].label

        edge = graph.edges[0]
        assert edge.requires_input is True
        assert edge.input_fields == ["query"]

    def test_download_action_creates_download_node(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action(
                "a_pdf",
                ActionType.DOWNLOAD,
                "Download PDF",
                target_url="https://example.com/doc.pdf",
            ),
        ]
        graph = builder.build(actions)

        download_nodes = [n for n in graph.nodes if n.node_type == "download"]
        assert len(download_nodes) == 1
        assert download_nodes[0].url == "https://example.com/doc.pdf"

    def test_modal_action_creates_modal_node(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action(
                "a_settings",
                ActionType.CLICK,
                "Open Settings",
                may_open_modal=True,
            ),
        ]
        graph = builder.build(actions)

        modal_nodes = [n for n in graph.nodes if n.node_type == "modal"]
        assert len(modal_nodes) == 1
        assert "Settings" in modal_nodes[0].label

    def test_multiple_actions_mixed(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action("a_nav", ActionType.NAVIGATE, "Home", target_url="/"),
            _make_action("a_search", ActionType.SUBMIT, "Search", required_fields=["q"]),
            _make_action("a_dl", ActionType.DOWNLOAD, "Get CSV", target_url="/data.csv"),
            _make_action("a_modal", ActionType.CLICK, "Settings", may_open_modal=True),
        ]
        graph = builder.build(actions, source_url="https://example.com")

        # 1 current + 4 new nodes
        assert len(graph.nodes) == 5
        assert len(graph.edges) == 4

    def test_navigate_with_role_includes_role_in_label(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action(
                "a_next",
                ActionType.NAVIGATE,
                "Next",
                role="next_page",
                target_url="/page/2",
            ),
        ]
        graph = builder.build(actions)

        edge = graph.edges[0]
        assert "next_page" in edge.label

    def test_no_duplicate_nodes_for_same_target(self):
        builder = NavGraphBuilder()
        actions = [
            _make_action("a_link1", ActionType.NAVIGATE, "Link 1", target_url="/about"),
            _make_action("a_link2", ActionType.NAVIGATE, "Link 2", target_url="/about"),
        ]
        graph = builder.build(actions)

        # Same target URL should produce the same node ID, so only 2 nodes total
        page_nodes = [n for n in graph.nodes if n.node_type == "page"]
        # current page + 1 /about node
        assert len(page_nodes) == 2
        # But 2 edges (both links point to same node)
        assert len(graph.edges) == 2


class TestNavigationGraph:
    def test_get_reachable_pages(self):
        current = NavNode(id="current", label="Home", url="/", node_type="page")
        about = NavNode(id="about", label="About", url="/about", node_type="page")
        modal = NavNode(id="modal1", label="Modal", node_type="modal")

        graph = NavigationGraph(
            current_page=current,
            nodes=[current, about, modal],
            edges=[
                NavEdge(action_id="a1", source="current", target="about", action_type="navigate", label="About"),
                NavEdge(action_id="a2", source="current", target="modal1", action_type="click", label="Open Modal"),
            ],
        )

        reachable = graph.get_reachable_pages()
        assert len(reachable) == 1
        assert reachable[0].id == "about"

    def test_get_form_flows(self):
        current = NavNode(id="current", label="Home", node_type="page")
        result1 = NavNode(id="result1", label="Search Result", node_type="form_result")

        graph = NavigationGraph(
            current_page=current,
            nodes=[current, result1],
            edges=[
                NavEdge(
                    action_id="a1", source="current", target="result1",
                    action_type="submit", label="Search",
                    requires_input=True, input_fields=["q"],
                ),
            ],
        )

        flows = graph.get_form_flows()
        assert len(flows) == 1
        assert len(flows[0]) == 1
        assert flows[0][0].input_fields == ["q"]

    def test_get_pagination_chain(self):
        current = NavNode(id="current", label="Page 1", node_type="page")
        page2 = NavNode(id="page2", label="Page 2", node_type="page")

        graph = NavigationGraph(
            current_page=current,
            nodes=[current, page2],
            edges=[
                NavEdge(
                    action_id="a_next", source="current", target="page2",
                    action_type="navigate", label="next_page: Next",
                ),
            ],
        )

        chain = graph.get_pagination_chain()
        assert len(chain) == 1

    def test_to_dict_serialization(self):
        current = NavNode(id="current", label="Home", url="/", node_type="page")
        graph = NavigationGraph(
            current_page=current,
            nodes=[current],
            edges=[],
        )

        d = graph.to_dict()
        assert "current_page" in d
        assert d["current_page"]["id"] == "current"
        assert "nodes" in d
        assert "edges" in d
        assert len(d["nodes"]) == 1
        assert len(d["edges"]) == 0

    def test_to_dict_includes_edge_fields(self):
        current = NavNode(id="c", label="C", node_type="page")
        target = NavNode(id="t", label="T", node_type="form_result")
        edge = NavEdge(
            action_id="a1", source="c", target="t",
            action_type="submit", label="Submit",
            requires_input=True, input_fields=["email", "password"],
        )

        graph = NavigationGraph(current_page=current, nodes=[current, target], edges=[edge])
        d = graph.to_dict()

        edge_dict = d["edges"][0]
        assert edge_dict["requires_input"] is True
        assert edge_dict["input_fields"] == ["email", "password"]

    def test_empty_graph(self):
        current = NavNode(id="c", label="Empty", node_type="page")
        graph = NavigationGraph(current_page=current)

        assert graph.get_reachable_pages() == []
        assert graph.get_form_flows() == []
        assert graph.get_pagination_chain() == []
