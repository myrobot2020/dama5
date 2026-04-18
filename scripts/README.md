## Firebase admin scripts

### Set dev claim for a user

1. Download a service account JSON key from Firebase Console:
   - Project settings → Service accounts → **Generate new private key**
2. Save it as `scripts/serviceAccount.json` (this file is ignored by git).
3. Install dependencies:

```bash
cd scripts
npm i
```

4. Set the claim (replace UID):

```bash
set DAMA_DEV_UID=WHyxoulJUSWhuU2TvFVjJ2H335w1S
node set_firebase_dev_claim.mjs
```

After setting the claim, sign out/in so the Firebase ID token refreshes.

