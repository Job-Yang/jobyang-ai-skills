#!/usr/bin/env python3
"""Native image generation through the documented Ferry + Codex route.

Uses an isolated CODEX_HOME and the already-running local Ferry gateway. Never
logs out a user, changes their client config, starts a monitor, or substitutes a
programmatically drawn PNG for native image generation. Official Codex binaries
are provided by the user/installer and checked against the local pinned manifest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path
try:
    import tomllib
except ImportError:  # Other backends and the renderer still support Python 3.8+.
    tomllib = None

CACHE = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home() / '.cache'))) / 'content-infographic' / 'ferry-codex'


def available() -> bool:
    return bool(sys.version_info >= (3, 11) and shutil.which('ferry') and binary_path().is_file())


def binary_path() -> Path:
    override = os.environ.get('CI_IMAGE_CODEX_BIN')
    return Path(override).expanduser() if override else CACHE / 'codex'


def image_format(data: bytes) -> str | None:
    if data.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if data.startswith(b'\xff\xd8\xff'):
        return 'jpeg'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'webp'
    return None


def collect_native_candidates(home: Path) -> list[tuple[Path, bytes, str]]:
    native = home / 'generated_images'
    if not native.exists():
        return []

    candidates = []
    for file in native.rglob('*'):
        if not file.is_file() or not file.name.startswith('call_'):
            continue
        data = file.read_bytes()
        fmt = image_format(data)
        if len(data) >= 20_000 and fmt:
            candidates.append((file, data, fmt))
    candidates.sort(key=lambda candidate: candidate[0].stat().st_mtime_ns)
    return candidates


def preserve_candidates(candidates: list[tuple[Path, bytes, str]],
                        target: Path) -> list[dict[str, str]]:
    outputs = []
    suffixes = {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}
    for index, (_, data, fmt) in enumerate(candidates, start=1):
        path = target.with_name(f'{target.stem}.candidate-{index}{suffixes[fmt]}')
        if path.exists():
            raise ValueError('Candidate evidence already exists; choose a new output path')
        outputs.append((path, data))

    evidence = []
    for path, data in outputs:
        path.write_bytes(data)
        evidence.append({'file': str(path), 'sha256': hashlib.sha256(data).hexdigest()})
    return evidence


def preserve_run_artifacts(run: Path, target: Path) -> dict[str, str]:
    artifacts = {}
    for name in ('events.jsonl', 'stderr.log', 'result.txt'):
        source = run / name
        if not source.is_file():
            continue
        destination = target.with_suffix(target.suffix + f'.{name}')
        shutil.copyfile(source, destination)
        artifacts[name] = str(destination)
    return artifacts


def write_receipt(path: Path, receipt: dict[str, object]) -> None:
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2))


def isolated_config() -> str:
    if tomllib is None:
        raise ValueError('Ferry native adapter requires Python 3.11+; other backends remain usable')
    proc = subprocess.run(['ferry', 'config', 'codex'], capture_output=True,
                          text=True, timeout=30, check=True)
    match = re.search(r'(?m)^model_provider\s*=', proc.stdout)
    if not match:
        raise RuntimeError('Ferry did not return its documented Codex configuration')
    config = proc.stdout[match.start():].split('[mcp_servers.ferry]', 1)[0].strip() + '\n'
    parsed = tomllib.loads(config)
    if parsed.get('model_provider') != 'ferry':
        raise RuntimeError('Expected the explicit Ferry provider, not an official subscription')
    provider = parsed.get('model_providers', {}).get('ferry', {})
    from urllib.parse import urlsplit
    url = urlsplit(provider.get('base_url', ''))
    if url.scheme != 'http' or url.hostname not in ('127.0.0.1', 'localhost', '::1'):
        raise RuntimeError('Ferry must use its local gateway')
    if provider.get('http_headers', {}).get('x-openai-actor-authorization') != 'ferry':
        raise RuntimeError('Ferry image actor header is missing; update the documented config')
    return config


def generate(prompt: str, out: str, *, dry_run: bool = False,
             timeout: int = 600) -> int | None:
    binary = binary_path().resolve()
    if not binary.is_file() or not shutil.which('ferry'):
        raise ValueError('Ferry/Codex native backend is not provisioned; see references/ferry-codex.md')
    manifest = CACHE / 'manifest.json'
    if manifest.is_file() and not os.environ.get('CI_IMAGE_CODEX_BIN'):
        pinned = json.loads(manifest.read_text())
        if hashlib.sha256(binary.read_bytes()).hexdigest() != pinned['binary_sha256']:
            raise RuntimeError('Cached Codex differs from the verified official binary')
    config = isolated_config()
    if dry_run:
        print(json.dumps({'backend': 'ferry_codex', 'binary': str(binary),
                          'isolated_account': True, 'new_api_key_required': False,
                          'output': str(Path(out).resolve())}, ensure_ascii=False))
        return None
    target = Path(out).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise ValueError('Output already exists; choose a new path rather than overwriting an image')
    target_receipt = target.with_suffix(target.suffix + '.receipt.json')
    with tempfile.TemporaryDirectory(prefix='native-image-') as tmp:
        run = Path(tmp)
        home = run / 'client-home'
        work = run / 'work'
        home.mkdir(mode=0o700)
        work.mkdir()
        (home / 'config.toml').write_text(config)
        (work / 'prompt.txt').write_text(prompt)
        env = os.environ.copy()
        env['CODEX_HOME'] = str(home)
        directive = prompt + '''\n\n执行要求：调用实际可用的原生图片生成工具，只生成一张位图，不用 SVG、Python/HTML/ASCII 绘图代替，不派其他 Agent。除非提示词另有明确比例，图像工具选择横向宽画布，size 若支持则设为 1536x1024 或同为 3:2 的更高分辨率，不用 auto、square 或 portrait。不要修改任何账户或全局配置。必要的内置图片工具说明可读，其他私人文件不得读取。图像工具返回后直接报告它给出的原始缓存路径，不执行 cp、mv、rm、sips、Python 等文件操作，不拉伸、裁剪或改写生成图片；本脚本会负责保存和格式规范化。没有图就报失败，不编造路径。'''
        proc = None
        timeout_error = None
        try:
            with (run / 'events.jsonl').open('w') as stdout, (run / 'stderr.log').open('w') as stderr:
                proc = subprocess.run([str(binary), '-a', 'never', 'exec', '--ephemeral',
                                       '--skip-git-repo-check', '-s', 'workspace-write',
                                       '-C', str(work), '--json', '-o', str(run / 'result.txt'), '-'],
                                      env=env, input=directive, text=True,
                                      stdout=stdout, stderr=stderr, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            timeout_error = exc

        run_artifacts = preserve_run_artifacts(run, target)
        candidates = collect_native_candidates(home)
        raw_copy = None
        if candidates:
            source, data, fmt = candidates[-1]
            raw_suffix = {'png': '.png', 'jpeg': '.jpg', 'webp': '.webp'}[fmt]
            raw_copy = target.with_name(target.stem + '.native' + raw_suffix)
            if raw_copy.exists():
                raise ValueError('Native evidence output already exists; choose a new output path')

        evidence_candidates = preserve_candidates(candidates, target)
        if raw_copy:
            raw_copy.write_bytes(data)

        failure_receipt = target.with_suffix(target.suffix + '.failed.json')
        failure_details = {
            'native_image_count': len(candidates),
            'candidates': evidence_candidates,
            'run_artifacts': run_artifacts,
        }
        if raw_copy:
            failure_details['native_file'] = str(raw_copy)

        if timeout_error:
            write_receipt(failure_receipt, {
                'status': 'timeout_unverified',
                'do_not_auto_retry': True,
                **failure_details,
            })
            raise RuntimeError(
                'Native generation timed out; do not assume it failed before retrying'
            ) from timeout_error

        if proc is None or proc.returncode or not candidates:
            exit_code = proc.returncode if proc else None
            error = (run / 'stderr.log').read_text(errors='replace')[:500]
            write_receipt(failure_receipt, {
                'status': 'no_verified_image',
                'exit_code': exit_code,
                **failure_details,
            })
            raise RuntimeError(
                'No verified native image was produced; exit=' + str(exit_code) + ' ' + error
            )

        # The model may refine a completed first image. Keep every real candidate,
        # use the latest native artifact, and leave semantic acceptance to the caller.
        try:
            if target.suffix.lower() == '.png' and fmt != 'png':
                if not shutil.which('sips'):
                    raise RuntimeError(
                        'Native output is ' + fmt + '; choose .jpg/.webp or install a PNG converter'
                    )
                converted = run / 'converted.png'
                subprocess.run(['sips', '-s', 'format', 'png', str(source), '--out', str(converted)],
                               capture_output=True, timeout=60, check=True)
                data = converted.read_bytes()
                if image_format(data) != 'png':
                    raise RuntimeError('PNG normalization failed')
            target.write_bytes(data)
            output_format = image_format(data)
            dimensions = struct.unpack('>II', data[16:24]) if output_format == 'png' else None
            receipt = {'status': 'native_image_saved', 'backend': 'ferry_codex',
                       'native_source': str(source.relative_to(home)),
                       'native_file': str(raw_copy),
                       'native_sha256': hashlib.sha256(candidates[-1][1]).hexdigest(),
                       'sha256': hashlib.sha256(data).hexdigest(),
                       'format': output_format, 'dimensions': dimensions,
                       'size': len(data), 'output': str(target),
                       'native_candidate_count': len(candidates), 'candidates': evidence_candidates,
                       'run_artifacts': run_artifacts,
                       'prompt_sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                       'note': 'This proves native generation and saving, not semantic/visual acceptance.'}
            write_receipt(target_receipt, receipt)
        except (ValueError, RuntimeError, OSError, struct.error,
                subprocess.SubprocessError) as exc:
            write_receipt(failure_receipt, {
                'status': 'output_save_failed',
                'error': str(exc),
                **failure_details,
            })
            raise
        return len(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prompt-file', type=Path, required=True)
    parser.add_argument('-o', '--out', required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    try:
        n = generate(args.prompt_file.read_text(), args.out, dry_run=args.dry_run)
        print(json.dumps({'output': args.out, 'bytes': n}, ensure_ascii=False))
        return 0
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        print(json.dumps({'status': 'failed_or_unverified', 'error': str(exc)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
