#!/usr/bin/env python3
"""Public-tree YAML/include/link/secret guard. Complements manual diff review."""
import ast
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]


class Loader(yaml.SafeLoader):
    pass


def mapping(loader, node, deep=False):
    result = {}
    for key, value in node.value:
        key = loader.construct_object(key, deep=deep)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value, deep=deep)
    return result


Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
for tag in ('!secret', '!include', '!include_dir_merge_list'):
    Loader.add_constructor(tag, lambda loader, node: loader.construct_scalar(node))


def public_files():
    result = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=ROOT)
    return sorted(set(Path(p.decode()) for p in result.split(b'\0') if p))


def main():
    failures = []
    files = public_files()
    secrets = [
        r'gh[pousr]_[A-Za-z0-9]{30,}', r'github_pat_[A-Za-z0-9_]{40,}',
        r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        r'(?i)bearer\s+[A-Za-z0-9_.-]{30,}', r'\bSmartBat-[AB]\d+\b',
        r'\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b',
    ]
    for relative in files:
        path = ROOT / relative
        if relative.name in ('.env', 'secrets.yaml', 'config.json') or any(
            part in ('.storage', 'custom_components', 'backups', 'private', 'runtime') for part in relative.parts
        ) or path.suffix in ('.db', '.so', '.key', '.pem', '.zip', '.gpg', '.age'):
            failures.append(f'{relative}: forbidden private/generated path')
            continue
        if not path.is_file():
            continue
        try:
            content = path.read_text()
        except UnicodeDecodeError:
            failures.append(f'{relative}: unexpected binary')
            continue
        for pattern in secrets:
            if re.search(pattern, content):
                failures.append(f'{relative}: possible identifier/secret (inspect privately)')
        if path.suffix in ('.yaml', '.yml'):
            try:
                yaml.load(content, Loader=Loader)
            except (yaml.YAMLError, ValueError) as exc:
                failures.append(f'{relative}: invalid YAML ({type(exc).__name__})')
            if relative.parts[0] == 'homeassistant':
                for include in re.findall(r'!include(?:_dir_merge_list)?\s+([^\s#]+)', content):
                    if not (path.parent / include).exists():
                        failures.append(f'{relative}: missing include {include}')
        if path.suffix == '.py':
            try:
                ast.parse(content)
            except SyntaxError:
                failures.append(f'{relative}: Python syntax error')
        if path.suffix == '.md':
            for target in re.findall(r'\]\(([^)]+)\)', content):
                if ':' not in target and not target.startswith('#') and not (path.parent / target.split('#')[0]).exists():
                    failures.append(f'{relative}: missing link target {target}')
    if failures:
        print('\n'.join(failures), file=sys.stderr)
        raise SystemExit(1)
    print(f'Validated {len(files)} public paths: YAML/Python/includes/links/credential patterns. Manual privacy review still required.')


if __name__ == '__main__':
    main()
