import { readFileSync } from "fs";
import { join } from "path";

const root = join(__dirname, "../..");
const readProjectFile = (path: string) => readFileSync(join(root, path), "utf8");

describe("encrypted offline database native configuration", () => {
  it("enables SQLCipher in both Expo config and the checked-in Android build", () => {
    const config = JSON.parse(readProjectFile("app.json"));
    expect(config.expo.plugins).toContainEqual(["expo-sqlite", { useSQLCipher: true }]);
    expect(readProjectFile("android/gradle.properties")).toMatch(/^expo\.sqlite\.useSQLCipher=true$/m);
  });

  it("excludes the encrypted database and its SecureStore key from backup and transfer", () => {
    const manifest = readProjectFile("android/app/src/main/AndroidManifest.xml");
    expect(manifest).toContain('android:fullBackupContent="@xml/offline_backup_rules"');
    expect(manifest).toContain('android:dataExtractionRules="@xml/offline_data_extraction_rules"');
    for (const file of ["offline_backup_rules.xml", "offline_data_extraction_rules.xml"]) {
      const rules = readProjectFile(`android/app/src/main/res/xml/${file}`);
      expect(rules).toContain('domain="file" path="SQLite/"');
      expect(rules).toContain('domain="sharedpref" path="SecureStore"');
    }
  });

  it("also keeps the plain app storage and queued capture photos out of backup and transfer", () => {
    for (const file of ["offline_backup_rules.xml", "offline_data_extraction_rules.xml"]) {
      const rules = readProjectFile(`android/app/src/main/res/xml/${file}`);
      for (const name of ["RKStorage", "RKStorage-journal", "RKStorage-wal", "RKStorage-shm"]) {
        expect(rules).toContain(`domain="database" path="${name}"`);
      }
      expect(rules).toContain('domain="file" path="card-queue/"');
    }
  });

  it("does not ship the draw-over-other-apps permission in the release manifest", () => {
    expect(readProjectFile("android/app/src/main/AndroidManifest.xml")).not.toContain("SYSTEM_ALERT_WINDOW");
    expect(readProjectFile("android/app/src/debug/AndroidManifest.xml")).toContain("SYSTEM_ALERT_WINDOW");
    const config = JSON.parse(readProjectFile("app.json"));
    expect(config.expo.android.blockedPermissions).toContain("android.permission.SYSTEM_ALERT_WINDOW");
  });
});
