# Projek-SIBAL
Sistem Informasi Berbasis Akuntansi Ikan Bawal

## Setup singkat & environment variables

1. Salin file `.env.example` ke `.env` atau set environment variables di sistem Anda.

2. Environment penting yang harus di-set sebelum menjalankan aplikasi:

	- `GOOGLE_CLIENT_ID` dan `GOOGLE_CLIENT_SECRET` — gunakan Google Cloud Console untuk membuat OAuth client.
	- `GOOGLE_REDIRECT_URI` — biasanya `http://localhost:8051/auth/callback` saat development.
	- `SECRET_KEY` — random string untuk Flask session.
	- `SUPABASE_URL` dan `SUPABASE_KEY` — untuk koneksi Supabase (jika Anda gunakan Supabase).

3. Jalankan aplikasi (PowerShell):

```powershell
python -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# set env (sesi terminal)
$env:GOOGLE_CLIENT_ID = 'PASTE_CLIENT_ID'
$env:GOOGLE_CLIENT_SECRET = 'PASTE_CLIENT_SECRET'
python sibal.py
```

## Rotasi / revoke Google client secret

Jika secret sempat terkomit, segera revoke/rotate client secret di Google Cloud Console:
1. Buka https://console.cloud.google.com/apis/credentials
2. Pilih OAuth 2.0 Client IDs lalu revoke/regen secret.
3. Update environment variable `GOOGLE_CLIENT_SECRET` dengan nilai baru.

## Migrasi data lama (opsional)

Jika Anda sudah punya data yang tersimpan di Supabase tanpa `user_id`, gunakan skrip `scripts/migrate_add_userid.py` untuk memberi `user_id` default. Hati-hati: lakukan backup terlebih dahulu.
