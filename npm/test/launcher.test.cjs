'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '../..');
const {runtimeLocation} = require('../bin/archctl.cjs');

test('bundled wheel tampering is rejected before execution', t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'archclt-checksum-'));
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}));
  fs.mkdirSync(path.join(directory, 'npm/runtime'), {recursive:true});
  fs.writeFileSync(path.join(directory, 'npm/runtime/runtime.whl'), 'altered');
  fs.writeFileSync(path.join(directory, 'npm/runtime/manifest.json'), JSON.stringify({wheel:'runtime.whl', version:'0.3.0', sha256:crypto.createHash('sha256').update('reviewed').digest('hex')}));
  assert.throws(() => runtimeLocation(directory), /checksum mismatch/);
});

test('install-skill copies complete resources and preserves an existing installation', t => {
  const destination = fs.mkdtempSync(path.join(os.tmpdir(), 'archclt-skill-'));
  t.after(() => fs.rmSync(destination, {recursive:true, force:true}));
  const cli = path.join(root, 'npm/bin/archctl.cjs');
  const invoke = () => spawnSync(process.execPath, [cli, 'install-skill', destination], {encoding:'utf8'});
  const first = invoke(); assert.equal(first.status, 0, first.stderr);
  assert.ok(fs.existsSync(path.join(destination, 'architecture-control/references/change.md')));
  const marker = path.join(destination, 'architecture-control/SKILL.md');
  fs.writeFileSync(marker, 'local changes');
  const second = invoke(); assert.equal(second.status, 3); assert.match(second.stderr, /already exists/);
  assert.equal(fs.readFileSync(marker, 'utf8'), 'local changes');
});
