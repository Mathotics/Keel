const fs = require("fs");

function withFirebase(config) {
  if (!fs.existsSync("./google-services.json")) {
    return config;
  }
  config.android = config.android || {};
  config.android.googleServicesFile = "./google-services.json";
  return config;
}

module.exports = withFirebase;
