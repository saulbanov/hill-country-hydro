"""Lay out the same public package for a Claude artifact. Offline; publishes nothing.

An artifact page is wrapped in its own document skeleton and may load scripts only from a short
CDN list, so this copies the public file plan, inlines every stylesheet (including the vendored
Leaflet one), strips the document tags from the front page and points document links at the
artifact's own root. Base-map tiles come from another host and will not load there; channels,
watersheds and readings are the page's own files and do.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
try:
    from . import package_regional_site as site
except ImportError:
    import package_regional_site as site

ROOT = Path(__file__).resolve().parents[1]
TITLE = 'Central Texas Water Ledger'
GUTTER = '<style>main,header,footer{padding-inline:max(16px,4vw)}</style>'


def inline_styles(html):
    def swap(match):
        href = match.group(1)
        source = ROOT/'app/vendor/leaflet.css' if 'leaflet' in href else ROOT/'app'/href
        return '<style>'+source.read_text()+'</style>'
    return re.sub(r'<link rel="stylesheet" href="([^"]+)">', swap, html)


def package(out):
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    files = site.plan(); site.check_inputs(files)
    for src, dst in files.items():
        if any(site.private_hits(ROOT/src)):
            raise ValueError(f'{src}: private content')
        target = out/dst; target.parent.mkdir(parents=True, exist_ok=True)
        if dst.endswith('.html'):
            html = inline_styles((ROOT/src).read_text()).replace('../docs/', 'docs/')
            if dst == 'index.html':
                body = html[html.index('<body>')+6:html.index('</body>')]
                styles = ''.join(re.findall(r'<style>.*?</style>', html[:html.index('<body>')], flags=re.S))
                html = f'<title>{TITLE}</title>{styles}{GUTTER}{body}'
            target.write_text(html)
        else:
            shutil.copy2(ROOT/src, target)
    manifest = {dst: dst for dst in files.values() if dst != 'index.html'}
    (out.parent/(out.name+'-files.json')).write_text(json.dumps(manifest))
    print(f'{len(files)} files in {out}; front page {len((out/"index.html").read_text())} bytes; {len(manifest)} supporting files')
    return manifest


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--out', type=Path, required=True); a = p.parse_args(); package(a.out)
