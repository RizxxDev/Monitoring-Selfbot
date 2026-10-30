# Growcord Multi-Account Worker Engine (Server A)

Modul **Server A** bertugas sebagai mesin operasional 24/7 yang mengelola *pool* multi-akun bot autofarm Discord, mendengarkan perintah remote dari Dashboard Web Vercel via Supabase, dan mengirimkan notifikasi insiden via Discord Webhook.

---

## 🏗️ Arsitektur & Alur Kerja

```
[ Dashboard Web (Vercel) ]
          │  (INSERT PENDING / UPDATE)
          ▼
   [ Supabase Cloud ]
          │  (Polling & Realtime)
          ▼
[ AccountManager (Server A) ]
    ├── Token Decryption (AES-256-GCM)
    ├── BotWorker Pool (Thread per Active Account)
    │     ├── Discord Gateway WSS (Realtime Events)
    │     ├── Anti-AFK Auto Solver & Latency Logger
    │     ├── Auto Re-buff & Auto-Restock Engine
    │     └── Periodic Telemetry Reporter (Metrics & Heartbeat)
    └── Discord Notifier (Webhook Alert Dispatcher)
```

---

## 🚀 Cara Menjalankan Worker

### 1. Pemasangan Dependensi Python

```bash
cd worker
pip install -r requirements.txt
```

### 2. Konfigurasi Lingkungan (`.env.local`)

Worker otomatis membaca file `.env.local` yang ada di root direktori proyek:

```env
# URL & Kunci Supabase
NEXT_PUBLIC_SUPABASE_URL=https://kwogpweprnkpqquasshr.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_supabase_anon_key

# Kunci Enkripsi Token Discord (harus sama dengan yang ada di web)
ENCRYPTION_KEY=growcord_super_secret_aes_key_2026

# (Opsional) URL Webhook Discord untuk Alert Peringatan
DISCORD_ALERT_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

### 3. Menjalankan Engine Multi-Akun

```bash
python worker/account_manager.py
```

Worker akan:
1. Menghubungi database Supabase.
2. Membaca seluruh akun berstatus `ACTIVE`.
3. Mendekripsi token Discord masing-masing akun secara aman (AES-256-GCM).
4. Menjalankan *worker thread* terisolasi untuk tiap akun.
5. Memantau antrean `bot_commands` untuk perintah instan (*START*, *PAUSE*, *FORCE_REBUFF*, *FORCE_RESTOCK*).
6. Mengirim telemetri (gems, sisa stok, status buff) dan heartbeat secara berkala ke tabel `metrics_history`.
