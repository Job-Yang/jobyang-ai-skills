#!/usr/bin/env python3
"""Replace one Lark image with an explicit apply gate and byte-verified readback.

Only calls the installed lark-cli; no embedded accounts or credentials.
Default is a read-only preview. --apply is for an explicitly authorized update.
"""
from __future__ import annotations
import argparse
import hashlib
import html
import json
import shutil
import struct
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data) >= 24:
        return struct.unpack('>II', data[16:24])
    return None


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def cli(args: list[str], cwd: Path | None = None) -> dict:
    r = subprocess.run(['lark-cli', *args, '--as', 'user'], cwd=cwd,
                       capture_output=True, text=True, timeout=120)
    raw = r.stdout.strip() or r.stderr.strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError('lark-cli did not return JSON: ' + raw[:800]) from exc
    if r.returncode or not result.get('ok'):
        raise RuntimeError(json.dumps(result, ensure_ascii=False))
    return result


def document(result: dict) -> dict:
    return result['data']['document']


def image_nodes(content: str) -> list[ET.Element]:
    return list(ET.fromstring('<root>' + content + '</root>').iter('img'))


def replace(doc: str, block_id: str, image: Path, expected_token: str,
            caption: str, apply: bool = False) -> dict:
    data = image.read_bytes()
    if not (data.startswith(b'\x89PNG\r\n\x1a\n') or data.startswith(b'\xff\xd8\xff')):
        raise ValueError('Image must be an actual PNG/JPEG, not an error page or placeholder')
    if not 20_000 <= len(data) <= 20 * 1024 * 1024:
        raise ValueError('Image size is outside 20KB–20MiB')
    dims = png_dimensions(data)
    if dims and (min(dims) < 500 or max(dims) < 1000):
        raise ValueError('Image is too small for the technical infographic')
    old = document(cli(['docs', '+fetch', '--doc', doc, '--detail', 'full']))
    old_nodes = image_nodes(old['content'])
    matches = [e for e in old_nodes if e.get('id') == block_id]
    if len(matches) != 1:
        raise ValueError('Target image block is missing or ambiguous')
    if matches[0].get('src') != expected_token:
        raise ValueError('Target image changed since observation; refetch before updating')
    summary = {'document_id': old['document_id'], 'before_revision': old['revision_id'],
               'block_id': block_id, 'old_token': expected_token,
               'image': str(image.resolve()), 'sha256': sha(data),
               'size': len(data), 'dimensions': dims, 'caption': caption,
               'applied': False}
    if not apply:
        summary['status'] = 'preview_only'
        return summary
    before_ids = {e.get('id') for e in old_nodes}
    # This owned temp directory contains only the image and XML we deliberately copy.
    # Old CLI versions require @./ references within CWD.
    with tempfile.TemporaryDirectory(prefix='content-infographic-publish-') as tmp:
        work = Path(tmp)
        suffix = '.png' if data.startswith(b'\x89PNG') else '.jpg'
        shutil.copyfile(image, work / ('image' + suffix))
        payload = '<img path="@./image' + suffix + '" caption="' + html.escape(caption, quote=True) + '"/>'
        (work / 'image.xml').write_text(payload)
        changed = cli(['docs', '+update', '--doc', doc, '--command', 'block_replace',
                       '--block-id', block_id, '--revision-id', str(old['revision_id']),
                       '--content', '@./image.xml'], cwd=work)
        update = changed['data']
        if update.get('result') != 'success' or update.get('warnings'):
            raise RuntimeError('Image write not fully successful: ' + json.dumps(update, ensure_ascii=False))
        after = document(cli(['docs', '+fetch', '--doc', doc, '--detail', 'full']))
        if after['revision_id'] != update['document']['revision_id']:
            raise RuntimeError('Concurrent edit after write; image is written but final state needs verification')
        created = [e for e in image_nodes(after['content'])
                   if e.get('id') not in before_ids and e.get('caption', '').strip() == caption.strip()]
        if len(created) != 1:
            # Some servers retain the block ID on replacement.
            created = [e for e in image_nodes(after['content'])
                       if e.get('id') == block_id and e.get('src') != expected_token]
        if len(created) != 1:
            raise RuntimeError('Write succeeded but new image cannot be uniquely identified')
        node = created[0]
        downloaded = cli(['docs', '+media-download', '--token', node.get('src', ''),
                          '--output', './readback'], cwd=work)
        saved = Path(downloaded['data']['saved_path'])
        if not saved.resolve().is_relative_to(work.resolve()):
            raise RuntimeError('Readback path is outside the owned temporary directory')
        returned = saved.read_bytes()
        if sha(returned) != sha(data):
            raise RuntimeError('Image is written but original-byte readback differs; inspect before reporting success')
        summary.update(applied=True, status='verified', after_revision=after['revision_id'],
                       new_block_id=node.get('id'), new_token=node.get('src'),
                       readback_sha256=sha(returned))
    return summary


def main() -> int:
    a = argparse.ArgumentParser(description=__doc__)
    a.add_argument('--doc', required=True)
    a.add_argument('--block-id', required=True)
    a.add_argument('--expected-token', required=True)
    a.add_argument('--image', type=Path, required=True)
    a.add_argument('--caption', required=True)
    a.add_argument('--apply', action='store_true', help='Write only after explicit authorization')
    a.add_argument('--receipt', type=Path)
    args = a.parse_args()
    try:
        result = replace(args.doc, args.block_id, args.image, args.expected_token,
                         args.caption, args.apply)
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, RuntimeError, KeyError, OSError, ET.ParseError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'status': 'failed_or_unverified', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
