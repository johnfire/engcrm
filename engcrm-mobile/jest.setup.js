// react-native-safe-area-context's own mock: zero insets unless a test sets
// them on useSafeAreaInsets, and no native provider needed to render a screen.
jest.mock("react-native-safe-area-context", () =>
  require("react-native-safe-area-context/jest/mock").default,
);
