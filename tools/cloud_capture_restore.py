"""Restore cloud-session captures (_cloud-captures/<session>/) into data/raw/ with checksum verification.

Each capture folder carries manifest.jsonl, one row per file: ts, tool, request, body_sha256, body_bytes,
session, origin, stored_as, restore_to, meta. A row's file is gzipped when stored_as ends in .gz.
Rules: gunzip when needed; verify sha256 and length against the manifest; copy to restore_to under
--root (default: this repo); never overwrite a local file whose checksum differs (keep both: the restored
copy gets a .attempt-N suffix, as historical_backfill.py does); skip files already present and identical.
Dry-run with --check to see what would happen. Prints one line per outcome and a summary.
"""
import argparse, gzip, hashlib, json, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def restore(folder, root, check=False):
    manifest = folder / 'manifest.jsonl'
    if not manifest.exists(): raise SystemExit(f'{folder}: no manifest.jsonl')
    counts = {'restored': 0, 'identical': 0, 'kept_both': 0, 'checksum_mismatch': 0, 'missing_in_folder': 0}
    for line in manifest.read_text().splitlines():
        if not line.strip(): continue
        row = json.loads(line); src = folder / row['stored_as']
        if not src.exists(): counts['missing_in_folder'] += 1; print(f"MISSING  {row['stored_as']}"); continue
        body = gzip.decompress(src.read_bytes()) if row['stored_as'].endswith('.gz') else src.read_bytes()
        sha = hashlib.sha256(body).hexdigest()
        if sha != row['body_sha256'] or len(body) != row['body_bytes']:
            counts['checksum_mismatch'] += 1; print(f"BAD      {row['stored_as']}: sha/length differ from manifest; not restored"); continue
        dest = root / row['restore_to']; meta_src = folder / row['meta'] if row.get('meta') else None
        if dest.exists():
            if hashlib.sha256(dest.read_bytes()).hexdigest() == sha: counts['identical'] += 1; continue
            n = 1
            while dest.with_name(dest.name + f'.attempt-{n}').exists(): n += 1
            dest = dest.with_name(dest.name + f'.attempt-{n}'); counts['kept_both'] += 1; print(f"KEPT     {row['restore_to']} -> {dest.name} (local file differs)")
        else: counts['restored'] += 1
        if not check:
            dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes(body)
            if meta_src and meta_src.exists():
                meta_dest = dest.with_suffix('').with_suffix('.meta.json') if not dest.name.endswith('.meta.json') else dest
                if not meta_dest.exists(): shutil.copyfile(meta_src, meta_dest)
    print(f"{folder.name}: {counts}{' (check only)' if check else ''}")
    return counts

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('folders', nargs='*', help='capture folders; default: every _cloud-captures/* under --root'); p.add_argument('--root', default=str(ROOT)); p.add_argument('--check', action='store_true')
    a = p.parse_args(); root = Path(a.root).resolve()
    folders = [Path(f).resolve() for f in a.folders] or sorted((root / '_cloud-captures').glob('session_*'))
    for f in folders: restore(f, root, a.check)
