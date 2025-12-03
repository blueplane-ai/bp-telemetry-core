#!/usr/bin/env python3
"""
Extract and dump ALL model usage information from Cursor's database.

This script demonstrates that Cursor DOES store model information in the
composerData.usageData field, contrary to earlier assumptions.

The model name is stored as the KEY of the usageData dictionary, with
cost and usage count as values.

Example data structure:
{
    "usageData": {
        "claude-4.5-opus-high-thinking": {
            "costInCents": 141,
            "amount": 23
        }
    }
}

Usage:
    python scripts/extract_cursor_model_usage.py
    python scripts/extract_cursor_model_usage.py --output model_usage_report.json
"""

import argparse
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def get_cursor_global_db_path() -> Path:
    """Get the path to Cursor's global database."""
    return Path.home() / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "state.vscdb"


def extract_model_usage_from_cursor() -> dict[str, Any]:
    """
    Extract all model usage information from Cursor's composerData.
    
    Returns a comprehensive report including:
    - All composers with model usage
    - Model usage aggregated across all composers
    - Cost totals by model
    """
    db_path = get_cursor_global_db_path()
    
    if not db_path.exists():
        return {"error": f"Cursor database not found at {db_path}"}
    
    report = {
        "extraction_timestamp": datetime.now(timezone.utc).isoformat(),
        "database_path": str(db_path),
        "composers_with_model_data": [],
        "composers_without_model_data": 0,
        "model_summary": defaultdict(lambda: {
            "total_cost_cents": 0,
            "total_responses": 0,
            "composer_count": 0
        }),
        "total_composers": 0,
        "total_cost_cents": 0,
    }
    
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Query all composerData entries
        cursor.execute("""
            SELECT key, value 
            FROM cursorDiskKV 
            WHERE key LIKE 'composerData:%'
        """)
        
        for row in cursor.fetchall():
            key = row['key']
            composer_id = key.replace('composerData:', '')
            
            try:
                value = row['value']
                if not value:
                    continue
                data = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            
            report["total_composers"] += 1
            
            usage_data = data.get('usageData', {})
            
            if not usage_data:
                report["composers_without_model_data"] += 1
                continue
            
            # Extract model information
            composer_info = {
                "composer_id": composer_id,
                "name": data.get('name', ''),
                "created_at": data.get('createdAt'),
                "last_updated_at": data.get('lastUpdatedAt'),
                "unified_mode": data.get('unifiedMode'),
                "is_agentic": data.get('isAgentic'),
                "total_token_count": data.get('tokenCount'),
                "models": []
            }
            
            for model_name, model_stats in usage_data.items():
                cost_cents = model_stats.get('costInCents', 0)
                amount = model_stats.get('amount', 0)
                
                composer_info["models"].append({
                    "model": model_name,
                    "cost_cents": cost_cents,
                    "response_count": amount
                })
                
                # Update model summary
                report["model_summary"][model_name]["total_cost_cents"] += cost_cents
                report["model_summary"][model_name]["total_responses"] += amount
                report["model_summary"][model_name]["composer_count"] += 1
                
                report["total_cost_cents"] += cost_cents
            
            report["composers_with_model_data"].append(composer_info)
        
        conn.close()
        
        # Convert defaultdict to regular dict for JSON serialization
        report["model_summary"] = dict(report["model_summary"])
        
        # Sort composers by last_updated_at (most recent first)
        report["composers_with_model_data"].sort(
            key=lambda x: x.get('last_updated_at') or 0,
            reverse=True
        )
        
    except Exception as e:
        report["error"] = str(e)
    
    return report


def print_report(report: dict[str, Any]) -> None:
    """Print a human-readable summary of the model usage report."""
    if "error" in report:
        print(f"Error: {report['error']}")
        return
    
    print("=" * 70)
    print("CURSOR MODEL USAGE EXTRACTION REPORT")
    print("=" * 70)
    print(f"\nExtraction Time: {report['extraction_timestamp']}")
    print(f"Database Path: {report['database_path']}")
    
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print("=" * 70)
    print(f"Total Composers: {report['total_composers']}")
    print(f"Composers with Model Data: {len(report['composers_with_model_data'])}")
    print(f"Composers without Model Data: {report['composers_without_model_data']}")
    print(f"Total Cost: ${report['total_cost_cents'] / 100:.2f}")
    
    print(f"\n{'=' * 70}")
    print("MODEL USAGE BY MODEL NAME")
    print("=" * 70)
    
    if report["model_summary"]:
        # Sort by total cost
        sorted_models = sorted(
            report["model_summary"].items(),
            key=lambda x: x[1]["total_cost_cents"],
            reverse=True
        )
        
        print(f"\n{'Model':<40} {'Responses':>10} {'Cost':>12} {'Composers':>10}")
        print("-" * 72)
        
        for model_name, stats in sorted_models:
            cost_dollars = stats["total_cost_cents"] / 100
            print(f"{model_name:<40} {stats['total_responses']:>10} ${cost_dollars:>10.2f} {stats['composer_count']:>10}")
    else:
        print("No model usage data found!")
    
    print(f"\n{'=' * 70}")
    print("RECENT COMPOSERS WITH MODEL DATA (Last 10)")
    print("=" * 70)
    
    for composer in report["composers_with_model_data"][:10]:
        print(f"\n  Composer: {composer['composer_id'][:8]}...")
        if composer.get('name'):
            name = composer['name'][:50] + "..." if len(composer.get('name', '')) > 50 else composer['name']
            print(f"  Name: {name}")
        if composer.get('last_updated_at'):
            ts = datetime.fromtimestamp(composer['last_updated_at'] / 1000)
            print(f"  Last Updated: {ts.isoformat()}")
        print(f"  Mode: {composer.get('unified_mode')} | Agentic: {composer.get('is_agentic')}")
        print(f"  Models Used:")
        for model in composer['models']:
            print(f"    - {model['model']}: {model['response_count']} responses, ${model['cost_cents']/100:.2f}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract model usage information from Cursor's database"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output JSON file path (optional)",
        type=str,
        default=None
    )
    parser.add_argument(
        "--json-only",
        help="Output only JSON (no human-readable summary)",
        action="store_true"
    )
    
    args = parser.parse_args()
    
    report = extract_model_usage_from_cursor()
    
    if args.json_only:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nFull report saved to: {args.output}")


if __name__ == "__main__":
    main()

