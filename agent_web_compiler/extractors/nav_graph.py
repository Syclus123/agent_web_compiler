"""Navigation graph -- models page state transitions from actions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from agent_web_compiler.core.action import Action, ActionType


@dataclass
class NavNode:
    """A state in the navigation graph."""

    id: str
    label: str
    url: str | None = None
    node_type: str = "page"  # "page", "modal", "form_result", "download"


@dataclass
class NavEdge:
    """A transition between states."""

    action_id: str
    source: str  # NavNode id
    target: str  # NavNode id
    action_type: str
    label: str
    requires_input: bool = False
    input_fields: list[str] | None = None


@dataclass
class NavigationGraph:
    """Complete navigation model for a page."""

    current_page: NavNode
    nodes: list[NavNode] = field(default_factory=list)
    edges: list[NavEdge] = field(default_factory=list)

    def get_reachable_pages(self) -> list[NavNode]:
        """Return all page-type nodes reachable from the current page."""
        reachable_ids: set[str] = set()
        for edge in self.edges:
            if edge.source == self.current_page.id:
                reachable_ids.add(edge.target)

        return [n for n in self.nodes if n.id in reachable_ids and n.node_type == "page"]

    def get_form_flows(self) -> list[list[NavEdge]]:
        """Return lists of edges that represent form submission flows.

        Each flow is a list of edges where requires_input=True, grouped
        by sharing the same target node (form result).
        """
        # Group form edges by target
        form_edges_by_target: dict[str, list[NavEdge]] = {}
        for edge in self.edges:
            if edge.requires_input:
                if edge.target not in form_edges_by_target:
                    form_edges_by_target[edge.target] = []
                form_edges_by_target[edge.target].append(edge)

        return list(form_edges_by_target.values())

    def get_pagination_chain(self) -> list[NavEdge]:
        """Return edges that form a pagination chain (next/prev page actions)."""
        return [
            edge for edge in self.edges
            if "next_page" in edge.label.lower()
            or "prev_page" in edge.label.lower()
            or "pagination" in edge.label.lower()
        ]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the graph to a plain dict."""
        return {
            "current_page": _node_to_dict(self.current_page),
            "nodes": [_node_to_dict(n) for n in self.nodes],
            "edges": [_edge_to_dict(e) for e in self.edges],
        }


def _node_to_dict(node: NavNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "label": node.label,
        "url": node.url,
        "node_type": node.node_type,
    }


def _edge_to_dict(edge: NavEdge) -> dict[str, Any]:
    result: dict[str, Any] = {
        "action_id": edge.action_id,
        "source": edge.source,
        "target": edge.target,
        "action_type": edge.action_type,
        "label": edge.label,
        "requires_input": edge.requires_input,
    }
    if edge.input_fields:
        result["input_fields"] = edge.input_fields
    return result


class NavGraphBuilder:
    """Builds a navigation graph from extracted actions.

    For each action, creates appropriate nodes and edges based on the action
    type and its state effects. Navigation actions create page nodes, submit
    actions create form_result nodes, downloads create download nodes, and
    actions that may open modals create modal nodes.
    """

    def build(
        self,
        actions: list[Action],
        source_url: str | None = None,
    ) -> NavigationGraph:
        """Build a NavigationGraph from a list of actions.

        Args:
            actions: List of extracted actions from a page.
            source_url: The URL of the current page, if known.

        Returns:
            A NavigationGraph modeling reachable states and transitions.
        """
        current_id = self._make_node_id("current", source_url or "page")
        current_node = NavNode(
            id=current_id,
            label=source_url or "Current Page",
            url=source_url,
            node_type="page",
        )

        nodes: list[NavNode] = [current_node]
        edges: list[NavEdge] = []
        seen_node_ids: set[str] = {current_id}

        for action in actions:
            action_nodes, action_edges = self._process_action(
                action, current_id, seen_node_ids,
            )
            nodes.extend(action_nodes)
            edges.extend(action_edges)
            for n in action_nodes:
                seen_node_ids.add(n.id)

        return NavigationGraph(
            current_page=current_node,
            nodes=nodes,
            edges=edges,
        )

    def _process_action(
        self,
        action: Action,
        current_id: str,
        seen_ids: set[str],
    ) -> tuple[list[NavNode], list[NavEdge]]:
        """Process a single action into nodes and edges."""
        nodes: list[NavNode] = []
        edges: list[NavEdge] = []

        target_url = action.state_effect.target_url if action.state_effect else None
        may_open_modal = action.state_effect.may_open_modal if action.state_effect else False

        if action.type == ActionType.NAVIGATE:
            node_id = self._make_node_id("nav", target_url or action.id)
            if node_id not in seen_ids:
                nodes.append(NavNode(
                    id=node_id,
                    label=action.label,
                    url=target_url,
                    node_type="page",
                ))
            edge_label = action.label
            if action.role:
                edge_label = f"{action.role}: {action.label}"
            edges.append(NavEdge(
                action_id=action.id,
                source=current_id,
                target=node_id,
                action_type=action.type.value,
                label=edge_label,
            ))

        elif action.type == ActionType.SUBMIT:
            node_id = self._make_node_id("form", action.id)
            if node_id not in seen_ids:
                nodes.append(NavNode(
                    id=node_id,
                    label=f"Result: {action.label}",
                    url=target_url,
                    node_type="form_result",
                ))
            edges.append(NavEdge(
                action_id=action.id,
                source=current_id,
                target=node_id,
                action_type=action.type.value,
                label=action.label,
                requires_input=True,
                input_fields=action.required_fields if action.required_fields else None,
            ))

        elif action.type == ActionType.DOWNLOAD:
            node_id = self._make_node_id("download", target_url or action.id)
            if node_id not in seen_ids:
                nodes.append(NavNode(
                    id=node_id,
                    label=f"Download: {action.label}",
                    url=target_url,
                    node_type="download",
                ))
            edges.append(NavEdge(
                action_id=action.id,
                source=current_id,
                target=node_id,
                action_type=action.type.value,
                label=action.label,
            ))

        elif may_open_modal:
            node_id = self._make_node_id("modal", action.id)
            if node_id not in seen_ids:
                nodes.append(NavNode(
                    id=node_id,
                    label=f"Modal: {action.label}",
                    node_type="modal",
                ))
            edges.append(NavEdge(
                action_id=action.id,
                source=current_id,
                target=node_id,
                action_type=action.type.value,
                label=action.label,
            ))

        return nodes, edges

    @staticmethod
    def _make_node_id(prefix: str, key: str) -> str:
        """Generate a deterministic node ID."""
        short_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()[:8]
        return f"{prefix}_{short_hash}"
