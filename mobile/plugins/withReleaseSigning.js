const { withAppBuildGradle } = require("expo/config-plugins");

const RELEASE_CONFIG = `
        release {
            def storePath = System.getenv("KEEL_ANDROID_KEYSTORE_PATH")
            if (storePath != null) {
                storeFile file(storePath)
                storePassword System.getenv("KEEL_ANDROID_KEYSTORE_PASSWORD")
                keyAlias System.getenv("KEEL_ANDROID_KEY_ALIAS")
                keyPassword System.getenv("KEEL_ANDROID_KEY_PASSWORD")
            }
        }`;

function withReleaseSigning(config) {
  return withAppBuildGradle(config, (mod) => {
    if (mod.modResults.language !== "groovy") {
      throw new Error("Keel release signing expects a Groovy app build.gradle");
    }
    let contents = mod.modResults.contents;
    if (contents.includes("KEEL_ANDROID_KEYSTORE_PATH")) {
      return mod;
    }
    if (!contents.includes("signingConfigs {")) {
      throw new Error("Keel release signing could not find signingConfigs");
    }
    contents = contents.replace(
      "signingConfigs {",
      `signingConfigs {${RELEASE_CONFIG}`,
    );
    const releaseSigning =
      /(\/\/ see https:\/\/reactnative\.dev\/docs\/signed-apk-android\.\r?\n\s*)signingConfig signingConfigs\.debug/;
    if (!releaseSigning.test(contents)) {
      throw new Error("Keel release signing could not find the release signingConfig");
    }
    contents = contents.replace(
      releaseSigning,
      "$1signingConfig signingConfigs.release",
    );
    mod.modResults.contents = contents;
    return mod;
  });
}

module.exports = withReleaseSigning;
