# Donation feature: setup guide for teammates

Online donations use the **PayHere sandbox**. It's free and uses test cards only, so no real money moves and no bank details are needed. Everything else in the app works without this setup. You only need it to test donations.

> **Never** share your keys in WhatsApp, chat, screenshots or commits. Each person uses their **own** PayHere sandbox and ngrok accounts. `backend/.env` is git-ignored, so keep it that way.

---

## 1. PayHere sandbox account (once, about 10 minutes)

1. Sign up at **https://sandbox.payhere.lk**. It's free and needs no bank details.
2. **Merchant ID and Merchant Secret:**
   1. Go to **Integrations > Add Domain/App**.
   2. Enter the domain `localhost` and request it. It is usually approved quickly in sandbox.
   3. Copy the **Merchant ID**, shown at the top of the Integrations page.
   4. Copy the **Merchant Secret** shown next to `localhost`.
3. **App ID and App Secret:**
   1. Go to **Settings > API Keys > Create API Key**.
   2. Enter any name and the domain `localhost`.
   3. Tick the payment retrieval permission, then save.
   4. Press **View Credentials** and copy the **App ID** and **App Secret**.
   - PayHere refuses these from localhost, but the backend still expects them. They're used on a deployed server.

---

## 2. ngrok tunnel (once, about 10 minutes)

PayHere confirms each payment by calling our backend. A backend on `localhost` can't be reached from the internet, so a tunnel gives it a public address.

1. Sign up free at **https://ngrok.com**.
2. Install **ngrok 3.28 or newer**. Older versions are refused on free accounts. The simplest way is to download the Windows zip from https://ngrok.com/download and unzip it to `C:\ngrok`. If you used winget, check the version with `ngrok version`.
3. Save your authtoken (once). Get it from the ngrok dashboard under **Getting Started > Your Authtoken**:
   ```
   C:\ngrok\ngrok.exe config add-authtoken <your-token>
   ```
   Type the token on its own, without a `$` in front. Don't put it in `.env`; ngrok stores it itself.
4. In the ngrok dashboard, open **Domains** and copy your free fixed domain, e.g. `something-something.ngrok-free.dev`.

---

## 3. `backend/.env`

Add these lines, using your own values. Keep the existing lines as they are.

```
PAYHERE_MERCHANT_ID=<from step 1>
PAYHERE_MERCHANT_SECRET=<from step 1>
PAYHERE_APP_ID=<from step 1>
PAYHERE_APP_SECRET=<from step 1>
PUBLIC_API_URL=https://<your-ngrok-domain>
```

- `PUBLIC_API_URL` has no slash at the end.
- `PAYHERE_SANDBOX` defaults to sandbox, so leave it out. Set `PAYHERE_SANDBOX=false` only with a live PayHere merchant account.
- `PUBLIC_APP_URL` (already there, `http://localhost:3000`) is where PayHere sends the donor back to.
- Thank-you emails use the existing `BREVO_API_KEY` / `BREVO_SENDER_EMAIL`. If they aren't set, donations still work, just without emails.

Restart the backend after editing `.env`.

---

## 4. Every time you test or demo donations

Run these three, each in its own terminal:

1. **Backend:** start it the way you normally do, on port 8000.
2. **Frontend:** from `frontend/`, run `npm run dev`.
3. **Tunnel:** from any folder, run:
   ```
   C:\ngrok\ngrok.exe http --domain=<your-ngrok-domain> 8000
   ```

The ngrok window should show `Forwarding https://<your-ngrok-domain> -> http://localhost:8000`.

---

## 5. Test a donation

1. Open **http://localhost:3000/donate**, choose an amount and a purpose, fill in your details (or turn on anonymous), and press **Donate**.
2. On PayHere's page, pay with a **sandbox test card**. Real cards are rejected in sandbox, which is expected. Use any name, any future expiry date and any CVV:
   - Visa `4916217501611292`
   - Mastercard `5307732125531191`
   - Amex `346781005510225`
   - If these change, see "Test card numbers" in PayHere's sandbox docs at support.payhere.lk.
3. After paying:
   - The ngrok window shows `POST /api/donations/payhere/notify 200`.
   - The thank-you page says **"Thank you for your donation!"**.
   - **Finance > Ledger** has a new Income row, "Donation-General" or "Donation-<Program>".
   - **Donations > Donation details** shows it as **Paid** (Admin, Director or Finance Officer login).
   - A named donor receives a thank-you email. Check spam too.

---

## Troubleshooting

| What you see | Cause and fix |
|---|---|
| Donate page says "Online donations are not set up yet" | `PAYHERE_MERCHANT_ID` / `PAYHERE_MERCHANT_SECRET` are missing from `backend/.env`, or the backend wasn't restarted. |
| Paid on PayHere, but stays "Awaiting payment" | The tunnel wasn't running, or `PUBLIC_API_URL` is wrong. Fix it, restart the backend, then make a new test donation. A payment made while the tunnel was off can't be confirmed later, so delete that pending row in Supabase. |
| `ngrok` "is not recognized" | Close VS Code completely and reopen it, or use the full path `C:\ngrok\ngrok.exe`. |
| ngrok "agent version is too old" (ERR_NGROK_121) | Install the latest ngrok from https://ngrok.com/download. |
| ngrok "unknown flag: --url" | Older versions use `--domain=` instead of `--url=`. |
| "Card number invalid" on PayHere | Use the sandbox test cards above. |
| Backend log: "Access denied for the domain" | Expected on localhost. PayHere refuses the Retrieval API from localhost; the tunnel route handles confirmation instead. |
| Check a specific order | From `backend/`: `python scripts/check_payhere_order.py VFF-XXXXXXXXXXXX 2500`. It prints no keys or card details. |
