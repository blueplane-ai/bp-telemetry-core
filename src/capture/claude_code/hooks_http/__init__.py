# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
HTTP-based Claude Code hooks for testing zero-dependency event submission.

These hooks use HTTP POST to submit events to the telemetry server,
requiring only Python standard library (no redis, yaml, etc.).
"""
