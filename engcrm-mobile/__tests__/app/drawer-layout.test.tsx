import { AppState } from "react-native";
import { render, fireEvent } from "@testing-library/react-native";

let mockDrawerContent: ((props: any) => any) | undefined;
jest.mock("expo-router/drawer", () => {
  const Drawer: any = ({ drawerContent }: any) => {
    mockDrawerContent = drawerContent;
    return null;
  };
  Drawer.Screen = () => null;
  return {
    Drawer,
    DrawerContentScrollView: ({ children }: any) => children,
    DrawerItemList: () => null,
  };
});
jest.mock("expo-router", () => ({ useRouter: () => ({}) }));
jest.mock("../../services/auth", () => ({ clearToken: jest.fn() }));

import DrawerLayout from "../../app/(drawer)/_layout";

describe("drawer menu", () => {
  it("always offers a Close menu button that closes the drawer", () => {
    render(<DrawerLayout />);
    expect(mockDrawerContent).toBeDefined();
    const closeDrawer = jest.fn();
    const { getByLabelText } = render(mockDrawerContent!({ navigation: { closeDrawer } }));
    fireEvent.press(getByLabelText("✕ Close menu"));
    expect(closeDrawer).toHaveBeenCalledTimes(1);
  });

  it("closes the drawer when the app returns to the foreground", () => {
    let onChange: (state: string) => void = () => undefined;
    const remove = jest.fn();
    jest.spyOn(AppState, "addEventListener").mockImplementation(((_: string, cb: (state: string) => void) => {
      onChange = cb;
      return { remove };
    }) as never);
    render(<DrawerLayout />);
    const closeDrawer = jest.fn();
    const view = render(mockDrawerContent!({ navigation: { closeDrawer } }));
    onChange("background");
    expect(closeDrawer).not.toHaveBeenCalled();
    onChange("active");
    expect(closeDrawer).toHaveBeenCalledTimes(1);
    view.unmount();
    expect(remove).toHaveBeenCalled();
  });
});
