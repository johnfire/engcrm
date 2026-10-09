# Handoff: engcrm mobile drawer stuck-open bug

Date: 2026-10-09 · Repo: `johnfire/engcrm` · Area: `engcrm-mobile/`

## 1. Problem

The mobile app's menu (drawer) opens, then gets stuck open. It cannot be closed and the app becomes unusable. Request: the menu must always be closable.

## 2. Status

| Item | State |
|---|---|
| Close-menu button | Done, merged to `main` |
| Root cause of the stuck drawer | **Not found** |
| Verified on a real phone | **No** (Chris is testing) |

## 3. What was shipped

- **Commit:** `fc76c3a` "Add an always-visible Close menu button to the mobile drawer". `main` fast-forwarded `586201a..fc76c3a`, no PR.
- **Deploy:** merging to `main` triggers Chris's CI/CD pipeline, which ships to Google Play. No manual EAS build is needed. The pipeline's result was not checked from the cloud session.
- **Change:** `engcrm-mobile/app/(drawer)/_layout.tsx` now passes a custom `drawerContent` to `<Drawer>`. `CustomDrawerContent` renders a "✕ Close menu" button (`navigation.closeDrawer()`) pinned above a `DrawerContentScrollView` holding `DrawerItemList`. The button is outside the scroll area, so it is always visible.
- **i18n:** new key `drawer.closeMenu` in `i18n/en.json` ("✕ Close menu") and `i18n/de.json` ("✕ Menü schließen"). Keys are flat dotted strings.
- **Test:** `__tests__/app/drawer-layout.test.tsx` mocks `expo-router/drawer`, renders the drawer content, presses the button, and asserts `closeDrawer` is called once.
- **Checks run:** `tsc --noEmit` clean, eslint clean, jest 296/296 passing.

## 4. Gotchas

- Import `Drawer`, `DrawerContentScrollView`, `DrawerItemList` and the `DrawerContentComponentProps` type from **`expo-router/drawer`**, not `@react-navigation/drawer`. Under Expo Router 56 the two type sets are incompatible (tsc error TS2322 on `navigation`).
- `engcrm-mobile/AGENTS.md` says to read the Expo SDK 56 docs (https://docs.expo.dev/versions/v56.0.0/) before writing code.
- Stack: Expo ~56, React Native 0.85.3, React 19.2.3, expo-router ~56.2.8, react-native-reanimated 4.3.1, react-native-gesture-handler ~2.31.1, react-native-screens 4.25.2.

## 5. Open question: why does the drawer get stuck?

Unknown. Hypotheses, none confirmed:

1. Gesture-handler or Reanimated fault leaves the drawer overlay or animation in a bad state.
2. A navigation or screen change while the drawer is open (many hidden detail screens live inside the drawer navigator, with `backBehavior="history"`).
3. Overlay tap or swipe handlers not registering after a camera/scan/voice flow returns.

Tests Chris should run on the phone:

- Does the new "✕ Close menu" button close the drawer?
- **Is the button still responsive when the drawer is stuck?** If it is dead too, the whole UI thread or touch layer is frozen and the bug is below the drawer (hypothesis 1 or 3).
- What screen or action came right before the stuck state?
- Does the Android back button close it?

Next steps depend on the answers:

- Button works while stuck: the fix is sufficient as a safety net, and the underlying cause is low priority.
- Button is dead too: investigate Reanimated/gesture-handler versions and `GestureHandlerRootView` setup in the root layout, and check device logs (`adb logcat`) at the moment of the freeze.

## 6. Resume locally

```bash
git clone https://github.com/johnfire/engcrm.git   # or: git pull
cd engcrm && git checkout main && git pull
cd engcrm-mobile
npm ci
npx tsc --noEmit
npx eslint "app/(drawer)/_layout.tsx"
npx jest
```

The cloud session's working branch `claude/wonderful-meitner-3uw6vp` is identical to `main` at `fc76c3a` and can be deleted.

## 7. Other items seen in passing (not touched)

- Open Brain notes unmerged work on branch `ccr-be53bb57-gazg77` (list paging, filters, Reachable fits screen) from the 2026-10-03 handoff.
- Dependabot reports 80 vulnerabilities (4 critical) on `engcrm` main (Open Brain note, 2026-10-07).
- Open question from 2026-10-07: whether the marketing pipeline graphic should keep showing the Follow-up agent (disabled per `AGENTS.md`).

## 8. Open Brain

Session captured under project `engcrm` (2026-10-09), including the open actions above.
