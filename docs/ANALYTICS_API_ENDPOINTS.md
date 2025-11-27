# Analytics API Endpoints Design

## Overview

This document outlines the design for REST API endpoints to expose analytics queries, enabling programmatic access to analytics data.

## Purpose

REST API endpoints provide:
- **Programmatic Access**: Enable external tools and dashboards to query analytics
- **Standardized Interface**: HTTP/REST is widely supported
- **Security**: Can add authentication/authorization layers
- **Flexibility**: Support multiple clients (web, CLI, other services)

## Design Principles

1. **RESTful**: Follow REST conventions (GET for queries, proper status codes)
2. **JSON**: All requests/responses use JSON
3. **Query Parameters**: Use query parameters for filtering (not request body for GET)
4. **Pagination**: Support pagination for large result sets
5. **Error Handling**: Consistent error response format

## Proposed API Endpoints

### Base URL

```
http://localhost:8789/api/analytics/v1
```

**Note**: Port 8789 to avoid conflict with HTTP hooks endpoint (8787).

### Endpoints

#### 1. GET `/workspaces/{workspace_hash}/activity`

Query workspace activity over time.

**Query Parameters**:
- `start_time` (optional): ISO 8601 timestamp
- `end_time` (optional): ISO 8601 timestamp
- `limit` (optional): Max results (default: 100, max: 1000)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "workspace_hash": "abc123",
  "activity": [
    {
      "trace_sequence": 1,
      "timestamp": "2025-11-27T10:00:00Z",
      "generation_count": 5,
      "composer_session_count": 2,
      "file_count": 10,
      "total_lines_added": 150,
      "total_lines_removed": 30
    }
  ],
  "total": 50,
  "limit": 100,
  "offset": 0
}
```

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `404 Not Found`: Workspace not found
- `500 Internal Server Error`: Server error

#### 2. GET `/generations`

Query AI generations.

**Query Parameters**:
- `workspace_hash` (optional): Filter by workspace
- `generation_type` (optional): Filter by type
- `start_time` (optional): ISO 8601 timestamp
- `end_time` (optional): ISO 8601 timestamp
- `limit` (optional): Max results (default: 100, max: 1000)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "generations": [
    {
      "generation_id": "gen-001",
      "workspace_hash": "abc123",
      "trace_sequence": 1,
      "generation_time": "2025-11-27T10:00:00Z",
      "generation_type": "code_completion",
      "description": "Added function to process user input"
    }
  ],
  "total": 200,
  "limit": 100,
  "offset": 0
}
```

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Server error

#### 3. GET `/composer-sessions`

Query composer sessions.

**Query Parameters**:
- `workspace_hash` (optional): Filter by workspace
- `unified_mode` (optional): Filter by mode (chat/edit)
- `start_time` (optional): ISO 8601 timestamp
- `end_time` (optional): ISO 8601 timestamp
- `limit` (optional): Max results (default: 100, max: 1000)
- `offset` (optional): Pagination offset (default: 0)

**Response**:
```json
{
  "sessions": [
    {
      "composer_id": "composer-001",
      "workspace_hash": "abc123",
      "trace_sequence": 1,
      "created_at": "2025-11-27T10:00:00Z",
      "unified_mode": "chat",
      "force_mode": "none",
      "lines_added": 45,
      "lines_removed": 12,
      "is_archived": false
    }
  ],
  "total": 50,
  "limit": 100,
  "offset": 0
}
```

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Server error

#### 4. GET `/workspaces`

List all workspaces with summary statistics.

**Query Parameters**:
- `limit` (optional): Max results (default: 100, max: 1000)
- `offset` (optional): Pagination offset (default: 0)
- `sort` (optional): Sort field (default: "last_seen")
- `order` (optional): Sort order (asc/desc, default: "desc")

**Response**:
```json
{
  "workspaces": [
    {
      "workspace_hash": "abc123",
      "workspace_path": "/path/to/workspace",
      "first_seen": "2025-11-20T10:00:00Z",
      "last_seen": "2025-11-27T10:00:00Z",
      "total_traces": 150,
      "platform": "cursor"
    }
  ],
  "total": 10,
  "limit": 100,
  "offset": 0
}
```

**Status Codes**:
- `200 OK`: Success
- `400 Bad Request`: Invalid parameters
- `500 Internal Server Error`: Server error

#### 5. GET `/health`

Health check endpoint.

**Response**:
```json
{
  "status": "ok",
  "analytics_service": {
    "enabled": true,
    "last_processed": {
      "cursor": {
        "sequence": 1000,
        "timestamp": "2025-11-27T10:00:00Z"
      },
      "claude_code": {
        "sequence": 500,
        "timestamp": "2025-11-27T09:55:00Z"
      }
    }
  },
  "duckdb": {
    "connected": true,
    "database_path": "~/.blueplane/analytics.duckdb"
  }
}
```

**Status Codes**:
- `200 OK`: Service healthy
- `503 Service Unavailable`: Service unhealthy

## Error Response Format

All errors follow this format:

```json
{
  "error": {
    "code": "INVALID_PARAMETER",
    "message": "Invalid start_time format. Expected ISO 8601.",
    "details": {
      "parameter": "start_time",
      "value": "invalid"
    }
  }
}
```

**Error Codes**:
- `INVALID_PARAMETER`: Invalid query parameter
- `NOT_FOUND`: Resource not found
- `INTERNAL_ERROR`: Server error
- `SERVICE_UNAVAILABLE`: Analytics service unavailable

## Implementation Plan

### Phase 1: Basic API Server (Future)

**Tasks**:
- [ ] Choose web framework (FastAPI recommended)
- [ ] Implement API server structure
- [ ] Add endpoint routing
- [ ] Integrate with existing query functions
- [ ] Add error handling
- [ ] Add request validation

### Phase 2: Integration (Future)

**Tasks**:
- [ ] Integrate API server with main server
- [ ] Add configuration for API server
- [ ] Add startup/shutdown logic
- [ ] Add health check endpoint
- [ ] Add logging

### Phase 3: Advanced Features (Future)

**Tasks**:
- [ ] Add authentication/authorization
- [ ] Add rate limiting
- [ ] Add request/response caching
- [ ] Add API documentation (OpenAPI/Swagger)
- [ ] Add metrics/observability

## Implementation Example

### Using FastAPI

```python
from fastapi import FastAPI, Query, HTTPException
from typing import Optional
from datetime import datetime

app = FastAPI(title="Blueplane Analytics API", version="1.0.0")

@app.get("/api/analytics/v1/workspaces/{workspace_hash}/activity")
async def get_workspace_activity(
    workspace_hash: str,
    start_time: Optional[datetime] = Query(None),
    end_time: Optional[datetime] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0)
):
    """Get workspace activity over time."""
    try:
        from src.analytics.queries.analytics_queries import query_workspace_activity
        from src.capture.shared.config import Config
        
        config = Config()
        duckdb_path = Path(config.get_path("analytics.duckdb.db_path"))
        
        activity = query_workspace_activity(
            duckdb_path,
            workspace_hash,
            start_time=start_time,
            end_time=end_time
        )
        
        # Apply pagination
        total = len(activity)
        paginated = activity[offset:offset+limit]
        
        return {
            "workspace_hash": workspace_hash,
            "activity": paginated,
            "total": total,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

## Security Considerations

### Authentication (Future)

- **API Keys**: Simple API key authentication
- **OAuth2**: For more complex scenarios
- **Localhost Only**: Default to localhost-only access

### Authorization (Future)

- **Workspace Access**: Restrict access to user's workspaces
- **Rate Limiting**: Prevent abuse
- **CORS**: Configure CORS for web clients

## Configuration

Add to `config/config.yaml`:

```yaml
analytics:
  api:
    enabled: false  # Enable API server
    host: "127.0.0.1"  # Bind to localhost only
    port: 8789  # API server port
    authentication:
      enabled: false  # Enable API key authentication
      api_key: null  # API key (set in user config)
```

## Status

**Current Status**: ⚠️ **Design Phase** - Not yet implemented

**Next Steps**:
1. Validate API design with stakeholders
2. Implement basic API server
3. Add integration tests
4. Document API usage

## Related Documents

- [Analytics Queries](src/analytics/queries/analytics_queries.py) - Query functions to expose
- [Analytics Service](src/analytics/service.py) - Processing service
- [HTTP Endpoint](src/processing/http_endpoint.py) - Existing HTTP server pattern

