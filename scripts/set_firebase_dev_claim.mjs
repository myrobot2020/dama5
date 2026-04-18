import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import admin from "firebase-admin";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function die(msg) {
  console.error(msg);
  process.exit(1);
}

const uid = (process.env.DAMA_DEV_UID || "").trim();
if (!uid) {
  die("Missing DAMA_DEV_UID env var (Firebase UID).");
}

// Usage:
// 1) Download service account JSON and save next to this script as serviceAccount.json
// 2) DAMA_DEV_UID="<uid>" node scripts/set_firebase_dev_claim.mjs
const svcPath = path.join(__dirname, "serviceAccount.json");
if (!fs.existsSync(svcPath)) {
  die(
    "Missing scripts/serviceAccount.json. Download from Firebase Console → Project settings → Service accounts → Generate new private key."
  );
}

const serviceAccount = JSON.parse(fs.readFileSync(svcPath, "utf8"));

admin.initializeApp({
  credential: admin.credential.cert(serviceAccount),
});

await admin.auth().setCustomUserClaims(uid, { dev: true });
console.log("OK: set dev=true for uid:", uid);

