"""API candidate synthesis -- find machine-callable interfaces behind UI actions.

Analyzes action patterns, URL structures, and form submissions to
identify potential API endpoints that agents can call directly instead
of driving a browser.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qs, urlparse

from agent_web_compiler.actiongraph.models import APICandidate, NetworkRequest
from agent_web_compiler.core.action import Action, ActionType
from agent_web_compiler.core.document import AgentDocument

# Patterns that suggest an API endpoint
_API_PATH_PATTERN = re.compile(
    r"(/api/|/v[0-9]+/|/graphql|/rest/|/json/|/data/)", re.IGNORECASE
)
_QUERY_PARAM_PATTERN = re.compile(r"\?[a-zA-Z_]+=")
_PAGINATION_PATTERN = re.compile(
    r"[?&](page|offset|limit|start|cursor|skip)=", re.IGNORECASE
)

# HTTP methods that are read-only
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Content types that indicate structured data
_STRUCTURED_CONTENT_TYPES = frozenset({
    "application/json",
    "application/xml",
    "text/xml",
    "application/rss+xml",
    "application/atom+xml",
})


class APISynthesizer:
    """Synthesizes pseudo-API candidates from UI actions.

    Examines action target URLs, form submissions, and network request
    patterns to identify endpoints that an agent could call directly
    via HTTP instead of driving a browser.
    """

    def synthesize_from_document(self, doc: AgentDocument) -> list[APICandidate]:
        """Analyze a document's actions and synthesize API candidates.

        Args:
            doc: A compiled AgentDocument with extracted actions.

        Returns:
            List of APICandidate objects, sorted by confidence descending.
        """
        candidates: list[APICandidate] = []
        seen_endpoints: set[str] = set()

        for action in doc.actions:
            candidate = self.synthesize_from_action(action, doc)
            if candidate is not None:
                # Deduplicate by endpoint + method
                key = f"{candidate.method}:{candidate.endpoint}"
                if key not in seen_endpoints:
                    seen_endpoints.add(key)
                    candidates.append(candidate)

        # Sort by confidence descending
        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    def synthesize_from_action(
        self, action: Action, doc: AgentDocument
    ) -> APICandidate | None:
        """Try to synthesize an API candidate from a single action.

        Args:
            action: An extracted Action from the page.
            doc: The parent document (for context like source URL).

        Returns:
            An APICandidate if synthesis succeeds, None otherwise.
        """
        target_url = action.state_effect.target_url if action.state_effect else None

        # Submit actions with form data -> potential API
        if action.type == ActionType.SUBMIT:
            return self._synthesize_from_submit(action, target_url, doc)

        # Navigate actions with API-like URLs
        if action.type == ActionType.NAVIGATE and target_url:
            return self._synthesize_from_navigate(action, target_url)

        # Download actions -> direct download API
        if action.type == ActionType.DOWNLOAD and target_url:
            return self._synthesize_from_download(action, target_url)

        return None

    def synthesize_from_network_trace(
        self, requests: list[NetworkRequest]
    ) -> list[APICandidate]:
        """Synthesize APIs from captured network requests.

        Analyzes network traffic to find patterns that indicate
        callable API endpoints.

        Args:
            requests: List of captured NetworkRequest objects.

        Returns:
            List of APICandidate objects derived from network patterns.
        """
        candidates: list[APICandidate] = []
        seen_endpoints: set[str] = set()

        for req in requests:
            parsed = urlparse(req.url)
            path = parsed.path

            # Skip non-API-like requests
            if not _API_PATH_PATTERN.search(path) and not _is_structured_response(req):
                continue

            key = f"{req.method}:{parsed.scheme}://{parsed.netloc}{path}"
            if key in seen_endpoints:
                continue
            seen_endpoints.add(key)

            # Build params schema from query params
            params_schema: dict[str, str] = {}
            query_params = parse_qs(parsed.query)
            for param_name in query_params:
                params_schema[param_name] = "string"

            # Also include params from request body if present
            if req.params:
                for param_name in req.params:
                    params_schema[param_name] = "string"

            safety = self._assess_safety_from_request(req)
            confidence = self._estimate_confidence_from_request(req)

            candidate = APICandidate(
                api_id=f"api_net_{_short_hash(key)}",
                derived_from_action_id=req.triggered_by_action,
                endpoint=f"{parsed.scheme}://{parsed.netloc}{path}",
                method=req.method,
                params_schema=params_schema,
                headers_pattern=_extract_safe_headers(req.headers),
                confidence=confidence,
                safety_level=safety,
                recommended_mode=_recommend_mode(safety, confidence),
                description=f"Network-traced {req.method} {path}",
            )
            candidates.append(candidate)

        candidates.sort(key=lambda c: c.confidence, reverse=True)
        return candidates

    # ------------------------------------------------------------------
    # Private synthesis methods
    # ------------------------------------------------------------------

    def _synthesize_from_submit(
        self, action: Action, target_url: str | None, doc: AgentDocument
    ) -> APICandidate | None:
        """Synthesize an API from a form submission action."""
        # Build endpoint from form action URL or document URL
        endpoint = target_url or doc.source_url or ""
        if not endpoint:
            return None

        # Build params schema from required fields / value schema
        params_schema: dict[str, str] = {}
        if action.value_schema:
            for field_name, field_type in action.value_schema.items():
                params_schema[field_name] = str(field_type)
        elif action.required_fields:
            for field_name in action.required_fields:
                params_schema[field_name] = "string"

        # Determine method: search forms are usually GET, others POST
        is_search = action.role in ("submit_search", "search")
        method = "GET" if is_search else "POST"

        safety = self._assess_safety_for_method(method, action)
        confidence = self._estimate_confidence_for_action(action, endpoint)

        return APICandidate(
            api_id=f"api_submit_{_short_hash(action.id)}",
            derived_from_action_id=action.id,
            endpoint=endpoint,
            method=method,
            params_schema=params_schema,
            confidence=confidence,
            safety_level=safety,
            recommended_mode=_recommend_mode(safety, confidence),
            description=f"Form submit: {action.label}",
        )

    def _synthesize_from_navigate(
        self, action: Action, target_url: str
    ) -> APICandidate | None:
        """Synthesize an API from a navigation action with API-like URL."""
        parsed = urlparse(target_url)

        # Only synthesize if URL looks API-like or has query params
        has_api_path = bool(_API_PATH_PATTERN.search(parsed.path))
        has_params = bool(parsed.query)
        has_pagination = bool(_PAGINATION_PATTERN.search(target_url))

        if not (has_api_path or has_pagination):
            return None

        # Build params from query string
        params_schema: dict[str, str] = {}
        if has_params:
            query_params = parse_qs(parsed.query)
            for param_name in query_params:
                params_schema[param_name] = "string"

        confidence = 0.5
        if has_api_path:
            confidence += 0.2
        if has_params:
            confidence += 0.1
        confidence = min(confidence, 0.9)

        return APICandidate(
            api_id=f"api_nav_{_short_hash(target_url)}",
            derived_from_action_id=action.id,
            endpoint=target_url,
            method="GET",
            params_schema=params_schema,
            confidence=confidence,
            safety_level="read_only",
            recommended_mode=_recommend_mode("read_only", confidence),
            description=f"Navigate API: {action.label}",
        )

    def _synthesize_from_download(
        self, action: Action, target_url: str
    ) -> APICandidate | None:
        """Synthesize a direct download API from a download action."""
        return APICandidate(
            api_id=f"api_dl_{_short_hash(target_url)}",
            derived_from_action_id=action.id,
            endpoint=target_url,
            method="GET",
            confidence=0.8,
            safety_level="read_only",
            recommended_mode="api",
            description=f"Direct download: {action.label}",
        )

    # ------------------------------------------------------------------
    # Safety and confidence assessment
    # ------------------------------------------------------------------

    def _assess_safety(self, candidate: APICandidate) -> str:
        """Assess the safety level of an API candidate."""
        if candidate.method in _READ_METHODS:
            return "read_only"
        if candidate.headers_pattern.get("Authorization"):
            return "auth_required"
        return "write"

    def _assess_safety_for_method(self, method: str, action: Action) -> str:
        """Assess safety based on HTTP method and action context."""
        if method in _READ_METHODS:
            return "read_only"
        # Check if action role suggests auth
        if action.role and "login" in action.role:
            return "auth_required"
        return "write"

    def _assess_safety_from_request(self, req: NetworkRequest) -> str:
        """Assess safety from a captured network request."""
        if req.method in _READ_METHODS:
            return "read_only"
        headers_lower = {k.lower(): v for k, v in req.headers.items()}
        if "authorization" in headers_lower or "cookie" in headers_lower:
            return "auth_required"
        return "write"

    def _estimate_confidence(self, candidate: APICandidate) -> float:
        """Estimate confidence that this is a real, callable API."""
        confidence = 0.3
        if _API_PATH_PATTERN.search(candidate.endpoint):
            confidence += 0.3
        if candidate.params_schema:
            confidence += 0.1
        if candidate.safety_level == "read_only":
            confidence += 0.1
        return min(confidence, 0.95)

    def _estimate_confidence_for_action(
        self, action: Action, endpoint: str
    ) -> float:
        """Estimate confidence for an action-derived API."""
        confidence = 0.3

        # Higher confidence for API-like endpoints
        if _API_PATH_PATTERN.search(endpoint):
            confidence += 0.3

        # Higher for well-identified actions
        confidence += action.confidence * 0.2

        # Higher for actions with clear parameters
        if action.value_schema or action.required_fields:
            confidence += 0.1

        return min(round(confidence, 2), 0.95)

    def _estimate_confidence_from_request(self, req: NetworkRequest) -> float:
        """Estimate confidence from a network request."""
        confidence = 0.4

        # Successful response
        if 200 <= req.response_status < 300:
            confidence += 0.2

        # Structured content type
        if _is_structured_response(req):
            confidence += 0.2

        # API path pattern
        if _API_PATH_PATTERN.search(req.url):
            confidence += 0.1

        return min(round(confidence, 2), 0.95)


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _is_structured_response(req: NetworkRequest) -> bool:
    """Check if a request has a structured (API-like) response content type."""
    ct = req.response_content_type.lower().split(";")[0].strip()
    return ct in _STRUCTURED_CONTENT_TYPES


def _extract_safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Extract non-sensitive headers suitable for pattern matching.

    Strips Authorization, Cookie, and other sensitive headers.
    """
    sensitive = frozenset({"authorization", "cookie", "set-cookie", "x-csrf-token"})
    return {
        k: v for k, v in headers.items()
        if k.lower() not in sensitive
    }


def _recommend_mode(safety: str, confidence: float) -> str:
    """Recommend execution mode based on safety and confidence."""
    if safety == "write" or safety == "auth_required":
        return "confirm"
    if safety == "read_only" and confidence >= 0.7:
        return "api"
    return "browser"


def _short_hash(value: str) -> str:
    """Generate a short hash for ID generation."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
