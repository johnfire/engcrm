module.exports = {
  preset: "jest-expo",
  moduleNameMapper: {
    "^expo-secure-store$": "<rootDir>/__mocks__/expo-secure-store.js",
    "^expo-device$": "<rootDir>/__mocks__/expo-device.js",
    "^expo-notifications$": "<rootDir>/__mocks__/expo-notifications.js",
  },
  testMatch: ["**/__tests__/**/*.[jt]s?(x)"],
};
