import { formatAmount, formatEur, typedAmount } from "../../services/money";

describe("money — as the web's eur filter shows and takes it", () => {
  it("groups thousands with dots, uses a comma for cents, drops cents on a whole amount", () => {
    expect(formatEur("2400.50")).toBe("2.400,50 €");
    expect(formatEur("2400.00")).toBe("2.400 €");
    expect(formatEur(49)).toBe("49 €");
    expect(formatAmount("1234567.5")).toBe("1.234.567,50");
    expect(formatAmount(null)).toBe("0");
  });

  it("takes a typed amount with a comma or a dot, and only above 0", () => {
    expect(typedAmount(" 2400 ")).toBe("2400");
    expect(typedAmount("2400,5")).toBe("2400.5");
    expect(typedAmount("2400.50")).toBe("2400.50");
    expect(typedAmount("0")).toBeNull();
    expect(typedAmount("-5")).toBeNull();
    expect(typedAmount("12,345")).toBeNull(); // three decimals: not an amount
    expect(typedAmount("abc")).toBeNull();
    expect(typedAmount("")).toBeNull();
  });
});
