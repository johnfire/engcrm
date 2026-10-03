module.exports = {
  preset: "jest-expo",
  moduleNameMapper: {
    "^expo-secure-store$": "<rootDir>/__mocks__/expo-secure-store.js",
    "^expo-device$": "<rootDir>/__mocks__/expo-device.js",
    "^expo-notifications$": "<rootDir>/__mocks__/expo-notifications.js",
  },
  testMatch: ["**/__tests__/**/*.[jt]s?(x)"],
  // The first test in a screen file pays for transforming the React Native
  // modules it loads: ~2.4 s here with a cold cache vs ~0.25 s warm. CI always
  // starts cold on 4 vCPUs and has pushed that past Jest's 5 s default. A real
  // hang still fails, just at 15 s.
  testTimeout: 15000,
};
