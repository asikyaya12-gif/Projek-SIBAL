"""
Skrip migrasi: tambahkan `user_id` ke semua record yang belum punya.
Jalankan dengan environment sudah ter-set (SUPABASE_URL & SUPABASE_KEY),
contoh:

PS> $env:SUPABASE_URL = 'https://...'
PS> $env:SUPABASE_KEY = '...'
PS> .\.venv\Scripts\python.exe scripts\migrate_add_userid.py --target-user-id <USER_ID>

PERINGATAN: Ini akan menulis ke DB. Backup sebelum menjalankan.
"""
import argparse
import os
from supabase import create_client


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target-user-id', required=True, help='User ID yang akan dipakai sebagai owner untuk record lama')
    args = parser.parse_args()

    url = os.getenv('SUPABASE_URL')
    key = os.getenv('SUPABASE_KEY')
    if not url or not key:
        print('SUPABASE_URL and SUPABASE_KEY must be set in environment')
        return

    client = create_client(url, key)
    tables = ['transaksi_pemasukan', 'transaksi_pengeluaran', 'jurnal_umum', 'jurnal_penyesuaian', 'kartu_persediaan']

    for table in tables:
        print(f'Processing table: {table}')
        res = client.table(table).select('*').execute()
        rows = res.data if res.data else []
        for row in rows:
            if 'user_id' not in row or not row.get('user_id'):
                try:
                    client.table(table).update({'user_id': args.target_user_id}).eq('id', row['id']).execute()
                    print(f"Updated {table} id={row['id']} -> user_id={args.target_user_id}")
                except Exception as e:
                    print(f"Failed to update {table} id={row.get('id')}: {e}")

    print('Migration complete.')


if __name__ == '__main__':
    main()
