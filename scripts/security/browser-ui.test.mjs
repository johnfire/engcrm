import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";

function formHarness(confirmed) {
  const listeners = {};
  class Form {
    dataset = { confirm: "Delete O'Reilly's record?" };
    button = { disabled: false };
    hasAttribute(name) { return name === "data-disable-submit"; }
    querySelector() { return this.button; }
  }
  const window = { confirm: () => confirmed };
  vm.runInNewContext(readFileSync(new URL("../../gcrm/ui/static/form-behavior.js", import.meta.url), "utf8"), {
    window, HTMLFormElement: Form, document: { addEventListener: (name, callback) => { listeners[name] = callback; } },
  });
  return { listeners, Form, window };
}

test("cancelled native confirmations preserve the form and do not disable its button", () => {
  const { listeners, Form } = formHarness(false);
  const form = new Form();
  let prevented = false;
  listeners.submit({ target: form, preventDefault: () => { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(form.button.disabled, false);
});

test("confirmed submissions retain repeat-submit protection", () => {
  const { listeners, Form } = formHarness(true);
  const form = new Form();
  listeners.submit({ target: form, preventDefault: () => assert.fail("confirmed form was blocked") });
  assert.equal(form.button.disabled, true);
});

test("dropdown changes submit through the native validation and keep-place paths", () => {
  const { listeners, window } = formHarness(true);
  let submitted = 0;
  const form = { requestSubmit: () => { submitted++; } };
  const select = { dataset: {}, form };
  const event = { target: { closest: () => select } };
  listeners.change(event);
  assert.equal(submitted, 1);
  select.dataset.keepPlace = "true";
  window.keepPlaceSubmit = (submittedForm) => { assert.equal(submittedForm, form); submitted++; };
  listeners.change(event);
  assert.equal(submitted, 2);
});

test("map popup labels are text, and its button uses an event listener", () => {
  const window = {};
  const createElement = (tag) => ({ tag, children: [], textContent: "", listeners: {},
    append(...children) { this.children.push(...children); },
    addEventListener(name, callback) { this.listeners[name] = callback; },
    set innerHTML(_content) { assert.fail("untrusted map content was interpreted as HTML"); },
  });
  vm.runInNewContext(readFileSync(new URL("../../gcrm/ui/static/area-popup.js", import.meta.url), "utf8"), {
    window, document: { createElement },
  });
  const label = '<img src=x onerror="alert(1)">';
  let viewed = null;
  const popup = window.buildAreaPopup({ id: 42, radius_m: 500 }, label, "View results",
    (id, selectedLabel) => { viewed = [id, selectedLabel]; });
  assert.equal(popup.children[0].textContent, label);
  const button = popup.children.find((child) => child.tag === "button");
  button.listeners.click();
  assert.deepEqual(viewed, [42, label]);
});
