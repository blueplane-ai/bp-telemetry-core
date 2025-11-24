# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Privacy sanitization utilities.
"""

import hashlib
import re
from typing import Any, Dict, Optional


class PrivacySanitizer:
    """
    Privacy sanitization utility.
    Implements privacy controls according to privacy.yaml configuration.
    """

    def __init__(self, privacy_config: Optional[Dict[str, Any]] = None):
        """
        Initialize sanitizer with privacy configuration.

        Args:
            privacy_config: Privacy configuration dict (from Config.privacy)
        """
        self.config = privacy_config or {}
        self.opt_out = self.config.get('opt_out', [
            'user_prompts',
            'file_contents',
            'error_messages',
            'commit_messages',
            'environment_variables'
        ])

    @staticmethod
    def hash_value(value: str, algorithm: str = "sha256", truncate: int = 16) -> str:
        """
        Hash a value for privacy.

        Args:
            value: Value to hash
            algorithm: Hash algorithm to use
            truncate: Length to truncate hash (0 = no truncation)

        Returns:
            Hashed value (optionally truncated)
        """
        if algorithm == "sha256":
            hash_obj = hashlib.sha256(value.encode())
        else:
            hash_obj = hashlib.sha256(value.encode())

        hash_hex = hash_obj.hexdigest()
        return hash_hex[:truncate] if truncate > 0 else hash_hex

    def redact_error_message(self, error_message: str) -> str:
        """
        Redact sensitive information from error messages.

        Args:
            error_message: Original error message

        Returns:
            Redacted error message with generic placeholder
        """
        if not error_message:
            return error_message

        if 'error_messages' in self.opt_out:
            # Fully redact - only return error type/category
            # Try to extract error type (first word or exception class)
            match = re.match(r'^(\w+(?:Error|Exception)?)', error_message)
            if match:
                return f"<redacted:{match.group(1)}>"
            return "<redacted:error>"

        # Partial redaction - remove file paths, stack traces, etc.
        redacted = error_message
        # Remove file paths
        redacted = re.sub(r'/[^\s]+', '<path>', redacted)
        redacted = re.sub(r'[A-Z]:\\[^\s]+', '<path>', redacted)
        # Remove line numbers
        redacted = re.sub(r'line \d+', 'line <num>', redacted)
        # Remove specific values
        redacted = re.sub(r'\d{3,}', '<num>', redacted)

        return redacted

    def sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize event payload according to privacy rules.

        Args:
            payload: Event payload to sanitize

        Returns:
            Sanitized payload
        """
        sanitized = payload.copy()

        # Redact error messages if present
        if 'error_message' in sanitized:
            sanitized['error_message'] = self.redact_error_message(sanitized['error_message'])

        # Remove prompt text content
        if 'prompt_text' in sanitized and 'user_prompts' in self.opt_out:
            # Replace with hash or remove entirely
            if sanitized['prompt_text']:
                sanitized['prompt_text_hash'] = self.hash_value(sanitized['prompt_text'])
            del sanitized['prompt_text']

        # Remove file contents
        if 'file_content' in sanitized and 'file_contents' in self.opt_out:
            if sanitized['file_content']:
                sanitized['file_content_hash'] = self.hash_value(sanitized['file_content'])
            del sanitized['file_content']

        return sanitized

    def sanitize_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize complete event data.

        Args:
            event: Event to sanitize

        Returns:
            Sanitized event
        """
        sanitized = event.copy()

        # Sanitize payload
        if 'payload' in sanitized:
            sanitized['payload'] = self.sanitize_payload(sanitized['payload'])

        return sanitized
