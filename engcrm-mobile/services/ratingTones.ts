// The colours of the private ratings, the same as the web's. Which tone each rating gets
// is the server's (priority_tone / value_tone in gcrm/api/templates.py) and the colours
// are its stylesheet's (.tone-* in gcrm/ui/static/style.css);
// tests/test_mobile_rating_tones.py fails if they drift apart. One entry per line so
// that test can read this file.

export type Tone = "green" | "yellow" | "blue" | "orange" | "gray" | "dark";

/** Priority (organizations) and my rating (people): 1 is the best. */
export const PRIORITY_TONE: Record<number, Tone> = {
  1: "green",
  2: "yellow",
  3: "blue",
  4: "orange",
  5: "gray",
  6: "dark",
};

/** Short- and long-term value: 3 high .. 0 zero. */
export const VALUE_TONE: Record<number, Tone> = {
  3: "green",
  2: "yellow",
  1: "blue",
  0: "gray",
};

/** fill: a picked choice's background; line: every choice's border; text: on the fill. */
export const TONE_COLOURS: Record<Tone, { fill: string; line: string; text: string }> = {
  green: { fill: "#5fae78", line: "#5fae78", text: "#0c0b09" },
  yellow: { fill: "#e3c443", line: "#e3c443", text: "#0c0b09" },
  blue: { fill: "#5b8fd9", line: "#5b8fd9", text: "#0c0b09" },
  orange: { fill: "#e0883a", line: "#e0883a", text: "#0c0b09" },
  gray: { fill: "#8d877a", line: "#8d877a", text: "#0c0b09" },
  dark: { fill: "#3a3834", line: "#77736a", text: "#ffffff" },
};
