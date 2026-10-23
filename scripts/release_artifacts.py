"""Build standard public artifacts and checksums from the release source."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]

def main():
    destination = ROOT/'dist'; destination.mkdir(exist_ok=True)
    package = json.loads((ROOT/'package.json').read_text()); version=package['version']
    sys.path.insert(0,str(ROOT/'src'))
    from archctl import __version__
    if version != __version__: raise RuntimeError('Python/npm versions differ')
    # Stable timestamps let both npm's bundled wheel and direct distribution
    # identify the same bytes when built from one release commit.
    epoch = subprocess.run(['git','-C',str(ROOT),'log','-1','--format=%ct'],capture_output=True,text=True)
    environment = {**os.environ, 'SOURCE_DATE_EPOCH':os.environ.get('SOURCE_DATE_EPOCH') or epoch.stdout.strip() or '315532800'}
    subprocess.run([sys.executable,'-m','build','--no-isolation','--outdir',str(destination)],cwd=ROOT,env=environment,check=True)
    subprocess.run([sys.executable, str(ROOT/'scripts/build_npm.py')], cwd=ROOT, env=environment, check=True)
    packed = subprocess.run(['npm','pack','--ignore-scripts','--json','--pack-destination',str(destination)],cwd=ROOT,env=environment,capture_output=True,text=True,check=True)
    tarball = destination/json.loads(packed.stdout)[0]['filename']
    skill=destination/f'architecture-control-skill-{version}.zip'
    with zipfile.ZipFile(skill,'w',compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((ROOT/'skills/architecture-control').rglob('*')):
            if path.is_file():
                info=zipfile.ZipInfo(path.relative_to(ROOT/'skills').as_posix(),date_time=(1980,1,1,0,0,0))
                info.compress_type=zipfile.ZIP_DEFLATED; info.external_attr=0o100644<<16
                archive.writestr(info,path.read_bytes())
        archive.writestr("architecture-control/LICENSE", (ROOT/"LICENSE").read_bytes())
    artifacts=[destination/f'archclt-{version}-py3-none-any.whl',destination/f'archclt-{version}.tar.gz',tarball,skill]
    bundled=json.loads((ROOT/'npm/runtime/manifest.json').read_text())
    wheel_digest=hashlib.sha256(artifacts[0].read_bytes()).hexdigest()
    if bundled['sha256'] != wheel_digest: raise RuntimeError('npm wheel differs from direct release wheel')
    (destination/'SHA256SUMS').write_text(''.join(f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in artifacts))
    print('\n'.join(str(p) for p in artifacts))
    return 0

if __name__=='__main__': raise SystemExit(main())
