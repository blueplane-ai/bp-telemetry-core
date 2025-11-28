# Copyright © 2025 Sierra Labs LLC
# SPDX-License-Identifier: AGPL-3.0-only
# License-Filename: LICENSE

"""
Cursor Markdown History Writer.

Writes workspace history to Markdown files by reading from Cursor's ItemTable.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Keys to monitor in Cursor's ItemTable for trace-relevant data
TRACE_RELEVANT_KEYS = [
    'aiService.generations',
    'aiService.prompts',
    'composer.composerData',
    'workbench.backgroundComposer.workspacePersistentData',
    'workbench.agentMode.exitInfo',
    'interactive.sessions',
    'history.entries',
    'cursorAuth/workspaceOpenedDate',
]


class CursorMarkdownWriter:
    """
    Writes Cursor workspace history to Markdown files.
    
    Formats data from ItemTable keys into human-readable Markdown.
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize Markdown writer.

        Args:
            output_dir: Base directory for output files (default: workspace/.history/)
        """
        self.output_dir = output_dir
        
    def write_workspace_history(
        self,
        workspace_path: str,
        workspace_hash: str,
        data: Dict[str, Any],
        timestamp: Optional[datetime] = None
    ) -> Path:
        """
        Write workspace history to Markdown file.

        Args:
            workspace_path: Path to workspace directory
            workspace_hash: Hash of workspace path
            data: Dictionary of ItemTable key-value pairs
            timestamp: Timestamp for filename (default: now)

        Returns:
            Path to written Markdown file
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        # Determine output directory
        if self.output_dir:
            output_path = self.output_dir
        else:
            # Default: workspace/.history/
            output_path = Path(workspace_path) / ".history"
        
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Generate filename with timestamp
        filename = f"{workspace_hash}_{timestamp.strftime('%Y%m%d_%H%M%S')}.md"
        filepath = output_path / filename
        
        # Generate Markdown content
        content = self._generate_markdown(workspace_path, workspace_hash, data, timestamp)
        
        # Write to file
        filepath.write_text(content, encoding='utf-8')
        
        logger.info(f"Wrote workspace history to {filepath}")
        return filepath
    
    def _generate_markdown(
        self,
        workspace_path: str,
        workspace_hash: str,
        data: Dict[str, Any],
        timestamp: datetime
    ) -> str:
        """
        Generate Markdown content from workspace data.

        Args:
            workspace_path: Path to workspace
            workspace_hash: Hash of workspace path
            data: ItemTable data
            timestamp: Current timestamp

        Returns:
            Markdown formatted string
        """
        lines = []
        
        # Header
        lines.append("# Cursor Workspace History")
        lines.append("")
        lines.append(f"**Workspace**: `{workspace_path}`")
        lines.append(f"**Workspace Hash**: `{workspace_hash}`")
        lines.append(f"**Generated**: {timestamp.isoformat()}")
        lines.append("")
        lines.append("---")
        lines.append("")
        
        # AI Service section
        if 'aiService.generations' in data or 'aiService.prompts' in data:
            lines.append("## AI Service Activity")
            lines.append("")
            
            if 'aiService.generations' in data:
                lines.extend(self._format_generations(data['aiService.generations']))
            
            if 'aiService.prompts' in data:
                lines.extend(self._format_prompts(data['aiService.prompts']))
            
            lines.append("")
        
        # Composer section
        if 'composer.composerData' in data:
            lines.append("## Composer Sessions")
            lines.append("")
            lines.extend(self._format_composer_data(data['composer.composerData']))
            lines.append("")
        
        # Background Composer section
        if 'workbench.backgroundComposer.workspacePersistentData' in data:
            lines.append("## Background Composer")
            lines.append("")
            lines.extend(self._format_background_composer(
                data['workbench.backgroundComposer.workspacePersistentData']
            ))
            lines.append("")
        
        # Agent Mode section
        if 'workbench.agentMode.exitInfo' in data:
            lines.append("## Agent Mode")
            lines.append("")
            lines.extend(self._format_agent_mode(data['workbench.agentMode.exitInfo']))
            lines.append("")
        
        # File History section
        if 'history.entries' in data:
            lines.append("## File History")
            lines.append("")
            lines.extend(self._format_history_entries(data['history.entries']))
            lines.append("")
        
        # Interactive Sessions section
        if 'interactive.sessions' in data:
            lines.append("## Interactive Sessions")
            lines.append("")
            lines.extend(self._format_interactive_sessions(data['interactive.sessions']))
            lines.append("")
        
        # Workspace Info section
        if 'cursorAuth/workspaceOpenedDate' in data:
            lines.append("## Workspace Info")
            lines.append("")
            lines.extend(self._format_workspace_info(data['cursorAuth/workspaceOpenedDate']))
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_generations(self, generations_data: Any) -> list:
        """Format AI generations data."""
        lines = []
        
        try:
            if isinstance(generations_data, bytes):
                generations = json.loads(generations_data.decode('utf-8'))
            elif isinstance(generations_data, str):
                generations = json.loads(generations_data)
            else:
                generations = generations_data
            
            if not generations:
                lines.append("*No generations recorded*")
                return lines
            
            lines.append("### Generations")
            lines.append("")
            
            # Sort by timestamp if available
            if isinstance(generations, list):
                sorted_gens = sorted(
                    generations,
                    key=lambda x: x.get('unixMs', 0) if isinstance(x, dict) else 0,
                    reverse=True
                )
                
                for gen in sorted_gens[:10]:  # Show last 10
                    if not isinstance(gen, dict):
                        continue
                    
                    timestamp = gen.get('unixMs', 0)
                    if timestamp:
                        dt = datetime.fromtimestamp(timestamp / 1000)
                        lines.append(f"- **{dt.strftime('%Y-%m-%d %H:%M:%S')}**")
                    else:
                        lines.append("- **Unknown time**")
                    
                    gen_type = gen.get('type', 'unknown')
                    lines.append(f"  - Type: `{gen_type}`")
                    
                    gen_id = gen.get('generationUUID', 'unknown')
                    lines.append(f"  - ID: `{gen_id[:8]}...`")
                    
                    description = gen.get('textDescription')
                    if description:
                        # Truncate long descriptions
                        if len(description) > 100:
                            description = description[:97] + "..."
                        lines.append(f"  - Description: {description}")
                    
                    lines.append("")
                
                if len(sorted_gens) > 10:
                    lines.append(f"*...and {len(sorted_gens) - 10} more*")
                    lines.append("")
        
        except Exception as e:
            logger.error(f"Error formatting generations: {e}")
            lines.append(f"*Error parsing generations data: {e}*")
        
        return lines
    
    def _format_prompts(self, prompts_data: Any) -> list:
        """Format AI prompts data."""
        lines = []
        
        try:
            if isinstance(prompts_data, bytes):
                prompts = json.loads(prompts_data.decode('utf-8'))
            elif isinstance(prompts_data, str):
                prompts = json.loads(prompts_data)
            else:
                prompts = prompts_data
            
            if not prompts:
                lines.append("*No prompts recorded*")
                return lines
            
            lines.append("### Prompts")
            lines.append("")
            
            if isinstance(prompts, list):
                for i, prompt in enumerate(prompts[-5:], 1):  # Show last 5
                    if not isinstance(prompt, dict):
                        continue
                    
                    text = prompt.get('text', '')
                    command_type = prompt.get('commandType', 'unknown')
                    
                    lines.append(f"{i}. **Command Type {command_type}**")
                    if text:
                        # Truncate long prompts
                        if len(text) > 150:
                            text = text[:147] + "..."
                        lines.append(f"   - {text}")
                    lines.append("")
                
                if len(prompts) > 5:
                    lines.append(f"*...and {len(prompts) - 5} more*")
                    lines.append("")
        
        except Exception as e:
            logger.error(f"Error formatting prompts: {e}")
            lines.append(f"*Error parsing prompts data: {e}*")
        
        return lines
    
    def _format_composer_data(self, composer_data: Any) -> list:
        """Format composer session data."""
        lines = []
        
        try:
            if isinstance(composer_data, bytes):
                data = json.loads(composer_data.decode('utf-8'))
            elif isinstance(composer_data, str):
                data = json.loads(composer_data)
            else:
                data = composer_data
            
            all_composers = data.get('allComposers', [])
            
            if not all_composers:
                lines.append("*No composer sessions*")
                return lines
            
            for composer in all_composers:
                if not isinstance(composer, dict):
                    continue
                
                composer_id = composer.get('composerId', 'unknown')[:8]
                created_at = composer.get('createdAt', 0)
                
                if created_at:
                    dt = datetime.fromtimestamp(created_at / 1000)
                    lines.append(f"### Session `{composer_id}...` ({dt.strftime('%Y-%m-%d %H:%M')})")
                else:
                    lines.append(f"### Session `{composer_id}...`")
                
                lines.append("")
                
                mode = composer.get('unifiedMode', 'unknown')
                force_mode = composer.get('forceMode', 'unknown')
                lines.append(f"- **Mode**: {mode} (force: {force_mode})")
                
                lines_added = composer.get('totalLinesAdded', 0)
                lines_removed = composer.get('totalLinesRemoved', 0)
                lines.append(f"- **Changes**: +{lines_added} / -{lines_removed} lines")
                
                is_archived = composer.get('isArchived', False)
                has_unread = composer.get('hasUnreadMessages', False)
                status_parts = []
                if is_archived:
                    status_parts.append("archived")
                if has_unread:
                    status_parts.append("unread messages")
                if status_parts:
                    lines.append(f"- **Status**: {', '.join(status_parts)}")
                
                lines.append("")
        
        except Exception as e:
            logger.error(f"Error formatting composer data: {e}")
            lines.append(f"*Error parsing composer data: {e}*")
        
        return lines
    
    def _format_background_composer(self, bg_composer_data: Any) -> list:
        """Format background composer data."""
        lines = []
        
        try:
            if isinstance(bg_composer_data, bytes):
                data = json.loads(bg_composer_data.decode('utf-8'))
            elif isinstance(bg_composer_data, str):
                data = json.loads(bg_composer_data)
            else:
                data = bg_composer_data
            
            setup_step = data.get('setupStep')
            if setup_step:
                lines.append(f"- **Setup Step**: {setup_step}")
            
            terminals = data.get('terminals', [])
            if terminals:
                lines.append(f"- **Terminals**: {len(terminals)} configured")
            
            ran_commands = data.get('ranTerminalCommands', False)
            if ran_commands:
                lines.append("- **Terminal Commands**: Executed")
            
            git_state = data.get('gitState')
            if git_state:
                lines.append(f"- **Git State**: {git_state}")
        
        except Exception as e:
            logger.error(f"Error formatting background composer: {e}")
            lines.append(f"*Error parsing background composer data: {e}*")
        
        return lines
    
    def _format_agent_mode(self, agent_mode_data: Any) -> list:
        """Format agent mode exit info."""
        lines = []
        
        try:
            if isinstance(agent_mode_data, bytes):
                data = json.loads(agent_mode_data.decode('utf-8'))
            elif isinstance(agent_mode_data, str):
                data = json.loads(agent_mode_data)
            else:
                data = agent_mode_data
            
            was_visible = data.get('wasVisible', {})
            if was_visible:
                visible_parts = []
                if was_visible.get('panel'):
                    visible_parts.append('panel')
                if was_visible.get('auxiliaryBar'):
                    visible_parts.append('auxiliary bar')
                if was_visible.get('sideBar'):
                    visible_parts.append('side bar')
                
                if visible_parts:
                    lines.append(f"- Last exit had visible: {', '.join(visible_parts)}")
        
        except Exception as e:
            logger.error(f"Error formatting agent mode: {e}")
            lines.append(f"*Error parsing agent mode data: {e}*")
        
        return lines
    
    def _format_history_entries(self, history_data: Any) -> list:
        """Format file history entries."""
        lines = []
        
        try:
            if isinstance(history_data, bytes):
                entries = json.loads(history_data.decode('utf-8'))
            elif isinstance(history_data, str):
                entries = json.loads(history_data)
            else:
                entries = history_data
            
            if not entries:
                lines.append("*No file history*")
                return lines
            
            if isinstance(entries, list):
                lines.append("Recent files:")
                lines.append("")
                
                for entry in entries[:10]:  # Show last 10
                    if not isinstance(entry, dict):
                        continue
                    
                    editor = entry.get('editor', {})
                    resource = editor.get('resource', '')
                    
                    if resource:
                        # Extract filename from resource URI
                        if '/' in resource:
                            filename = resource.split('/')[-1]
                        else:
                            filename = resource
                        lines.append(f"- `{filename}`")
                
                if len(entries) > 10:
                    lines.append(f"- *...and {len(entries) - 10} more*")
        
        except Exception as e:
            logger.error(f"Error formatting history entries: {e}")
            lines.append(f"*Error parsing history entries: {e}*")
        
        return lines
    
    def _format_interactive_sessions(self, sessions_data: Any) -> list:
        """Format interactive sessions data."""
        lines = []
        
        try:
            if isinstance(sessions_data, bytes):
                sessions = json.loads(sessions_data.decode('utf-8'))
            elif isinstance(sessions_data, str):
                sessions = json.loads(sessions_data)
            else:
                sessions = sessions_data
            
            if not sessions:
                lines.append("*No interactive sessions*")
            else:
                lines.append(f"- Sessions data available: {len(sessions) if isinstance(sessions, list) else 'yes'}")
        
        except Exception as e:
            logger.error(f"Error formatting interactive sessions: {e}")
            lines.append(f"*Error parsing interactive sessions: {e}*")
        
        return lines
    
    def _format_workspace_info(self, workspace_info_data: Any) -> list:
        """Format workspace info."""
        lines = []
        
        try:
            if isinstance(workspace_info_data, bytes):
                info = workspace_info_data.decode('utf-8')
            elif isinstance(workspace_info_data, str):
                info = workspace_info_data
            else:
                info = str(workspace_info_data)
            
            # Try to parse as timestamp
            try:
                timestamp = int(info)
                dt = datetime.fromtimestamp(timestamp / 1000)
                lines.append(f"- **Workspace Opened**: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
            except ValueError:
                lines.append(f"- **Workspace Info**: {info}")
        
        except Exception as e:
            logger.error(f"Error formatting workspace info: {e}")
            lines.append(f"*Error parsing workspace info: {e}*")
        
        return lines
