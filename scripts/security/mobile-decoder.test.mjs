import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { test } from "node:test";

const requireMobile = createRequire(new URL("../../engcrm-mobile/package.json", import.meta.url));
const queryStringPath = requireMobile.resolve("query-string");

test("navigation preserves unicode, spaces, arrays and escaped path characters", () => {
  const queryString = requireMobile("query-string");
  const parameters = { search: "München + /", tag: ["one", "two"] };
  assert.deepEqual({ ...queryString.parse(queryString.stringify(parameters)) }, parameters);
  assert.equal(queryString.parse("search=hello+world").search, "hello world");
  assert.equal(queryString.parse("path=%2Fpeople%2F42").path, "/people/42");
});

test("malformed deep-link queries finish within a bounded child process", () => {
  // GHSA-qr28-fpjm-wq7f: many distinct percent runs followed by malformed input.
  const reproduction = `
    const queryString = require(${JSON.stringify(queryStringPath)});
    let encoded = '';
    for (let index = 0; index < 32000; index++) {
      const high = Math.floor(index / 256).toString(16).padStart(2, '0');
      const low = (index % 256).toString(16).padStart(2, '0');
      encoded += '%' + high + '%' + low + 'x';
    }
    const parsed = queryString.parse('search=' + encoded + '%zz');
    if (!parsed.search.endsWith('%zz')) process.exit(2);
  `;
  execFileSync(process.execPath, ["-e", reproduction], { timeout: 5000, stdio: "pipe" });
});
