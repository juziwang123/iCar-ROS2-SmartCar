"""Safe, dependency-free mission report export helpers."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any, Dict


class ReportExportError(ValueError):
    """Raised when a report cannot be written inside its managed directory."""


def export_report(report: Dict[str, Any], reports_root: str) -> str:
    """Write JSON and a small self-contained HTML report and return the JSON path.

    Evidence is referenced only by the already validated paths in the database;
    it is never copied or served by this function.
    """
    mission_id = str(report.get('mission', {}).get('mission_id', ''))
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', mission_id):
        raise ReportExportError('mission_id is unsafe for a report filename')
    root = Path(reports_root).expanduser().resolve()
    destination = (root / mission_id).resolve()
    if destination.parent != root:
        raise ReportExportError('report destination escapes the managed reports root')
    destination.mkdir(parents=True, exist_ok=True)
    json_path = destination / 'report.json'
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding='utf-8')
    (destination / 'report.html').write_text(_html_report(report), encoding='utf-8')
    return str(json_path)


def _html_report(report: Dict[str, Any]) -> str:
    mission = report.get('mission', {})
    summary = report.get('summary', {})
    rows = []
    for key, value in summary.items():
        rows.append(f'<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>')
    events = report.get('events', [])
    event_rows = ''.join(
        '<tr>' + ''.join(
            f'<td>{html.escape(str(event.get(key, "")))}</td>'
            for key in ('created_at', 'state', 'checkpoint_id', 'code', 'detail')
        ) + '</tr>'
        for event in events
    )
    return f'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><title>iCar mission report</title>
<style>body{{font-family:sans-serif;margin:2rem}}table{{border-collapse:collapse}}th,td{{border:1px solid #bbb;padding:.4rem;text-align:left}}th{{background:#f3f3f3}}</style>
<h1>iCar 巡检报告</h1>
<p>任务：{html.escape(str(mission.get('mission_id', '')))}；状态：{html.escape(str(mission.get('state', '')))}</p>
<h2>汇总</h2><table>{''.join(rows)}</table>
<h2>事件</h2><table><tr><th>时间</th><th>状态</th><th>检查点</th><th>代码</th><th>详情</th></tr>{event_rows}</table>
</html>'''
