module.exports = {
  setNotificationHandler: jest.fn(),
  getPermissionsAsync: jest.fn().mockResolvedValue({ status: "denied" }),
  requestPermissionsAsync: jest.fn().mockResolvedValue({ status: "denied" }),
  getExpoPushTokenAsync: jest
    .fn()
    .mockResolvedValue({ data: "ExponentPushToken[test]" }),
  setNotificationChannelAsync: jest.fn().mockResolvedValue(undefined),
  AndroidImportance: { MAX: 5 },
};
