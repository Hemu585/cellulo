# Google sign-in setup

About 10 minutes, once. You create a small private "app" in your own Google account so the tool can sign in as you. It costs nothing.

At the end you will have one file: `C:\Users\<you>\.cellulo\credentials.json`.

## 1. Create a project

1. Open <https://console.cloud.google.com/> and sign in with the Google account that should own the spreadsheets.
2. Click the project picker at the top → **New project**.
3. Name it `cellulo` → **Create**. Make sure it is selected in the project picker afterwards.

## 2. Turn on the Sheets API

1. Menu → **APIs & Services** → **Library**.
2. Search for **Google Sheets API** → open it → **Enable**.

## 3. Set up the consent screen

1. Menu → **Google Auth Platform** (or open <https://console.cloud.google.com/auth/overview>) → **Get started**.
2. **App information:** app name `Cellulo`, support email = your address.
3. **Audience:** choose **External**.
4. **Contact information:** your email. Agree to the policy → **Create**.
5. Open **Audience** in the left menu → **Test users** → **Add users** → type your own Gmail address, press Enter → **Save**.
6. Check that your address now appears in the Test users list. If the panel is still open, click **Save** again; the first click can be swallowed.

Without a saved test user, sign-in fails with `Error 403: access_denied`.

## 4. Create the sign-in client

1. Left menu → **Clients** → **Create client**.
2. Application type: **Desktop app**. Name: `cellulo-desktop`. → **Create**.
3. In the dialog that appears, click **Download JSON** straight away. Google may not show the secret again later; if you miss it, create another client.

## 5. Put the file in place

Create the folder:

```powershell
New-Item -ItemType Directory -Force "$HOME\.cellulo"
```

Move the newest download there and rename it (this picks the latest one if you have several `client_secret` files):

```powershell
Get-ChildItem "$HOME\Downloads\client_secret_*.json" | Sort-Object LastWriteTime | Select-Object -Last 1 | Move-Item -Destination "$HOME\.cellulo\credentials.json"
```

## 6. First run

```powershell
python cellulo.py upload sample.mp4
```

1. Your browser opens. Pick your account.
2. "Google hasn't verified this app" appears. That is expected for your own test app: click **Continue**.
3. Allow the access it asks for: "See, edit, create and delete only the specific Google Drive files that you use with this app".
4. The browser says the flow is complete. The tool saves `token.json` next to `credentials.json` and carries on.

## What the tool can and cannot reach

- It asks for one permission, `drive.file`. It can only open spreadsheets **it created**. It cannot see your other Sheets, Docs or Drive files.
- So it cannot write to a spreadsheet you made by hand. Let `upload` create one.

## Keeping it safe

- `credentials.json` and `token.json` are keys to that permission. Do not share, email or commit them. They sit outside the project folder on purpose.
- To cut off access: <https://myaccount.google.com/connections> → `Cellulo` → remove. Then delete `token.json`.

## Signing in again

While the app is in **Testing** status, Google expires the sign-in after 7 days. The tool notices and opens the browser again. Nothing is lost.
