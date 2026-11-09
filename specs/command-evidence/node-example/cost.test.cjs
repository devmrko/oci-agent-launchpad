const {test} = require('node:test');
const assert = require('node:assert/strict');
const {total} = require('./cost.cjs');
test('positive costs', () => assert.equal(total(2, 3), 5));
test('zero cost', () => assert.equal(total(0, 3), 3));
test('negative costs rejected', () => {
  assert.throws(() => total(-1, 2), RangeError);
  assert.throws(() => total(2, -1), RangeError);
});
