# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
HTTP client for communicating with the Layer 2 REST API.
"""

import json
from typing import Dict, Any, Optional, List
from functools import lru_cache
from datetime import datetime, timedelta
import time

import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from rich.console import Console

console = Console()


class CacheEntry:
    """Cache entry with TTL support."""

    def __init__(self, data: Any, ttl: int):
        self.data = data
        self.expires_at = time.time() + ttl

    def is_expired(self) -> bool:
        """Check if cache entry is expired."""
        return time.time() > self.expires_at


class APIClient:
    """HTTP client for Layer 2 REST API."""

    def __init__(self, config):
        """Initialize API client with configuration."""
        self.config = config
        self.base_url = config.server_url
        self.session = self._create_session()
        self._cache: Dict[str, CacheEntry] = {}

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry logic."""
        session = requests.Session()

        # Configure retries
        retry = Retry(
            total=self.config.retry,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504]
        )

        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # Set default timeout
        session.timeout = self.config.timeout

        # Set headers
        session.headers.update({
            "User-Agent": "Blueplane-CLI/0.1.0",
            "Accept": "application/json",
            "Content-Type": "application/json"
        })

        return session

    def _get_cache_key(self, method: str, endpoint: str, params: Optional[Dict] = None) -> str:
        """Generate cache key for request."""
        param_str = json.dumps(params or {}, sort_keys=True)
        return f"{method}:{endpoint}:{param_str}"

    def _get_cached(self, key: str) -> Optional[Any]:
        """Get cached response if available and not expired."""
        if not self.config.cache_enabled:
            return None

        if key in self._cache:
            entry = self._cache[key]
            if not entry.is_expired():
                return entry.data
            else:
                del self._cache[key]

        return None

    def _set_cached(self, key: str, data: Any):
        """Store response in cache."""
        if self.config.cache_enabled:
            self._cache[key] = CacheEntry(data, self.config.cache_ttl)

            # Limit cache size
            if len(self._cache) > self.config.cache_size:
                # Remove oldest entries
                sorted_keys = sorted(
                    self._cache.keys(),
                    key=lambda k: self._cache[k].expires_at
                )
                for old_key in sorted_keys[:len(self._cache) - self.config.cache_size]:
                    del self._cache[old_key]

    def test_connection(self) -> bool:
        """Test if the server is reachable."""
        try:
            response = self.session.get(
                f"{self.base_url}/api/v1/health",
                timeout=5
            )
            return response.status_code == 200
        except Exception:
            return False

    def get_metrics(
        self,
        session_id: Optional[str] = None,
        period: Optional[str] = None,
        group_by: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get metrics from the API."""
        params = {}
        if session_id:
            params["session_id"] = session_id
        if period:
            params["period"] = period
        if group_by:
            params["group_by"] = group_by

        return self._request("GET", "/api/v1/metrics", params=params)

    def get_sessions(
        self,
        limit: int = 10,
        offset: int = 0,
        platform: Optional[str] = None,
        project: Optional[str] = None,
        min_acceptance: Optional[float] = None,
        min_productivity: Optional[int] = None,
        since: Optional[str] = None,
        until: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get sessions list from the API."""
        params = {
            "limit": limit,
            "offset": offset
        }

        if platform:
            params["platform"] = platform
        if project:
            params["project"] = project
        if min_acceptance is not None:
            params["min_acceptance"] = min_acceptance
        if min_productivity is not None:
            params["min_productivity"] = min_productivity
        if since:
            params["since"] = since
        if until:
            params["until"] = until

        return self._request("GET", "/api/v1/sessions", params=params)

    def get_session_analysis(
        self,
        session_id: str,
        include_tools: bool = False,
        include_files: bool = False,
        include_insights: bool = False
    ) -> Dict[str, Any]:
        """Get detailed analysis of a session."""
        params = {
            "include_tools": include_tools,
            "include_files": include_files,
            "include_insights": include_insights
        }

        return self._request("GET", f"/api/v1/sessions/{session_id}/analysis", params=params)

    def get_insights(
        self,
        insight_type: Optional[str] = None,
        session_id: Optional[str] = None,
        priority: Optional[str] = None,
        actionable_only: bool = False
    ) -> Dict[str, Any]:
        """Get AI-powered insights."""
        params = {}

        if insight_type:
            params["type"] = insight_type
        if session_id:
            params["session_id"] = session_id
        if priority:
            params["priority"] = priority
        if actionable_only:
            params["actionable"] = True

        return self._request("GET", "/api/v1/insights", params=params)

    def export_data(
        self,
        format: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        filters: Optional[Dict[str, Any]] = None,
        anonymize: bool = False
    ) -> bytes:
        """Export telemetry data."""
        params = {
            "format": format,
            "anonymize": anonymize
        }

        if start_date:
            params["start"] = start_date
        if end_date:
            params["end"] = end_date
        if filters:
            params["filters"] = json.dumps(filters)

        # Don't cache export requests
        response = self._raw_request("GET", "/api/v1/export", params=params)
        return response.content

    def get_config(self) -> Dict[str, Any]:
        """Get server configuration."""
        return self._request("GET", "/api/v1/config")

    def update_config(self, key: str, value: Any) -> Dict[str, Any]:
        """Update server configuration."""
        data = {
            "key": key,
            "value": value
        }
        # Don't cache config updates
        return self._request("POST", "/api/v1/config", data=data, use_cache=False)

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Make HTTP request to the API."""
        # Check cache for GET requests
        if method == "GET" and use_cache:
            cache_key = self._get_cache_key(method, endpoint, params)
            cached = self._get_cached(cache_key)
            if cached is not None:
                if self.config.debug:
                    console.print(f"[dim]Cache hit: {endpoint}[/dim]")
                return cached

        # Make request
        url = f"{self.base_url}{endpoint}"

        try:
            if self.config.debug:
                console.print(f"[dim]{method} {url}[/dim]")

            response = self.session.request(
                method,
                url,
                params=params,
                json=data,
                timeout=self.config.timeout
            )

            response.raise_for_status()
            result = response.json()

            # Cache successful GET requests
            if method == "GET" and use_cache:
                cache_key = self._get_cache_key(method, endpoint, params)
                self._set_cached(cache_key, result)

            return result

        except requests.exceptions.Timeout:
            raise Exception(f"Request timeout after {self.config.timeout}s")
        except requests.exceptions.ConnectionError:
            raise Exception(f"Cannot connect to server at {self.base_url}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise Exception(f"Endpoint not found: {endpoint}")
            elif e.response.status_code == 401:
                raise Exception("Authentication failed")
            elif e.response.status_code == 500:
                raise Exception("Server error")
            else:
                raise Exception(f"HTTP error {e.response.status_code}")
        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def _raw_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> requests.Response:
        """Make raw HTTP request (returns Response object)."""
        url = f"{self.base_url}{endpoint}"

        try:
            response = self.session.request(
                method,
                url,
                params=params,
                json=data,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            return response

        except Exception as e:
            raise Exception(f"Request failed: {e}")

    def clear_cache(self):
        """Clear the response cache."""
        self._cache.clear()
        if self.config.debug:
            console.print("[dim]Cache cleared[/dim]")