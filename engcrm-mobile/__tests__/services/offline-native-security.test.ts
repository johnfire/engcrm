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
});
