# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Database migration runner with SQL file support and rollback capabilities.

Provides Flyway-style versioned migrations with:
- SQL files in V{XXX}__{description}/ directories
- Rollback support (up.sql and down.sql)
- Checksum validation (SHA256)
- Automated backups before migrations
- Lock file mechanism to prevent concurrent migrations
- Full metadata tracking in migration_history table
- Backward compatibility with inline Python migrations
"""

import hashlib
import json
import logging
import os
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple, Callable
import yaml

from .sqlite_client import SQLiteClient

logger = logging.getLogger(__name__)


@dataclass
class Migration:
    """Represents a single database migration."""
    version: int
    description: str
    migration_type: str  # 'sql' or 'inline'
    up_sql: Optional[str] = None
    down_sql: Optional[str] = None
    up_func: Optional[Callable] = None
    down_func: Optional[Callable] = None
    checksum: Optional[str] = None
    metadata: dict = field(default_factory=dict)
    migration_dir: Optional[Path] = None


@dataclass
class MigrationStatus:
    """Status of an applied migration."""
    version: int
    description: str
    checksum: str
    applied_at: datetime
    execution_time_ms: int
    status: str  # 'completed', 'failed', 'rolled_back'
    rollback_at: Optional[datetime] = None
    applied_by: Optional[str] = None
    error_message: Optional[str] = None
    hostname: Optional[str] = None


class MigrationLockError(Exception):
    """Raised when migration lock cannot be acquired."""
    pass


class MigrationValidationError(Exception):
    """Raised when migration validation fails."""
    pass


class MigrationRunner:
    """
    Core migration engine for database schema versioning.

    Features:
    - Discovers SQL migrations from migrations/ directory
    - Validates migration consistency and checksums
    - Creates automated backups before migrations
    - Tracks migration history with comprehensive metadata
    - Supports rollback with down.sql scripts
    - Prevents concurrent migrations with lock files
    - Backward compatible with inline Python migrations
    """

    def __init__(
        self,
        sqlite_client: SQLiteClient,
        migrations_dir: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
        backup_retention: int = 10,
    ):
        """
        Initialize migration runner.

        Args:
            sqlite_client: SQLiteClient instance
            migrations_dir: Directory containing migration files (default: src/processing/database/migrations)
            backup_dir: Directory for database backups (default: ~/.blueplane/backups)
            backup_retention: Number of backups to retain (default: 10)
        """
        self.client = sqlite_client

        # Default migrations directory
        if migrations_dir is None:
            project_root = Path(__file__).parent.parent.parent.parent
            migrations_dir = project_root / "src" / "processing" / "database" / "migrations"
        self.migrations_dir = Path(migrations_dir)

        # Default backup directory
        if backup_dir is None:
            backup_dir = Path.home() / ".blueplane" / "backups"
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.backup_retention = backup_retention
        self.lock_file = Path.home() / ".blueplane" / "migration.lock"
        self.hostname = socket.gethostname()

    def initialize_migration_history(self) -> None:
        """
        Create migration_history table if it doesn't exist.

        Replaces the old schema_version table with comprehensive tracking.
        """
        sql = """
        CREATE TABLE IF NOT EXISTS migration_history (
            version INTEGER PRIMARY KEY,
            description TEXT NOT NULL,
            checksum TEXT NOT NULL,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            execution_time_ms INTEGER,
            status TEXT NOT NULL DEFAULT 'completed',
            rollback_at TIMESTAMP,
            applied_by TEXT,
            metadata TEXT,
            error_message TEXT,
            hostname TEXT,
            CHECK (status IN ('pending', 'running', 'completed', 'failed', 'rolled_back'))
        );
        """
        self.client.execute(sql)

        # Create index on status and applied_at
        self.client.execute("""
            CREATE INDEX IF NOT EXISTS idx_migration_history_status
            ON migration_history(status, applied_at DESC);
        """)

        logger.info("Migration history table initialized")

    def _compute_checksum(self, content: str) -> str:
        """
        Compute SHA256 checksum of migration content.

        Args:
            content: Migration file content

        Returns:
            Hex-encoded SHA256 hash
        """
        return hashlib.sha256(content.encode('utf-8')).hexdigest()

    def _load_migration_metadata(self, migration_dir: Path) -> dict:
        """
        Load optional metadata.yaml from migration directory.

        Args:
            migration_dir: Path to migration directory

        Returns:
            Metadata dictionary (empty if no metadata.yaml found)
        """
        metadata_file = migration_dir / "metadata.yaml"
        if metadata_file.exists():
            try:
                with open(metadata_file, 'r') as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Could not load metadata from {metadata_file}: {e}")
        return {}

    def discover_migrations(self) -> List[Migration]:
        """
        Discover SQL migrations from migrations/ directory.

        Scans for directories matching pattern: V{XXX}__{description}/
        Each directory should contain:
        - up.sql (required): Upgrade script
        - down.sql (optional): Rollback script
        - metadata.yaml (optional): Migration metadata

        Returns:
            List of Migration objects sorted by version
        """
        migrations = []

        if not self.migrations_dir.exists():
            logger.info(f"Migrations directory not found: {self.migrations_dir}")
            return migrations

        # Find all V{XXX}__{description} directories
        for migration_dir in sorted(self.migrations_dir.iterdir()):
            if not migration_dir.is_dir():
                continue

            dirname = migration_dir.name
            if not dirname.startswith('V'):
                continue

            # Parse version and description from directory name
            # Format: V001__initial_schema
            try:
                parts = dirname.split('__', 1)
                if len(parts) != 2:
                    logger.warning(f"Invalid migration directory name: {dirname}")
                    continue

                version_str = parts[0][1:]  # Remove 'V' prefix
                version = int(version_str)
                description = parts[1].replace('_', ' ')

            except ValueError:
                logger.warning(f"Could not parse version from: {dirname}")
                continue

            # Load up.sql
            up_sql_file = migration_dir / "up.sql"
            if not up_sql_file.exists():
                logger.warning(f"Missing up.sql in {migration_dir}")
                continue

            with open(up_sql_file, 'r') as f:
                up_sql = f.read()

            # Load down.sql (optional)
            down_sql = None
            down_sql_file = migration_dir / "down.sql"
            if down_sql_file.exists():
                with open(down_sql_file, 'r') as f:
                    down_sql = f.read()

            # Compute checksum from up.sql
            checksum = self._compute_checksum(up_sql)

            # Load metadata
            metadata = self._load_migration_metadata(migration_dir)

            migration = Migration(
                version=version,
                description=description,
                migration_type='sql',
                up_sql=up_sql,
                down_sql=down_sql,
                checksum=checksum,
                metadata=metadata,
                migration_dir=migration_dir,
            )

            migrations.append(migration)
            logger.debug(f"Discovered migration v{version}: {description}")

        return sorted(migrations, key=lambda m: m.version)

    def register_inline_migration(
        self,
        version: int,
        description: str,
        up_func: Callable,
        down_func: Optional[Callable] = None,
        metadata: Optional[dict] = None,
    ) -> Migration:
        """
        Register an inline Python migration for backward compatibility.

        Allows existing migrate_to_vX functions to work with new system.

        Args:
            version: Migration version number
            description: Human-readable description
            up_func: Function to execute for upgrade (takes SQLiteClient)
            down_func: Optional function for rollback
            metadata: Optional metadata dict

        Returns:
            Migration object
        """
        # Compute checksum from function name and description
        content = f"{up_func.__name__}:{description}"
        checksum = self._compute_checksum(content)

        return Migration(
            version=version,
            description=description,
            migration_type='inline',
            up_func=up_func,
            down_func=down_func,
            checksum=checksum,
            metadata=metadata or {},
        )

    def get_applied_migrations(self) -> List[MigrationStatus]:
        """
        Get list of applied migrations from migration_history.

        Returns:
            List of MigrationStatus objects sorted by version
        """
        with self.client.get_connection() as conn:
            cursor = conn.execute("""
                SELECT version, description, checksum, applied_at,
                       execution_time_ms, status, rollback_at,
                       applied_by, error_message, hostname
                FROM migration_history
                ORDER BY version
            """)

            migrations = []
            for row in cursor.fetchall():
                migrations.append(MigrationStatus(
                    version=row[0],
                    description=row[1],
                    checksum=row[2],
                    applied_at=datetime.fromisoformat(row[3]) if row[3] else None,
                    execution_time_ms=row[4],
                    status=row[5],
                    rollback_at=datetime.fromisoformat(row[6]) if row[6] else None,
                    applied_by=row[7],
                    error_message=row[8],
                    hostname=row[9],
                ))

            return migrations

    def get_current_version(self) -> int:
        """
        Get current database schema version.

        Returns:
            Current version number (0 if no migrations applied)
        """
        try:
            with self.client.get_connection() as conn:
                cursor = conn.execute("""
                    SELECT MAX(version) FROM migration_history
                    WHERE status = 'completed'
                """)
                row = cursor.fetchone()
                return row[0] if row and row[0] is not None else 0
        except Exception:
            return 0

    def get_pending_migrations(self, target_version: Optional[int] = None) -> List[Migration]:
        """
        Get list of pending migrations that haven't been applied.

        Args:
            target_version: Optional target version (default: all pending)

        Returns:
            List of Migration objects
        """
        all_migrations = self.discover_migrations()
        applied = {m.version for m in self.get_applied_migrations() if m.status == 'completed'}

        pending = [m for m in all_migrations if m.version not in applied]

        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]

        return sorted(pending, key=lambda m: m.version)

    def validate_migrations(self) -> Tuple[bool, List[str]]:
        """
        Validate migration consistency and checksums.

        Checks:
        1. No version gaps
        2. No duplicate versions
        3. Checksums match for applied migrations
        4. All applied migrations still exist

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors = []

        # Get all migrations
        all_migrations = self.discover_migrations()
        applied_migrations = self.get_applied_migrations()

        if not all_migrations and not applied_migrations:
            return True, []

        # Check for duplicate versions
        versions = [m.version for m in all_migrations]
        if len(versions) != len(set(versions)):
            duplicates = [v for v in versions if versions.count(v) > 1]
            errors.append(f"Duplicate migration versions found: {duplicates}")

        # Check for gaps in versions
        if all_migrations:
            versions_sorted = sorted(set(versions))
            for i in range(len(versions_sorted) - 1):
                if versions_sorted[i + 1] - versions_sorted[i] > 1:
                    errors.append(
                        f"Version gap detected: {versions_sorted[i]} -> {versions_sorted[i + 1]}"
                    )

        # Check checksums for applied migrations
        migration_map = {m.version: m for m in all_migrations}

        for applied in applied_migrations:
            if applied.status != 'completed':
                continue

            if applied.version not in migration_map:
                errors.append(
                    f"Applied migration v{applied.version} ({applied.description}) "
                    f"no longer exists in migrations directory"
                )
                continue

            migration = migration_map[applied.version]
            if migration.checksum != applied.checksum:
                errors.append(
                    f"Checksum mismatch for v{applied.version} ({applied.description}): "
                    f"expected {applied.checksum[:8]}..., got {migration.checksum[:8]}..."
                )

        return len(errors) == 0, errors

    def _acquire_lock(self) -> None:
        """
        Acquire migration lock to prevent concurrent migrations.

        Raises:
            MigrationLockError: If lock cannot be acquired
        """
        lock_dir = self.lock_file.parent
        lock_dir.mkdir(parents=True, exist_ok=True)

        if self.lock_file.exists():
            # Check if lock is stale
            try:
                with open(self.lock_file, 'r') as f:
                    lock_data = json.load(f)

                pid = lock_data.get('pid')
                timestamp = lock_data.get('timestamp')

                # Check if process is still running
                if pid:
                    try:
                        os.kill(pid, 0)  # Signal 0 checks if process exists
                        # Process exists, lock is valid
                        raise MigrationLockError(
                            f"Migration already in progress (PID: {pid}, started: {timestamp})"
                        )
                    except OSError:
                        # Process doesn't exist, lock is stale
                        logger.warning(f"Removing stale lock file (PID {pid} not found)")
                        self.lock_file.unlink()
            except (json.JSONDecodeError, KeyError):
                logger.warning("Invalid lock file, removing")
                self.lock_file.unlink()

        # Create lock file
        lock_data = {
            'pid': os.getpid(),
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'hostname': self.hostname,
        }

        with open(self.lock_file, 'w') as f:
            json.dump(lock_data, f, indent=2)

        logger.debug(f"Acquired migration lock: {self.lock_file}")

    def _release_lock(self) -> None:
        """Release migration lock."""
        if self.lock_file.exists():
            self.lock_file.unlink()
            logger.debug(f"Released migration lock: {self.lock_file}")

    def backup_database(self, target_version: int) -> Path:
        """
        Create timestamped backup of database before migration.

        Uses SQLite VACUUM INTO for consistent backups.

        Args:
            target_version: Target migration version

        Returns:
            Path to backup file
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_filename = f"telemetry_pre_v{target_version}_{timestamp}.db"
        backup_path = self.backup_dir / backup_filename

        logger.info(f"Creating backup: {backup_path}")

        with self.client.get_connection() as conn:
            conn.execute(f"VACUUM INTO '{backup_path}'")

        # Verify backup
        if not backup_path.exists():
            raise RuntimeError(f"Backup file not created: {backup_path}")

        # Clean up old backups
        self._cleanup_old_backups()

        logger.info(f"Backup created successfully: {backup_path}")
        return backup_path

    def _cleanup_old_backups(self) -> None:
        """Remove old backups beyond retention limit."""
        backups = sorted(
            self.backup_dir.glob("telemetry_pre_v*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

        if len(backups) > self.backup_retention:
            for old_backup in backups[self.backup_retention:]:
                try:
                    old_backup.unlink()
                    logger.debug(f"Removed old backup: {old_backup.name}")
                except Exception as e:
                    logger.warning(f"Could not remove old backup {old_backup}: {e}")

    def _record_migration_status(
        self,
        version: int,
        description: str,
        checksum: str,
        execution_time_ms: int,
        status: str = 'completed',
        error_message: Optional[str] = None,
        applied_by: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Record migration status in migration_history table.

        Args:
            version: Migration version
            description: Migration description
            checksum: Migration checksum
            execution_time_ms: Execution time in milliseconds
            status: Migration status
            error_message: Optional error message if failed
            applied_by: Who/what applied the migration
            metadata: Optional metadata dict
        """
        metadata_json = json.dumps(metadata) if metadata else None

        with self.client.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO migration_history
                (version, description, checksum, applied_at, execution_time_ms,
                 status, applied_by, metadata, error_message, hostname)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                version,
                description,
                checksum,
                datetime.now(timezone.utc).isoformat(),
                execution_time_ms,
                status,
                applied_by or 'migration_runner.py',
                metadata_json,
                error_message,
                self.hostname,
            ))
            conn.commit()

    def apply_migration(self, migration: Migration, dry_run: bool = False) -> bool:
        """
        Apply a single migration.

        Args:
            migration: Migration to apply
            dry_run: If True, only validate without applying

        Returns:
            True if successful, False otherwise
        """
        if dry_run:
            logger.info(f"[DRY RUN] Would apply migration v{migration.version}: {migration.description}")
            if migration.migration_type == 'sql':
                logger.info(f"[DRY RUN] SQL content preview:\n{migration.up_sql[:500]}...")
            return True

        logger.info(f"Applying migration v{migration.version}: {migration.description}")
        start_time = time.time()

        try:
            with self.client.get_connection() as conn:
                if migration.migration_type == 'sql':
                    # Execute SQL migration
                    conn.executescript(migration.up_sql)
                elif migration.migration_type == 'inline':
                    # Execute inline Python migration
                    if migration.up_func:
                        migration.up_func(self.client)
                    else:
                        raise ValueError(f"Inline migration v{migration.version} has no up_func")

                conn.commit()

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Record success
            self._record_migration_status(
                version=migration.version,
                description=migration.description,
                checksum=migration.checksum,
                execution_time_ms=execution_time_ms,
                status='completed',
                metadata=migration.metadata,
            )

            logger.info(
                f"Migration v{migration.version} completed in {execution_time_ms}ms"
            )
            return True

        except Exception as e:
            execution_time_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)

            logger.error(f"Migration v{migration.version} failed: {error_msg}", exc_info=True)

            # Record failure
            self._record_migration_status(
                version=migration.version,
                description=migration.description,
                checksum=migration.checksum,
                execution_time_ms=execution_time_ms,
                status='failed',
                error_message=error_msg,
                metadata=migration.metadata,
            )

            return False

    def rollback_migration(self, version: int) -> bool:
        """
        Rollback a specific migration using down.sql.

        Args:
            version: Version to rollback

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Rolling back migration v{version}")

        # Find migration
        all_migrations = self.discover_migrations()
        migration = next((m for m in all_migrations if m.version == version), None)

        if not migration:
            logger.error(f"Migration v{version} not found")
            return False

        if not migration.down_sql and not migration.down_func:
            logger.error(f"Migration v{version} has no rollback script")
            return False

        start_time = time.time()

        try:
            with self.client.get_connection() as conn:
                if migration.migration_type == 'sql':
                    conn.executescript(migration.down_sql)
                elif migration.migration_type == 'inline':
                    if migration.down_func:
                        migration.down_func(self.client)
                    else:
                        raise ValueError(f"Inline migration v{version} has no down_func")

                conn.commit()

            execution_time_ms = int((time.time() - start_time) * 1000)

            # Update status to rolled_back
            with self.client.get_connection() as conn:
                conn.execute("""
                    UPDATE migration_history
                    SET status = 'rolled_back',
                        rollback_at = ?
                    WHERE version = ?
                """, (datetime.now(timezone.utc).isoformat(), version))
                conn.commit()

            logger.info(f"Migration v{version} rolled back in {execution_time_ms}ms")
            return True

        except Exception as e:
            logger.error(f"Rollback of v{version} failed: {e}", exc_info=True)
            return False

    def migrate_to(self, target_version: int, dry_run: bool = False) -> bool:
        """
        Migrate database to specific version.

        Args:
            target_version: Target schema version
            dry_run: If True, only validate without applying

        Returns:
            True if successful, False otherwise
        """
        current_version = self.get_current_version()

        if current_version == target_version:
            logger.info(f"Database already at version {target_version}")
            return True

        if current_version > target_version:
            logger.error("Downgrade not supported via migrate_to (use rollback_migration)")
            return False

        # Validate migrations
        is_valid, errors = self.validate_migrations()
        if not is_valid:
            logger.error("Migration validation failed:")
            for error in errors:
                logger.error(f"  - {error}")
            raise MigrationValidationError(f"Migration validation failed: {errors}")

        # Get pending migrations
        pending = self.get_pending_migrations(target_version)

        if not pending:
            logger.info(f"No migrations to apply (current: v{current_version})")
            return True

        if dry_run:
            logger.info(f"[DRY RUN] Would apply {len(pending)} migration(s):")
            for migration in pending:
                logger.info(f"  - v{migration.version}: {migration.description}")
            return True

        # Acquire lock
        try:
            self._acquire_lock()
        except MigrationLockError as e:
            logger.error(str(e))
            return False

        try:
            # Create backup before applying migrations
            self.backup_database(target_version)

            # Apply migrations sequentially
            for migration in pending:
                success = self.apply_migration(migration, dry_run=False)
                if not success:
                    logger.error(
                        f"Migration v{migration.version} failed. "
                        f"Database left at v{self.get_current_version()}"
                    )
                    return False

            logger.info(
                f"Successfully migrated from v{current_version} to v{target_version}"
            )
            return True

        finally:
            self._release_lock()
