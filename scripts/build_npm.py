"""Bundle the exact Python wheel in the npm distribution."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    destination = ROOT / 'npm/runtime'
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='archclt-wheel-') as temporary:
        subprocess.run([sys.executable, '-m', 'pip', 'wheel', '--no-deps', '--no-build-isolation',
                        '--disable-pip-version-check', '--wheel-dir', temporary, str(ROOT)], check=True)
        wheels = list(Path(temporary).glob('archclt-*.whl'))
        if len(wheels) != 1:
            raise RuntimeError('Expected one archclt wheel')
        wheel = wheels[0]; raw = wheel.read_bytes()
        for old in destination.glob('*.whl'): old.unlink()
        (destination / wheel.name).write_bytes(raw)
        version = json.loads((ROOT / 'package.json').read_text())['version']
        if not wheel.name.startswith(f'archclt-{version}-'):
            raise RuntimeError('npm and Python versions disagree')
        manifest = {'version': version, 'wheel': wheel.name, 'sha256': hashlib.sha256(raw).hexdigest(),
                    'pyyaml': '6.0.3'}
        (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    return 0

if __name__ == '__main__': raise SystemExit(main())
