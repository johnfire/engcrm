// Exercise the shell-quote vulnerability without running a shell command.
import * as shellQuote from "shell-quote";

describe("shell-quote command injection regression", () => {
  it.each(["\n", "\r", "\u2028", "\u2029"])(
    "rejects a line terminator after a comment token: %j",
    (terminator) => {
      expect(() => shellQuote.quote(["echo", "ok", { comment: "note" }, `text${terminator}injected`]))
        .toThrow(TypeError);
    },
  );

  it("preserves safe argument quoting used by the build tools", () => {
    const argumentsToQuote = ["echo", "hello world", "single'quote", "$(literal)"];
    expect(shellQuote.parse(shellQuote.quote(argumentsToQuote))).toEqual(argumentsToQuote);
  });
});
