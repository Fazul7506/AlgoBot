const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const source = fs.readFileSync('static/js/core/money_display.js', 'utf8');
const window = {};
const document = {readyState: 'loading', addEventListener() {}};
vm.runInNewContext(source, {window, document});

const money = window.AlgoBotMoney;
assert.equal(money.currency, 'USD');
assert.equal(money.symbol, '$');
assert.equal(money.format(null), '$0.00');
assert.equal(money.format(undefined), '$0.00');
assert.equal(money.format('not-a-number'), '$0.00');
assert.equal(money.format(0), '$0.00');
assert.equal(money.format(1234.5), '$1,234.50');
assert.equal(money.format(-12.3), '$-12.30');
assert.equal(money.format(1234.5, 'USD'), '$1,234.50');
assert.equal(money.format(1234.5, ''), '$1,234.50');
assert.equal(money.format(1234.5, 'KES'), '$1,234.50');
assert.equal(money.format(10, 'EUR'), '$10.00');
assert.equal(money.symbolFor('KES'), '$');
assert.equal(money.numberFor(Infinity), 0);
assert.equal(money.isValid(false), false);

const css = fs.readFileSync('static/css/money_display.css', 'utf8');
assert.match(css, /\.algobot-money-value[\\s\\S]*color:[^;]+!important/);
console.log('USD-only money formatting and zero fallbacks passed.');
