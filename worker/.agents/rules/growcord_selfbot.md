# Growcord Selfbot Automation Rules

## 1. Direct Farm Bypass (Prioritaskan Kondisi Siap)
- Ketika membaca status di menu utama (`home`), periksa sisa durasi `Buff Aktif` (Arroz Con Pollo & Eggs Benedict) dan jumlah stok `Farmable Saat Ini`.
- Jika buff aktif dan stok farmable belum 0 (misalnya masih ribuan block):
  - **DILARANG** membuka menu `Toko` maupun `Item`/`Consumables`.
  - Cukup periksa status `Auto Farm:`. Jika `OFF`, langsung klik tombol `Farm` untuk mengubahnya menjadi `ON`.

## 2. Pengecekan Item Non-Purchasable (Lucky Clover)
- Lucky Clover tidak dijual di Toko Consumables Growcord.
- Cek ketersediaan Lucky Clover di inventory hanya satu kali saat startup awal (`clover_checked`).
- Jika tidak ada di inventory, tandai sebagai dilewati dan jangan pernah membuka menu inventory lagi untuk Lucky Clover selama siklus berjalan.

## 3. Quiet Standby Monitoring & Drain Queue
- Setelah persiapan awal selesai atau setelah melakukan aksi interaksi menu, **kuras antrean event Gateway** (`while gw.pop_event(0) is not None: pass`) agar event lama berstatus `OFF` tidak memicu loop restock/persiapan berulang.
- Selama standby, hanya respon 3 kondisi:
  1. **Anti-AFK**: Prompt `are you still there?` dengan tombol `Yes, keep farming` -> klik dengan jeda manusiawi (1.2–2.2 detik).
  2. **Stok Habis**: Stok terbaca `0` block -> buka Toko Farmable -> Pot O' Gems (Buy Max) -> kembali ke Home -> nyalakan Farm.
  3. **Buff Kedaluwarsa**: Arroz Con Pollo atau Eggs Benedict hilang dari daftar `Buff Aktif` -> jalankan re-buff.
  4. **Auto Farm Mati Tidak Terduga**: Jika status berubah `OFF` tapi stok masih ada dan buff aktif -> klik tombol `Farm` di home tanpa membuka menu lain.

## 4. Pola Tombol Komponen Aman
- Tombol aksi `Use` pada layar consumables harus menggunakan regex `r"\b(?:Use|Gunakan)\b"` agar tidak salah mengklik tombol tab `🎒 Habis Pakai`.

## 5. Tombol Navigasi Kembali dari Layar Consumables (Item • Habis Pakai)
- Pada layar `Item • Habis Pakai`, tombol kembali berlabel **`← Item`** (bukan `Kembali`).
- Pola regex tombol kembali consumables harus menggunakan `r"←\s*(?:Items?|Kembali|Back)\b|^\s*(?:Items?|Kembali|Back)\s*$"` agar mencocokkan `← Item` tanpa salah mengklik tombol kategori lain seperti `Select Item`, `Custom Item`, dll.
- Rute kembali ke menu utama `home` dari `consumables` adalah rute bertingkat 2 langkah:
  1. `consumables` &rarr; `items` via tombol `← Item`.
  2. `items` &rarr; `home` via tombol `Kembali`.

## 6. Penanganan Tombol Disabled & Cooldown Interaksi
- Tombol aksi Discord (khususnya tombol `Farm` di `home`) dapat berada dalam status `disabled: true` sementara akibat cooldown internal server Growcord.
- JANGAN langsung melempar exception fatal atau menghentikan bot jika tombol disabled ditemukan.
- Terapkan mekanisme backoff (tunggu 3–5 detik) dan coba ulang hingga 3–5 kali sebelum memutuskan navigasi gagal.

## 7. Integritas Form Modal Discord (Text Input Limits)
- Properti `max_length` pada komponen Text Input Discord API v10 merepresentasikan **panjang maksimum karakter string** (digit count), BUKAN nilai nominal integer.
- Dilarang membatasi nilai angka menggunakan `min(amount, max_length)`. Validasi hanya panjang karakter: `len(str(amount)) <= max_length`.

## 8. Preservasi Jeda Manusiawi (Humanized Delay) Seluruh Modul
- Setiap respons terhadap prompt Anti-AFK (`are you still there?` / `Yes, keep farming`), baik di `core/bot.py` maupun `autofarm.py`, WAJIB menyertakan jeda acak manusiawi 1.2 hingga 2.2 detik sebelum interaksi dikirim.

## 9. Sinkronisasi Sesi Dinamis Gateway & REST API (24/7 Resilience)
- Gateway Discord dapat terputus dan reconnect sewaktu-waktu dengan `session_id` baru saat event `READY`.
- Objek `Api` WAJIB menggunakan session provider dinamis yang mengambil `session_id` terbaru dari Gateway agar submission modal form dan payload interaksi tidak ditolak Discord.
- Opcode 9 (`Invalid Session`) dan READY timeout harus diperlakukan sebagai reconnectable runtime error, BUKAN fatal `AuthError`.

## 10. Arsitektur Supervisor Loop & Graceful Navigation
- Main loop WAJIB dibungkus dalam supervisor loop 24/7 dengan exponential backoff.
- Kegagalan navigasi atau item tidak ditemukan di dropdown consumables TIDAK BOLEH mematikan proses bot; tangani secara aman, tunda konsumsi item, dan pulihkan navigasi ke `home`.
- Hanya `KeyboardInterrupt` (`Ctrl+C`) atau `AuthError` (token tidak valid) yang boleh menghentikan proses.

## 11. Gateway Resume (Opcode 6) & Opcode 7
- Saat koneksi Gateway terputus, kirim Opcode 6 (RESUME) jika `session_id` dan `seq` tersedia.
- Sambungkan ulang secara otomatis saat menerima Opcode 7 (Reconnect request) tanpa memicu socket timeout.

## 12. Zero Gems Guard
- Saat respons toko menolak pembelian karena gems habis/tidak cukup, lemparkan `GemsExhaustedError` dan hentikan proses secara fatal untuk mencegah spamming dan ban akun.

## 13. Safe Drain Queue
- Dilarang menguras antrean event Gateway secara membabi-buta; gunakan `safe_drain_events()` untuk memeriksa apakah ada event Anti-AFK yang tertinggal saat navigasi menu.

## 14. Kontinuitas Lucky Clover
- Lucky Clover terus digunakan jika stok di inventory masih ada. Hanya lewati jika inventory sudah diverifikasi kosong (0 stok).
