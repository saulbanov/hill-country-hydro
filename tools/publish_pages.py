#!/usr/bin/env python3
"""Publish the water map to GitHub Pages (PAGES_REMOTE), the map's real address since 2026-10-09.

Builds the same public package as package_regional_site.py (its file plan, input checks and
private-content checks), then makes it work one folder down: the pages live at the package root
but were written for app/, so their "../dist/", "../data/" and "../docs/" paths become "dist/",
"data/" and "docs/". Refuses to publish if any "../" path remains. Stamps pages-source.json with
the source commit, commits to the Pages repo only when files changed, and pushes.

  publish_pages.py                 build and publish
  publish_pages.py --dry-run DIR   build into DIR only
  publish_pages.py --daily         as the daily run calls it, after the day's water commit lands:
                                   publishes only a complete bundle generated today, logs every
                                   outcome, and always exits 0
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import package_regional_site as site  # noqa: E402

PAGES_REMOTE = os.environ.get('PAGES_REMOTE', 'https://github.com/saulbanov/hill-country-hydro-map.git')
PAGES_URL = 'https://saulbanov.github.io/hill-country-hydro-map/'
UP_PATH = re.compile(r'''(['"`(])\.\./(dist|data|docs)/''')
ANY_UP = re.compile(r'''['"`(]\.\./''')
LOCAL_TZ = ZoneInfo('America/Chicago')


def rewrite_up_paths(text: str) -> str:
    return UP_PATH.sub(lambda m: m.group(1) + m.group(2) + '/', text)


def build(out: Path) -> dict:
    files = site.plan()
    snap = site.check_inputs(files)
    dirty = subprocess.run(('git', 'status', '--porcelain', '--', *files), cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise ValueError('packaged files have uncommitted changes, so the source commit would not describe them; commit first: ' + dirty.splitlines()[0])
    if any(src.endswith(site.BLOCKED_SUFFIXES) for src in files):
        raise ValueError('a raw capture, store or collector is in the package plan')
    for src in files:
        hits = site.private_hits(ROOT / src)
        if hits:
            raise ValueError(f'{src}: private content {hits}')
    for src, dst in files.items():
        target = out / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / src, target)
    left = []
    for page in [p for p in out.iterdir() if p.suffix in ('.html', '.js')]:
        text = rewrite_up_paths(page.read_text())
        page.write_text(text)
        left += [f'{page.name}: {m.group(0)}' for m in ANY_UP.finditer(text)]
    if left:
        raise ValueError('paths that climb above the site remain: ' + '; '.join(left[:5]))
    site.check_links(out)
    commit = subprocess.run(('git', 'rev-parse', 'HEAD'), cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    (out / '.nojekyll').touch()
    (out / 'pages-source.json').write_text(json.dumps({
        'source_repo': 'saulbanov/hill-country-hydro', 'source_commit': commit,
        'built_by': 'tools/publish_pages.py', 'snapshot_publication_date': snap.get('publication_date')}, indent=2) + '\n')
    return {'files': len(files), 'commit': commit}


def bundle_problem() -> str | None:
    """The runner's own checks on dist/water-state.json, so a broken day is not published."""
    data = json.loads((ROOT / 'dist/water-state.json').read_text())
    if data.get('missing_inputs') != []:
        return 'bundle has missing inputs'
    generated = dt.datetime.fromisoformat(data['generated_at']).astimezone(LOCAL_TZ).date()
    if generated != dt.datetime.now(LOCAL_TZ).date():
        return f'bundle was generated {generated}, not today'
    return None


def publish() -> str:
    work = Path(tempfile.mkdtemp())
    try:
        git = lambda *a: subprocess.run(('git', *a), cwd=work / 'site', check=True, capture_output=True, text=True)
        subprocess.run(('git', 'clone', '--quiet', '--depth', '1', PAGES_REMOTE, str(work / 'site')), check=True, capture_output=True, text=True)
        subprocess.run(('git', '-C', str(work / 'site'), 'checkout', '--quiet', '-B', 'main'), check=True, capture_output=True, text=True)
        built = work / 'built'
        info = build(built)
        subprocess.run(('rsync', '-a', '--delete', '--exclude', '.git', f'{built}/', f'{work / "site"}/'), check=True)
        git('add', '-A')
        if subprocess.run(('git', 'diff', '--cached', '--quiet'), cwd=work / 'site').returncode == 0:
            return f'WATER PAGES UNCHANGED at {info["commit"][:8]}'
        git('commit', '--quiet', '-m', f'Publish from hill-country-hydro {info["commit"][:8]}')
        git('push', '--quiet', 'origin', 'main')
        return f'WATER PAGES PUSHED {info["files"]} files from {info["commit"][:8]} to {PAGES_URL}'
    finally:
        shutil.rmtree(work, ignore_errors=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dry-run', type=Path, metavar='DIR')
    p.add_argument('--daily', action='store_true')
    a = p.parse_args(argv)
    if a.dry_run:
        if a.dry_run.exists():
            shutil.rmtree(a.dry_run)
        info = build(a.dry_run)
        print(f'WATER PAGES DRY RUN {info["files"]} files from {info["commit"][:8]} in {a.dry_run}')
        return 0
    if not a.daily:
        print(publish())
        return 0
    try:
        problem = bundle_problem()
        print(f'WATER PAGES SKIPPED — {problem}' if problem else publish())
    except Exception as exc:  # the daily run must not fail because of publishing
        detail = getattr(exc, 'stderr', '') or ''
        print(f'WATER PAGES FAILED — {exc} {str(detail).strip()[:300]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
