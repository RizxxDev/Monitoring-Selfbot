# Growcord Multi-Account Autofarm Monitoring & Control Dashboard

Dashboard web modern berbasis **Next.js 14 (App Router)**, **TypeScript**, dan **Tailwind CSS** untuk memantau, mengontrol, dan menganalisis performa multi-akun bot autofarm Discord secara terpusat.

---

## 🚀 Fitur Unggulan

1. **Master Password Auth Guard & Security**:
   - Dilindungi halaman login dengan input password teks bebas.
   - Proteksi brute-force (kunci otomatis 3 menit setelah 5 kali gagal).
   - Sesi terenkripsi *HTTP-Only Cookie* (aktif selama 24 jam).
   - Default password: `admin123` (dapat dikonfigurasi melalui `.env.local`).

2. **Overview Grid & Multi-Account Card**:
   - Pemantauan multi-akun secara simultan dengan badge status interaktif (*RUNNING, PAUSED, ERROR*).
   - Indikator hitung mundur (*countdown real-time*) untuk 3 Buff Utama:
     - 🍀 **Lucky Clover** (Max 1 jam)
     - 🍗 **Arroz Con Pollo** (Max 2 jam)
     - 🍳 **Eggs Benedict** (Max 30 menit)
   - Indikator saldo gems terkini dan sisa stok farmable di tas bot.
   - Pengecekan *Last Heartbeat* dan latensi *Gateway Ping WSS*.

3. **Remote Lifecycle & Quick Control**:
   - **Start / Pause**: Mengubah status bot secara instan.
   - **Force Re-buff**: Mengisi penuh durasi buff (Clover, Arroz, Benedict) secara jarak jauh.
   - **Force Restock**: Membeli stok item di toko in-game otomatis.
   - **Aksi Massal**: Tombol *Start All* dan *Pause All*.

4. **Navigasi Hybrid (Drawer & Halaman Khusus)**:
   - **Slide-over Drawer**: Buka rincian cepat dan edit konfigurasi langsung dari dashboard utama tanpa berpindah halaman.
   - **Halaman Penuh (`/accounts/[id]`)**:
     - Grafik time-series interaktif pertumbuhan gems 24 jam / 7 hari (Recharts).
     - Perhitungan laju perolehan gems per jam (*Gems/Hour rate*).
     - Tabel *Audit Event Log* lengkap dengan filter kategori (`ANTI_AFK`, `BUFF`, `SHOP`, `ERROR`) dan tracking latensi klik anti-AFK.

5. **Arsitektur Dual-Mode (Active Demo Simulator & Supabase Cloud)**:
   - **Active Demo Simulation**: Langsung berjalan otomatis tanpa database eksternal. Jam countdown buff berjalan mundur, gems bertambah, dan log anti-AFK ter-generate secara realistis.
   - **Supabase Cloud**: Cukup isi `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_ANON_KEY` pada file `.env.local`.

---

## 🛠️ Panduan Menjalankan

### 1. Menjalankan Server Pengembangan (Dev Mode)

```bash
npm run dev
```

Buka peramban di: [http://localhost:3000](http://localhost:3000)

* Password login default: `admin123`

### 2. Membangun untuk Production (Build & Start)

```bash
npm run build
npm run start
```

---

## ⚙️ Variabel Lingkungan (`.env.local`)

```env
# Master Password untuk Login Dashboard
MASTER_PASSWORD=admin123

# Kunci Enkripsi Sesi (HMAC-SHA256)
AUTH_SECRET=monitoring_super_secret_jwt_key_2026

# Supabase Cloud (Kosongkan jika ingin menggunakan Active Demo Mode)
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
```

---

## 🗄️ Skema Database Supabase (Untuk Fase Server A)

File migrasi DDL PostgreSQL siap pakai tersedia di:
`supabase/migrations/01_init_schema.sql`

Tabel yang disediakan:
1. `accounts`: Menyimpan konfigurasi akun bot, channel ID, gem floor, status, dan heartbeat.
2. `bot_commands`: Antrean perintah remote (START, PAUSE, FORCE_REBUFF, FORCE_RESTOCK).
3. `metrics_history`: Log telemetri berkala untuk visualisasi grafik.
4. `event_logs`: Catatan kejadian anti-AFK, pemakaian buff, transaksi toko, dan insiden kritis.

---

## 📂 Struktur Direktori Proyek

```
d:\Project\Monitoring\
├── src/
│   ├── app/
│   │   ├── accounts/[id]/page.tsx   # Halaman Analisis & Grafik Penuh
│   │   ├── api/
│   │   │   ├── auth/                # API Login, Logout & Check Session
│   │   │   └── commands/            # API Eksekusi Remote Command
│   │   ├── login/page.tsx           # Gerbang Keamanan Master Password
│   │   ├── globals.css              # Dark Gamer Theme Styling
│   │   ├── layout.tsx               # Root App Layout
│   │   └── page.tsx                 # Dashboard Utama (Overview Grid)
│   ├── components/
│   │   ├── charts/                  # Recharts Area Gems Time-Series
│   │   └── dashboard/               # Cards, Buff Indicators, Drawer, Modal, Toast
│   ├── lib/
│   │   ├── auth.ts                  # Logika Brute-Force & Session Token
│   │   ├── constants.ts             # Item Farmable & Konfigurasi Buff
│   │   ├── mock-data.ts             # Data Simulasi Awal
│   │   ├── simulation-store.ts      # Active Real-time Simulator Engine
│   │   ├── supabase.ts              # Adapter Supabase Client
│   │   └── types.ts                 # TypeScript Schema & Interface
│   └── middleware.ts                # Route Guard Proteksi Sesi Cookie
├── supabase/
│   └── migrations/
│       └── 01_init_schema.sql       # Skema DDL Database Sesuai PRD
├── package.json
└── README.md
```
