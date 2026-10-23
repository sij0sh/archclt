"""Install the packed npm artifact in a separate project and run the real CLI."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

def main():
    version=json.loads((ROOT/'package.json').read_text())['version']
    artifact=ROOT/'dist'/f'archclt-archctl-{version}.tgz'
    if not artifact.is_file():raise RuntimeError('Build release artifacts before npm smoke')
    with tempfile.TemporaryDirectory(prefix='archclt-npm-smoke-') as temporary:
        base=Path(temporary); consumer=base/'consumer'; consumer.mkdir()
        env={**os.environ,'ARCHCLT_HOME':str(base/'runtime'),'ARCHCLT_PYTHON':sys.executable}
        env.pop('PYTHONPATH',None)
        npm='npm.cmd' if os.name=='nt' else 'npm'
        def run(args,expected=0):
            result=subprocess.run(args,cwd=consumer,env=env,capture_output=True,text=True)
            if result.returncode != expected:raise RuntimeError(f'{args}: {result.stdout}\n{result.stderr}')
            return result.stdout.strip()
        run([npm,'install','--ignore-scripts','--no-audit','--no-fund',str(artifact)])
        launcher=consumer/'node_modules/.bin'/('archctl.cmd' if os.name=='nt' else 'archctl')
        run(['git','init','-q'])
        cli=[str(launcher)]
        if run(cli+['--version']) != version:raise RuntimeError('Packed npm version mismatch')
        runtime=Path(run(cli+['--runtime-path']))
        if runtime.is_relative_to(consumer):raise RuntimeError('Runtime installed inside the application')
        run(cli+['init'])
        status=json.loads(run(cli+['status'],expected=2))
        if status['schema_version']!='archctl.status.v2' or status['status']!='needs_attention':
            raise RuntimeError('Unexpected neutral readiness contract')
        run(cli+['unknown-command'],expected=3)
        run(cli+['install-skill',str(base/'skills')])
        if not (base/'skills/architecture-control/references/change.md').is_file():
            raise RuntimeError('Packed npm skill is incomplete')
        print(json.dumps({'status':'passed','version':version,'external_runtime':True,'neutral_status':status['status'],
                          'exit_status_preserved':True,'skill_installed':True}))
    return 0

if __name__=='__main__':raise SystemExit(main())
