# 🌸 MOSI ANIME: How to put your website online

This takes about **10 minutes** and is **free**. You need a **GitHub** account (to store the code) and a **Render** account (to run the website).

---

## Step 1: Put the code on GitHub

1. Go to **https://github.com/signup** and create a free account (skip this if you have one).
2. Click the **+** (top right) → **New repository**.
3. Name it `mosi-anime`, keep it **Public**, and click **Create repository**.
4. On the next page click **"uploading an existing file"**.
5. Unzip `mosi-anime-deploy.zip` on your computer, open the `mosi-anime` folder,
   select **everything inside it** (including the `img` folder) and drag it into the GitHub page.
6. Click **Commit changes** and wait for the upload to finish.

> ⚠️ Drag the *contents* of the folder, not the folder itself. `server.py` must be at the top level of the repo.

## Step 2: Launch it on Render (free)

1. Go to **https://render.com** → **Get Started** → sign up with **GitHub** (easiest).
2. In the dashboard click **New + → Blueprint**.
3. Choose your `mosi-anime` repository and click **Connect**.
4. Render reads `render.yaml` automatically. When it asks for **YT_API_KEY**, paste your YouTube key
   (or leave it empty and add it later).
5. Click **Apply** / **Deploy**. After 1–3 minutes you get a link like
   **`https://mosi-anime.onrender.com`** 🎉

## Step 3: Open your admin panel

1. In Render, open the **mosi-anime** service → **Environment**.
2. Copy the value of **MOSI_ADMIN_KEY**. This is your secret admin password, created randomly for you.
3. Go to **`https://YOUR-SITE.onrender.com/admin.html`** and paste it to log in.

## Step 4: Turn on auto-play of free official episodes

1. Get a free **YouTube Data API v3** key (the admin panel has a step-by-step guide).
2. Best: in Render → **Environment** → add/edit **YT_API_KEY** → paste the key → **Save** (the site restarts).
   You can also paste it in the admin panel, but on the free plan that copy is lost when the server restarts.

## Step 5: Set your UPI ID for donations

Open `src.html` on GitHub → click the ✏️ pencil → find this line near the top of the script:

```js
upiId: "mosianime@upi",      // ← CHANGE THIS
```

Replace it with your real UPI ID (e.g. `yourname@okaxis`) → **Commit changes**. Render redeploys automatically.

---

## ⚠️ Important: the Render free plan

| Thing | Free plan behaviour |
|---|---|
| Sleeping | The site sleeps after 15 min without visitors, and the first visit then takes ~50 seconds to wake up. |
| Saved data | Requests, donation notes, donated videos and admin-panel settings are **wiped when the server restarts or redeploys**. |
| Fix | Add a **Render Disk** (Starter plan, ~$7/month): mount it at `/var/data`, then set env `DATA_DIR=/var/data/data` and `UPLOADS_DIR=/var/data/uploads`. |

Your **YouTube key** and **admin key** are safe because they're stored as environment variables, not in the data folder.

**Other hosts:** the included `Dockerfile` works on Railway (add a Volume at `/app/data`), Koyeb, Fly.io,
Google Cloud Run or any VPS. The `Procfile` works on Heroku-style hosts.

## Run it on your own computer

```bash
python3 server.py
# open http://localhost:8080        (admin: http://localhost:8080/admin.html, key: mosi-admin)
```

Only Python 3.9+ is needed; there's nothing to install.

## Files

| File | What it is |
|---|---|
| `server.py` | The server: website, auto-play episode finder, requests, donations, uploads |
| `src.html` | The website (edit this one) |
| `admin.html` | Admin panel |
| `index.html` | Offline single-file copy (rebuild with `python3 build.py` after editing `src.html`) |
| `img/` | Poster images |
| `render.yaml`, `Dockerfile`, `Procfile` | Hosting settings |
