"""Fail without printing secret values. Inspect tracked source."""
from pathlib import Path
import re
import subprocess
import sys
paths=subprocess.check_output(['git','ls-files','-z']).decode('utf-8').split('\0')
patterns=[re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),re.compile(rb'GOCSPX-[A-Za-z0-9_-]{20,}'),re.compile(rb'AIza[A-Za-z0-9_-]{30,}'),re.compile(rb'1//[A-Za-z0-9_-]{40,}')]
failures=[]
for name in filter(None,paths):
    path=Path(name)
    if not path.is_file():continue
    if name=='.env' or name.startswith(('secrets/','factory-data/','scratch/')):failures.append(name+': runtime/private file tracked');continue
    if path.suffix in ('.png','.jpg','.jpeg','.gif','.woff','.woff2'):continue
    if any(pattern.search(path.read_bytes()) for pattern in patterns):failures.append(name+': possible credential')
if failures:print('\n'.join(failures));sys.exit(1)
print('Tracked-file credential patterns and private-path check passed.')
