const test = require('node:test');
const assert = require('node:assert/strict');
const vm = require('node:vm');
const fs = require('node:fs');
const model = vm.createContext({});
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname, '../Model.js'), 'utf8'), model);

test('invalid or incomplete status never becomes disconnected success', () => {
  for (const raw of ['', '[]', '{}', 'null', '1', '{"ok":true}', '{"ok":true,"connected":false}'])
    assert.equal(model.parseStatus(raw).ok, false, raw);
});
test('accepts explicit valid status and preserves helper errors', () => {
  assert.equal(model.parseStatus('{"ok":true,"loggedIn":true,"connected":true,"country":"de"}').country, 'DE');
  assert.equal(model.parseStatus('{"ok":true,"loggedIn":true,"connected":false}').connected, false);
  assert.equal(model.parseStatus('{"ok":false,"error":"failed"}').error, 'failed');
});
test('malformed country response does not erase the current list', () => {
  for (const raw of ['{}', '[]', '{"ok":true}', '{"ok":true,"countries":{}}'])
    assert.equal(model.parseCountries(raw).ok, false);
  assert.equal(model.parseCountries('{"ok":true,"countries":[]}').ok, true);
});
