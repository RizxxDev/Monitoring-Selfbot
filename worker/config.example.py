import os

# ==============================================================
#  KONFIGURASI CONTOH (TEMPLATE)
#  Salin file ini menjadi config.py lalu isi token & channel kamu.
# ==============================================================

# Token akun Discord (cara ambil ada di README.md atau set env DISCORD_TOKEN)
TOKEN = os.getenv("DISCORD_TOKEN") or "ISI_TOKEN_DISCORD_DI_SINI"

# ID channel/thread farm (klik kanan thread -> Copy Channel ID atau set env GROWCORD_CHANNEL)
CHANNEL_ID = os.getenv("GROWCORD_CHANNEL") or "ISI_CHANNEL_ID_DI_SINI"

# (Opsional) ID aplikasi Growcord; otomatis diambil dari pesan bot jika kosong
GROWCORD_APP_ID = ""

# ================== PENGATURAN BELI WL / LOCK ==================
GEM_FLOOR = 2000          # berhenti kalau gems berada < nilai ini
WL_PRICE  = 2000          # harga 1 WL dalam gems
MAX_PER_BUY = 100         # batas jumlah per submit form (form: 1-100)
AUTO_LOCK_GEMS_THRESHOLD = int(os.getenv("AUTO_LOCK_GEMS_THRESHOLD") or 2_100_000_000)  # otomatis Toko -> Lock -> Beli All saat gems >= 2,1 Miliar

# ================== PENGATURAN TIMING ==================
DELAY_NAV   = (2.0, 4.0)   # delay acak antar klik navigasi (detik)
DELAY_BUY   = (3.0, 5.0)   # delay acak antar siklus beli (detik)
MODAL_TIMEOUT   = 8.0      # menunggu form/modal muncul (detik)
REPLY_TIMEOUT   = 15.0     # menunggu balasan bot setelah submit (detik)
NAV_MAX_STEPS   = 15       # batas langkah navigasi sampai tujuan

# ================== FALLBACK MODAL (opsional) ==================
MODAL_CUSTOM_ID = ""
MODAL_FIELD_CUSTOM_ID = ""

# ================== MODE WATCH & AUTOFARM ==================
WATCH_MINUTES    = 30      # jeda antar siklus watch (menit)
WATCH_BUY_GEMS   = 20000   # buy_wl hanya jika gems > nilai ini (0 = selalu)
WATCH_ITERATIONS = 0       # jumlah siklus; 0 = terus sampai Ctrl+C
# ================== PILIHAN FARMABLE TOKO GROWCORD ==================
# Opsi resmi: "Pot O' Gems", "Crystal Block", "Game Grave", "Rich Crystal", "Diamond Ore", "Diamond Block", "Void Crystal Ore"
FARMABLE_ITEMS = [
    "Pot O' Gems",
    "Crystal Block",
    "Game Grave",
    "Rich Crystal",
    "Diamond Ore",
    "Diamond Block",
    "Void Crystal Ore",
]
FARMABLE_ITEM    = "Pot O' Gems"  # item farmable yang dibeli di Toko jika stock kosong
AUTOFARM_CHECK_INTERVAL = 300     # interval cek berkala saat autofarm idle (detik)

# ================== PENDETEKSI GAGAL ==================
ABORT_PATTERNS = [
    "tidak cukup",
    "insufficient",
    "kehabisan",
    "pembelian gagal",
    "terjadi kesalahan",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

LOG_FILE = "runs.log"
