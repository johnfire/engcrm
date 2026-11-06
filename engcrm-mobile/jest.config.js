module.exports = {
  preset: "jest-expo",
  // The fixed URI decoder is ESM; compile it alongside Expo's normal modules.
  transformIgnorePatterns: [
    "/node_modules/(?!(.pnpm|react-native|@react-native|@react-native-community|expo|@expo|@expo-google-fonts|react-navigation|@react-navigation|@sentry/react-native|native-base|standard-navigation|decode-uri-component))",
    "/node_modules/react-native-reanimated/plugin/",
    "/node_modules/@react-native/babel-preset/",
  ],
  moduleNameMapper: {
    "^expo-secure-store$": "<rootDir>/__mocks__/expo-secure-store.js",
    "^expo-device$": "<rootDir>/__mocks__/expo-device.js",
    "^expo-notifications$": "<rootDir>/__mocks__/expo-notifications.js",
    // The package's own in-memory mock; a test that needs to watch the calls
    // still replaces it with jest.mock().
    "^@react-native-async-storage/async-storage$":
      "<rootDir>/node_modules/@react-native-async-storage/async-storage/jest/async-storage-mock.js",
  },
  testMatch: ["**/__tests__/**/*.[jt]s?(x)"],
  // The first test in a screen file pays for transforming the React Native
  // modules it loads: ~2.4 s here with a cold cache vs ~0.25 s warm. CI always
  // starts cold on 4 vCPUs and has pushed that past Jest's 5 s default. A real
  // hang still fails, just at 15 s.
  testTimeout: 15000,
};
