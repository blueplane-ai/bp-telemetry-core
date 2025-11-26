# Analytics Service Testing Plan

## Overview

Comprehensive testing plan for the analytics service refactor, covering unit tests, integration tests, and end-to-end scenarios.

## Test Categories

### 1. Unit Tests

#### 1.1 SQLiteReader Tests (`test_analytics_sqlite_reader.py`)
- [ ] Test initialization with valid/invalid database paths
- [ ] Test `get_last_processed_sequence()` - returns 0 for new platform
- [ ] Test `get_last_processed_sequence()` - returns correct sequence for existing platform
- [ ] Test `update_last_processed()` - creates new state record
- [ ] Test `update_last_processed()` - updates existing state record
- [ ] Test `get_new_traces()` - returns empty list when no new traces
- [ ] Test `get_new_traces()` - returns traces since last processed sequence
- [ ] Test `get_new_traces()` - handles decompression correctly
- [ ] Test `get_new_traces()` - handles invalid/corrupted data gracefully
- [ ] Test `get_new_traces()` - respects limit parameter
- [ ] Test `get_conversations()` - returns conversations correctly
- [ ] Test `get_conversations()` - filters by timestamp correctly
- [ ] Test `get_sessions()` - returns Cursor sessions correctly
- [ ] Test `get_sessions()` - filters by timestamp correctly
- [ ] Test error handling for missing tables
- [ ] Test error handling for database connection failures

#### 1.2 DuckDBWriter Tests (`test_analytics_duckdb_writer.py`)
- [ ] Test initialization with valid/invalid paths
- [ ] Test `connect()` - creates schema if not exists
- [ ] Test `connect()` - reuses existing schema
- [ ] Test `write_traces()` - handles empty trace list
- [ ] Test `write_traces()` - processes Cursor traces correctly
- [ ] Test `write_traces()` - processes Claude Code traces correctly
- [ ] Test `write_traces()` - extracts AI generations correctly
- [ ] Test `write_traces()` - extracts composer sessions correctly
- [ ] Test `write_traces()` - extracts file history correctly
- [ ] Test `write_traces()` - handles malformed event_data gracefully
- [ ] Test `write_traces()` - updates workspace metadata correctly
- [ ] Test `write_conversations()` - placeholder implementation
- [ ] Test `write_sessions()` - placeholder implementation
- [ ] Test `sync_workspace_metadata()` - creates/updates workspace
- [ ] Test error handling for DuckDB connection failures
- [ ] Test batch processing with large datasets

#### 1.3 AnalyticsService Tests (`test_analytics_service.py`)
- [ ] Test initialization with disabled config
- [ ] Test initialization with enabled config
- [ ] Test `start()` - does nothing when disabled
- [ ] Test `start()` - initializes components when enabled
- [ ] Test `stop()` - gracefully shuts down
- [ ] Test `process_once()` - processes Cursor traces
- [ ] Test `process_once()` - processes Claude Code traces
- [ ] Test `process_once()` - updates processing state correctly
- [ ] Test `process_once()` - handles errors gracefully
- [ ] Test `run()` - processes on schedule
- [ ] Test `run()` - handles cancellation correctly
- [ ] Test error recovery after failures

### 2. Integration Tests

#### 2.1 SQLite → DuckDB Pipeline (`test_analytics_integration.py`)
- [ ] Test full pipeline: SQLite traces → DuckDB analytics
- [ ] Test incremental processing (only new traces)
- [ ] Test state persistence across restarts
- [ ] Test processing with mixed Cursor and Claude Code traces
- [ ] Test processing with large batch sizes
- [ ] Test error recovery and retry logic
- [ ] Test concurrent access (read from SQLite while writing to DuckDB)

#### 2.2 End-to-End Test (`test_analytics_e2e.py`)
- [ ] Test complete flow: Capture → SQLite → Analytics → DuckDB
- [ ] Test with real Cursor workspace data
- [ ] Test with real Claude Code session data
- [ ] Test analytics queries return correct results
- [ ] Test performance with realistic data volumes

### 3. Test Fixtures

#### 3.1 SQLite Test Fixtures (`tests/fixtures/sqlite_fixtures.py`)
- [ ] Create test database with sample Cursor traces
- [ ] Create test database with sample Claude Code traces
- [ ] Create test database with conversations
- [ ] Create test database with sessions
- [ ] Helper functions to insert test data
- [ ] Helper functions to verify data

#### 3.2 DuckDB Test Fixtures (`tests/fixtures/duckdb_fixtures.py`)
- [ ] Create test DuckDB database
- [ ] Helper functions to query and verify analytics data
- [ ] Helper functions to clean up test data

## Test Implementation Strategy

1. **Create test fixtures first** - Reusable test data and helpers
2. **Implement unit tests** - Test each component in isolation
3. **Implement integration tests** - Test component interactions
4. **Implement end-to-end tests** - Test full pipeline
5. **Run all tests** - Verify everything works
6. **Fix issues** - Address any failures or edge cases
7. **Document results** - Record test coverage and results

## Test Data Requirements

### Sample Cursor Traces
- AI generation events
- Composer session events
- File history events
- Mixed event types

### Sample Claude Code Traces
- User message events
- Assistant message events
- Tool use events
- System events

### Sample Conversations
- Cursor conversations (with session_id)
- Claude Code conversations (no session_id)

### Sample Sessions
- Cursor sessions with various states

## Success Criteria

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All end-to-end tests pass
- [ ] Test coverage > 80% for analytics components
- [ ] Tests run in < 30 seconds
- [ ] Tests are deterministic and repeatable
- [ ] Tests clean up after themselves

