#!/usr/bin/env node
'use strict';
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const packageRoot = path.resolve(__dirname, '../..');

function run(executable, args, options = {}) {
  const result = spawnSync(executable, args, {stdio: 'inherit', ...options});
  if (result.error) throw new Error(`Cannot run ${executable}: ${result.error.message}`);
  if (result.signal) throw new Error(`${executable} terminated by ${result.signal}`);
  if (result.status !== 0) throw new Error(`${executable} exited with ${result.status}`);
  return result;
}
function runtimeLocation(root = packageRoot, environment = process.env) {
  const manifest = JSON.parse(fs.readFileSync(path.join(root, 'npm/runtime/manifest.json'), 'utf8'));
  const wheel = path.join(root, 'npm/runtime', manifest.wheel);
  if (crypto.createHash('sha256').update(fs.readFileSync(wheel)).digest('hex') !== manifest.sha256)
    throw new Error('Bundled Python wheel checksum mismatch');
  const base = environment.ARCHCLT_HOME || path.join(os.homedir(), '.local/share/archclt');
  const directory = path.resolve(base, manifest.version, manifest.sha256.slice(0, 16));
  const executable = path.join(directory, process.platform === 'win32' ? 'Scripts/archctl.exe' : 'bin/archctl');
  return {manifest, wheel, directory, executable};
}
function ensureRuntime(root = packageRoot) {
  const runtime = runtimeLocation(root);
  const repository = spawnSync('git', ['rev-parse', '--show-toplevel'], {encoding: 'utf8'});
  const application = repository.status === 0 ? path.resolve(repository.stdout.trim()) : null;
  const relative = application ? path.relative(application, runtime.directory) : null;
  if (relative !== null && !relative.startsWith('..' + path.sep) && relative !== '..' && !path.isAbsolute(relative))
    throw new Error('ARCHCLT_HOME must be outside the application repository');
  if (fs.existsSync(path.join(runtime.directory, ".ready"))) return runtime.executable;
  const python = process.env.ARCHCLT_PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
  run(python, ['-c', 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'], {stdio: ['ignore', 2, 2]});
  fs.mkdirSync(path.dirname(runtime.directory), {recursive: true});
  const staging = fs.mkdtempSync(path.join(path.dirname(runtime.directory), '.setup-'));
  try {
    process.stderr.write('archctl: installing the pinned Python runtime outside the application\n');
    run(python, ['-m', 'venv', staging], {stdio: ['ignore', 2, 2]});
    const interpreter = path.join(staging, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    run(interpreter, ['-m', 'pip', 'install', '--disable-pip-version-check', '--no-input', runtime.wheel,
      `PyYAML==${runtime.manifest.pyyaml}`], {stdio: ['ignore', 2, 2]});
    if (fs.existsSync(runtime.directory)) {
      if (!fs.existsSync(path.join(runtime.directory, '.ready')))
        throw new Error(`Incomplete runtime at ${runtime.directory}; remove it and retry setup`);
      return runtime.executable;
    }
    fs.renameSync(staging, runtime.directory);
    const stablePython = path.join(runtime.directory, process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
    // Recreate entrypoints with the final path, including Windows exe launchers.
    run(stablePython, ['-m', 'pip', 'install', '--disable-pip-version-check', '--no-deps', '--force-reinstall', runtime.wheel],
      {stdio: ['ignore', 2, 2]});
    fs.writeFileSync(path.join(runtime.directory, '.ready'), runtime.manifest.sha256 + '\n');
    return runtime.executable;
  } finally { fs.rmSync(staging, {recursive: true, force: true}); }
}
function main(args) {
  if (args[0] === 'install-skill') {
    if (args.length !== 2) throw new Error('Usage: archctl install-skill <agent-skills-directory>');
    const destination = path.resolve(args[1], 'architecture-control');
    if (fs.existsSync(destination)) throw new Error(`Skill already exists: ${destination}`);
    fs.cpSync(path.join(packageRoot, 'skills/architecture-control'), destination, {recursive: true, errorOnExist: true, force: false});
    process.stdout.write(destination + '\n'); return 0;
  }
  const executable = ensureRuntime();
  if (args[0] === 'setup' || args[0] === '--runtime-path') {
    if (args.length !== 1) throw new Error('Usage: archctl setup | archctl --runtime-path');
    process.stdout.write(executable + '\n'); return 0;
  }
  const interpreter = path.join(path.dirname(executable), process.platform === 'win32' ? 'python.exe' : 'python');
  const result = spawnSync(interpreter, ['-I', '-m', 'archctl', ...args], {stdio: 'inherit'});
  if (result.error) throw result.error;
  return result.signal ? 130 : result.status ?? 3;
}
module.exports = {runtimeLocation, ensureRuntime, main};
if (require.main === module) {
  try { process.exitCode = main(process.argv.slice(2)); }
  catch (error) { process.stderr.write(`archctl: ${error.message}\n`); process.exitCode = 3; }
}
