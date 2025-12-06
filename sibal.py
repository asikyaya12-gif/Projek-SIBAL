from dash import Dash, html, dcc, callback, Input, Output, State
import dash
import pandas as pd
from datetime import datetime, timedelta
import json
import random
from supabase import create_client, Client
import os
import glob

# Try to load environment variables from a .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("🔒 Loaded environment from .env (if present)")
except Exception:
    # dotenv not installed or no .env file; continue
    pass


def _load_google_credentials_from_local_file():
    """Attempt to read local client_secret JSON files often downloaded from Google Console.

    Looks for files named `client_secret*.json` or `client_secret.json` and extracts
    client_id and client_secret if present. Returns tuple (client_id, client_secret).
    """
    files = glob.glob('client_secret*.json') + glob.glob('client_secret.json')
    for path in files:
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
                # file may contain 'installed' or 'web'
                for key in ('installed', 'web'):
                    if key in payload:
                        info = payload[key]
                        cid = info.get('client_id')
                        secret = info.get('client_secret')
                        if cid and secret:
                            print(f"🔐 Loaded Google credentials from {path} (local file)")
                            return cid, secret
                # fallback try top-level keys
                if 'client_id' in payload and 'client_secret' in payload:
                    return payload['client_id'], payload['client_secret']
        except Exception:
            continue
    return None, None
from flask import Flask, redirect, url_for, session
from supabase import create_client, Client
import os

# ===== INISIALISASI URUTAN YANG BENAR =====

# 1. Inisialisasi app dulu
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "SIBAL - Sistem Informasi Bimbingan Akuntansi Lanjutan"

# 2. Setup server
server = app.server

# 3. Setup SECRET_KEY
import secrets
SECRET_KEY = os.getenv('SECRET_KEY', 'sibal-secure-' + secrets.token_hex(32))
server.config['SECRET_KEY'] = SECRET_KEY
# Ensure session cookie settings are explicit for local development
# Use Lax so top-level navigations (OAuth redirects) will include the cookie
server.config['SESSION_COOKIE_SAMESITE'] = os.getenv('SESSION_COOKIE_SAMESITE', 'Lax')
# For local development over HTTP, do not force Secure; in production set to True
server.config['SESSION_COOKIE_SECURE'] = False
server.config['SESSION_COOKIE_HTTPONLY'] = True
from datetime import timedelta as _td
server.config['PERMANENT_SESSION_LIFETIME'] = _td(days=7)

# 4. Setup Supabase client
supabase_url = "https://shltrwcweexbdcuogscs.supabase.co"
supabase_key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNobHRyd2N3ZWV4YmRjdW9nc2NzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQwNjk4MjUsImV4cCI6MjA3OTY0NTgyNX0.tVwzjiqORJ0dAZhW_f0PneVqJyummvmPOi-WFC5Wd1I"
supabase_client = create_client(supabase_url, supabase_key)

# ===== SIMPLE AUTH SYSTEM =====
import requests
import secrets
import hashlib
import random

class SimpleUser:
    def __init__(self, user_data=None):
        if user_data:
            self.id = user_data.get('id', '')
            self.email = user_data.get('email', '')
            self.name = user_data.get('name', '')
            self.username = user_data.get('username', '')
            self.is_authenticated = True
        else:
            self.id = ''
            self.email = ''
            self.name = ''
            self.username = ''
            self.is_authenticated = False
    
    def get_id(self):
        return str(self.id)

# Global current_user
current_user = SimpleUser()

# Simple user storage
users_db = {}

# Google OAuth config
# Gunakan environment variables agar tidak menyimpan secrets di repo
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET', None)
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8051/auth/callback')

# ===== SIMPLE AUTH FUNCTIONS =====
def login_user(user, remember=False):
    """Gantikan fungsi login_user dari Flask-Login"""
    global current_user
    current_user = SimpleUser(user)
    session['user_id'] = user['id']
    session['user_email'] = user['email']
    # Set active user in data layer so data dipisah per akun
    try:
        sibal_data.set_active_user(user.get('id'))
    except Exception:
        pass
    # make the session permanent so it survives short redirects
    try:
        session.permanent = True
    except Exception:
        pass
    print(f"✅ User logged in: {user['email']}")

def authenticate_user(identifier, password):
    """Gantikan auth_system.authenticate_user"""
    user = None
    # Cari user by email atau username
    for user_id, user_data in users_db.items():
        if user_data['email'] == identifier or user_data['username'] == identifier:
            user = user_data
            break
    
    if not user:
        return None, "User tidak ditemukan"
    
    # Verify password
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if user.get('password_hash') != password_hash:
        return None, "Password salah"
    
    return user, "Login berhasil"

# Update authentication functions untuk menggunakan tabel users yang baru
def create_user(username, email, password):
    """Create user dan simpan ke Supabase"""
    try:
        # Cek apakah email sudah terdaftar di tabel users
        existing_users = sibal_data._get_table_data('users')
        existing_email = any(user['email'] == email for user in existing_users)
        existing_username = any(user['username'] == username for user in existing_users)
        
        if existing_email:
            return None, "Email sudah terdaftar"
        if existing_username:
            return None, "Username sudah digunakan"
        
        # Create new user di Supabase
        user_data = {
            'email': email,
            'username': username,
            'name': username,
            'auth_provider': 'local'
        }
        
        saved_user = sibal_data._insert_table_data('users', user_data)
        if saved_user:
            user_data['id'] = saved_user['id']
            # Initialize per-user data from template (non-blocking)
            try:
                ok = sibal_data.initialize_user_from_template(user_data['id'])
                if not ok:
                    print(f"⚠️ Warning: failed to initialize template data for user {user_data['id']}")
            except Exception as e:
                print(f"⚠️ Exception during initializing template data: {e}")

            return user_data, "User created successfully"
        else:
            return None, "Gagal membuat user"
            
    except Exception as e:
        print(f"Error creating user: {e}")
        return None, "Error sistem"

def authenticate_user(identifier, password):
    """Authenticate user dari Supabase"""
    try:
        # Untuk sekarang, kita skip password verification 
        # karena tabel users tidak ada password_hash
        users_data = sibal_data._get_table_data('users')
        
        user_data = None
        for user in users_data:
            if user['email'] == identifier or user['username'] == identifier:
                user_data = user
                break
        
        if not user_data:
            return None, "User tidak ditemukan"
        
        # Untuk development, bypass password check
        # Karena tabel users tidak memiliki password_hash
        return user_data, "Login berhasil (development mode)"
        
    except Exception as e:
        print(f"Error authenticating user: {e}")
        return None, "Error sistem"
    
# Simple user storage - HANYA SIMPAN DI MEMORY
users_db = {}

# Google OAuth config (didefinisikan sebelumnya menggunakan environment variables)


# ========== BEAUTIFUL COLOR PALETTE ==========
COLORS = {
    'primary': '#473573',
    'primary_light': '#5A4A8A',
    'primary_dark': '#3A2B5C',
    'secondary': '#53619E',
    'secondary_light': '#6A77B0',
    'secondary_dark': '#454D80',
    'accent_teal': '#88BAC3',
    'accent_teal_light': '#9DC8D0',
    'accent_mint': '#D6F3EE',
    'accent_mint_light': '#E6F7F4',
    'accent_lavender': '#A78BFA',
    'accent_coral': '#FF6B6B',
    'white': '#FFFFFF',
    'gray_50': '#F8FAFC',
    'gray_100': '#F1F5F9',
    'gray_200': '#E2E8F0',
    'gray_300': '#CBD5E1',
    'gray_400': '#94A3B8',
    'gray_500': '#64748B',
    'gray_600': '#475569',
    'gray_700': '#334155',
    'gray_800': '#1E293B',
    'gray_900': '#0F172A',
    'success': '#10B981',
    'success_light': '#34D399',
    'warning': '#F59E0B',
    'warning_light': '#FBBF24',
    'error': '#EF4444',
    'error_light': '#F87171',
    'info': '#3B82F6',
    'info_light': '#60A5FA'
}

# ========== SISTEM KODE AKUN ==========
KODE_AKUN = {
    'kas': {'kode': '1-110', 'nama': 'Kas'},
    'persediaan': {'kode': '1-120', 'nama': 'Persediaan Barang Dagang'},
    'perlengkapan': {'kode': '1-130', 'nama': 'Perlengkapan'},
    'peralatan': {'kode': '1-210', 'nama': 'Peralatan'},
    'tanah': {'kode': '1-220', 'nama': 'Tanah'},
    'bangunan_gazebo': {'kode': '1-230', 'nama': 'Bangunan'},
    'akumulasi_penyusutan_bangunan': {'kode': '1-231', 'nama': 'Akumulasi Depresiasi Bangunan'},
    'kendaraan': {'kode': '1-240', 'nama': 'Kendaraan'},
    'akumulasi_penyusutan_kendaraan': {'kode': '1-241', 'nama': 'Akumulasi Depresiasi Kendaraan'},
    'akumulasi_penyusutan_peralatan': {'kode': '1-242', 'nama': 'Akumulasi Depresiasi Peralatan'},
    'utang': {'kode': '2-110', 'nama': 'Utang Dagang'},
    'utang_gaji': {'kode': '2-120', 'nama': 'Utang Gaji'},
    'modal': {'kode': '3-110', 'nama': 'Modal'},
    'pendapatan': {'kode': '4-110', 'nama': 'Penjualan'},
    'pendapatan_tiket': {'kode': '4-120', 'nama': 'Pendapatan Tiket'},
    'hpp': {'kode': '5-110', 'nama': 'Harga Pokok Produksi'},
    'beban_gaji': {'kode': '6-110', 'nama': 'Beban Gaji'},
    'beban_listrik': {'kode': '6-115', 'nama': 'Beban Listrik'},
    'beban_penyusutan_bangunan': {'kode': '6-120', 'nama': 'Beban Depresiasi Bangunan'},
    'beban_penyusutan_kendaraan': {'kode': '6-121', 'nama': 'Beban Depresiasi Kendaraan'},
    'beban_penyusutan_peralatan': {'kode': '6-122', 'nama': 'Beban Depresiasi Peralatan'},
    'beban_lainnya': {'kode': '6-130', 'nama': 'Beban Lainnya'}
}

def login_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.H1("🔐 Login ke SIBAL", style={
                    'textAlign': 'center', 
                    'color': COLORS['primary'],
                    'marginBottom': '10px'
                }),
                html.P("Sistem Informasi Bimbingan Akuntansi Lanjutan", 
                      style={'textAlign': 'center', 'color': COLORS['gray_600'], 'marginBottom': '40px'}),
                
                # TOMBOL GOOGLE
                html.Div([
                    html.A(
                        html.Button(
                            [
                                html.Img(
                                    src="https://developers.google.com/identity/images/g-logo.png",
                                    style={
                                        'width': '20px', 
                                        'height': '20px', 
                                        'marginRight': '12px',
                                        'verticalAlign': 'middle'
                                    }
                                ),
                                "Login dengan Google"
                            ],
                            style={
                                'width': '100%',
                                'padding': '15px 20px',
                                'fontSize': '16px',
                                'fontWeight': '500',
                                'backgroundColor': '#4285F4',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '8px',
                                'cursor': 'pointer',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center',
                                'transition': 'all 0.3s ease'
                            },
                            id='btn-google-login'  # ← ID UNTUK CALLBACK
                        ),
                        href="/auth/login",
                        style={'textDecoration': 'none'}
                    )
                ], style={'marginBottom': '30px'}),
                
                html.Div([
                    html.Hr(style={'margin': '20px 0'}),
                    html.P("Atau login dengan akun yang sudah dibuat", style={
                        'textAlign': 'center', 
                        'color': COLORS['gray_500'],
                        'marginBottom': '20px'
                    })
                ]),
                
                # FORM LOGIN MANUAL
                html.Div([
                    html.Label("Username atau Email", className="form-label"),
                    dcc.Input(
                        id='login-identifier',
                        type='text',
                        placeholder='Username atau email Anda...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Password", className="form-label"),
                    dcc.Input(
                        id='login-password', 
                        type='password',
                        placeholder='Password Anda...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                # TOMBOL LOGIN MANUAL
                html.Button(
                    "🚀 Login",
                    id='btn-login',  # ← ID UNTUK CALLBACK
                    className="btn btn-primary",
                    style={'width': '100%', 'marginBottom': '15px'}
                ),
                
                html.Div(id='login-alert'),
                
                html.Hr(style={'margin': '30px 0'}),
                
                html.Div([
                    html.P("Belum punya akun? ", style={'display': 'inline'}),
                    dcc.Link(
                        "Daftar di sini", 
                        href="/signup",
                        style={
                            'color': COLORS['primary'], 
                            'fontWeight': 'bold',
                            'textDecoration': 'none'
                        }
                    )
                ], style={'textAlign': 'center'})
                
            ], style={'padding': '50px'})
        ], style={
            'maxWidth': '450px',
            'margin': '80px auto',
            'backgroundColor': 'white',
            'borderRadius': '12px',
            'boxShadow': '0 10px 25px rgba(0,0,0,0.1)',
            'border': '1px solid #e0e0e0'
        })
    ], style={
        'backgroundColor': COLORS['gray_50'],
        'minHeight': '100vh',
        'padding': '20px',
        'fontFamily': 'Arial, sans-serif'
    })

def signup_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.H1("🚀 Daftar SIBAL", style={
                    'textAlign': 'center', 
                    'color': COLORS['primary'],
                    'marginBottom': '10px'
                }),
                html.P("Bergabung dengan sistem akuntansi kami", 
                      style={'textAlign': 'center', 'color': COLORS['gray_600'], 'marginBottom': '40px'}),
                
                # TOMBOL GOOGLE SIGNUP
                html.Div([
                    html.A(
                        html.Button(
                            [
                                html.Img(
                                    src="https://developers.google.com/identity/images/g-logo.png",
                                    style={
                                        'width': '20px', 
                                        'height': '20px', 
                                        'marginRight': '12px',
                                        'verticalAlign': 'middle'
                                    }
                                ),
                                "Daftar dengan Google"
                            ],
                            style={
                                'width': '100%',
                                'padding': '15px 20px',
                                'fontSize': '16px',
                                'fontWeight': '500',
                                'backgroundColor': '#34A853',
                                'color': 'white',
                                'border': 'none',
                                'borderRadius': '8px',
                                'cursor': 'pointer',
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'center'
                            },
                            id='btn-google-signup'  # ← ID UNTUK CALLBACK
                        ),
                        href="/auth/login",
                        style={'textDecoration': 'none'}
                    )
                ], style={'marginBottom': '30px'}),
                
                html.Div([
                    html.Hr(style={'margin': '20px 0'}),
                    html.P("Atau daftar dengan email", style={
                        'textAlign': 'center', 
                        'color': COLORS['gray_500'],
                        'marginBottom': '20px'
                    })
                ]),
                
                # FORM SIGNUP MANUAL
                html.Div([
                    html.Label("Username", className="form-label"),
                    dcc.Input(
                        id='signup-username',
                        type='text',
                        placeholder='Pilih username...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Email", className="form-label"),
                    dcc.Input(
                        id='signup-email',
                        type='email',
                        placeholder='Email Anda...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Password", className="form-label"),
                    dcc.Input(
                        id='signup-password',
                        type='password',
                        placeholder='Password minimal 6 karakter...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Konfirmasi Password", className="form-label"),
                    dcc.Input(
                        id='signup-confirm-password',
                        type='password',
                        placeholder='Ulangi password...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                # TOMBOL SIGNUP MANUAL
                html.Button(
                    "✅ Daftar dengan Email", 
                    id='btn-signup',  # ← ID UNTUK CALLBACK
                    className="btn btn-success",
                    style={'width': '100%', 'marginBottom': '15px'}
                ),
                
                html.Div(id='signup-alert'),
                
                html.Hr(style={'margin': '30px 0'}),
                
                html.Div([
                    html.P("Sudah punya akun? ", style={'display': 'inline'}),
                    dcc.Link(
                        "Login di sini", 
                        href="/login",
                        style={
                            'color': COLORS['primary'], 
                            'fontWeight': 'bold',
                            'textDecoration': 'none'
                        }
                    )
                ], style={'textAlign': 'center'})
                
            ], style={'padding': '50px'})
        ], style={
            'maxWidth': '450px',
            'margin': '80px auto',
            'backgroundColor': 'white',
            'borderRadius': '12px',
            'boxShadow': '0 10px 25px rgba(0,0,0,0.1)',
            'border': '1px solid #e0e0e0'
        })
    ], style={
        'backgroundColor': COLORS['gray_50'],
        'minHeight': '100vh',
        'padding': '20px',
        'fontFamily': 'Arial, sans-serif'
    })

def complete_profile_layout():
    """Halaman untuk buat username dan password setelah Google OAuth"""
    oauth_user = session.get('oauth_user')
    
    if not oauth_user:
        return html.Div([
            html.Div([
                html.H3("❌ Session Expired", style={'textAlign': 'center', 'color': COLORS['error']}),
                html.P("Silakan login kembali.", style={'textAlign': 'center'}),
                dcc.Link(
                    "Kembali ke Login", 
                    href="/login",
                    style={'display': 'block', 'textAlign': 'center', 'marginTop': '20px'}
                )
            ], style={'padding': '50px'})
        ], style={
            'maxWidth': '500px',
            'margin': '100px auto',
            'backgroundColor': 'white',
            'borderRadius': '12px',
            'boxShadow': '0 10px 25px rgba(0,0,0,0.1)'
        })
    
    return html.Div([
        html.Div([
            html.Div([
                html.H1("🎉 Selamat Datang!", style={'textAlign': 'center', 'color': COLORS['primary']}),
                html.P(f"Halo {oauth_user['name']}!", 
                      style={'textAlign': 'center', 'color': COLORS['gray_600'], 'fontSize': '1.1rem'}),
                html.P("Lengkapi profil Anda untuk mulai menggunakan SIBAL", 
                      style={'textAlign': 'center', 'color': COLORS['gray_500']}),
                
                html.Hr(style={'margin': '20px 0'}),
                
                html.Div([
                    html.Label("Username", className="form-label"),
                    dcc.Input(
                        id='complete-username',
                        type='text',
                        placeholder='Pilih username...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Password", className="form-label"),
                    dcc.Input(
                        id='complete-password',
                        type='password',
                        placeholder='Buat password minimal 6 karakter...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Div([
                    html.Label("Konfirmasi Password", className="form-label"),
                    dcc.Input(
                        id='complete-confirm-password',
                        type='password',
                        placeholder='Ulangi password...',
                        className="form-input"
                    )
                ], className="form-group"),
                
                html.Button(
                    "✅ Simpan Profil & Masuk",
                    id='btn-complete-profile',
                    className="btn btn-primary",
                    style={'width': '100%', 'marginTop': '20px', 'padding': '15px'}
                ),
                
                html.Div(id='complete-profile-alert', style={'marginTop': '20px'})
                
            ], style={'padding': '40px'})
        ], style={
            'maxWidth': '500px',
            'margin': '50px auto',
            'backgroundColor': 'white',
            'borderRadius': '12px',
            'boxShadow': '0 10px 25px rgba(0,0,0,0.1)',
            'border': '1px solid #e0e0e0'
        })
    ], style={
        'backgroundColor': COLORS['gray_50'],
        'minHeight': '100vh',
        'padding': '20px'
    })

def protected_layout():
    """Layout yang membutuhkan login"""
    if current_user.is_authenticated:
        return dashboard_layout()
    else:
        return login_layout()
    
def aset_tetap_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-building")
                ], className="card-icon"),
                html.H1("Manajemen Aset Tetap", className="card-title")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.H3("Input Aset Tetap", className="form-section-title"),
                    
                    html.Div([
                        html.Label("Jenis Aset", className="form-label"),
                        dcc.Dropdown(
                            id='jenis-aset',
                            options=[
                                {'label': 'Tanah', 'value': 'tanah'},
                                {'label': 'Bangunan Gazebo', 'value': 'bangunan_gazebo'},
                                {'label': 'Kendaraan', 'value': 'kendaraan'},
                                {'label': 'Peralatan', 'value': 'peralatan'}
                            ],
                            placeholder='Pilih Jenis Aset',
                            className="form-control"
                        )
                    ], className="form-group"),
                    
                    html.Div([
                        html.Label("Nilai Perolehan (Rp)", className="form-label"),
                        dcc.Input(
                            id='nilai-aset',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),
                    
                    html.Div([
                        html.Label("Tanggal Perolehan", className="form-label"),
                        dcc.DatePickerSingle(
                            id='tanggal-perolehan',
                            date=datetime.now().date(),
                            display_format='YYYY-MM-DD',
                            className="form-control"
                        )
                    ], className="form-group"),
                    
                    html.Div([
                        html.Label("Masa Manfaat (Tahun)", className="form-label"),
                        dcc.Input(
                            id='masa-manfaat',
                            type='number',
                            placeholder='0',
                            min=1,
                            className="form-input"
                        )
                    ], className="form-group"),
                    
                    html.Div([
                        html.Label("Metode Penyusutan", className="form-label"),
                        dcc.Dropdown(
                            id='metode-penyusutan',
                            options=[
                                {'label': 'Garis Lurus', 'value': 'garis_lurus'},
                                {'label': 'Saldo Menurun', 'value': 'saldo_menurun'}
                            ],
                            value='garis_lurus',
                            className="form-control"
                        )
                    ], className="form-group"),
                    
                    html.Div([
                        html.Label("Nilai Residu (Rp) - Optional", className="form-label"),
                        dcc.Input(
                            id='nilai-residu',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),
                    
                    html.Button(
                        "💾 Simpan Aset Tetap",
                        id='btn-simpan-aset',
                        className="btn btn-primary"
                    )
                ], className="form-container compact-form"),
                
                html.Div([
                    html.H3("Daftar Aset Tetap", className="form-section-title"),
                    html.Div(id='daftar-aset-tetap', className="table-container"),
                    html.Hr(),
                    html.Button(
                        "📊 Hitung Penyusutan",
                        id='btn-hitung-penyusutan',
                        className="btn btn-success"
                    )
                ], className="data-container"),
            ], className="form-row"),
        ], className="glass-card"),
        
        html.Div([
            html.H3("Kalkulator Penyusutan", className="card-title"),
            html.Div(id='kalkulator-penyusutan', className="table-container")
        ], className="glass-card"),
    ], className="main-container")

app.index_string = f'''
<!DOCTYPE html>
<html>
    <head>
        {{%metas%}}
        <title>{{%title%}}</title>
        {{%favicon%}}
        {{%css%}}
        <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Plus Jakarta Sans', sans-serif;
                background: linear-gradient(135deg, {COLORS['accent_mint']} 0%, {COLORS['white']} 50%, {COLORS['gray_50']} 100%);
                background-attachment: fixed;
                color: {COLORS['gray_800']};
                line-height: 1.6;
                min-height: 100vh;
            }}
            
            .glass-nav {{
                background: rgba(255, 255, 255, 0.85);
                backdrop-filter: blur(20px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.2);
                box-shadow: 0 8px 32px rgba(71, 53, 115, 0.1);
                position: sticky;
                top: 0;
                z-index: 1000;
            }}
            
            .nav-container {{
                max-width: 1400px;
                margin: 0 auto;
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: 1rem 2rem;
            }}
            
            .nav-brand {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            
            .brand-logo {{
                width: 45px;
                height: 45px;
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                border-radius: 12px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: {COLORS['white']};
                font-size: 1.3rem;
                box-shadow: 0 4px 12px rgba(71, 53, 115, 0.3);
            }}
            
            .brand-text {{
                font-size: 1.5rem;
                font-weight: 800;
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                letter-spacing: -0.5px;
            }}
            
            .nav-links {{
                display: flex;
                gap: 4px;
                background: rgba(255, 255, 255, 0.6);
                padding: 4px;
                border-radius: 16px;
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.3);
            }}
            
            .nav-link {{
                padding: 12px 24px;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 0.95rem;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                color: {COLORS['gray_600']};
                display: flex;
                align-items: center;
                gap: 8px;
                position: relative;
                overflow: hidden;
            }}
            
            .nav-link::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(71, 53, 115, 0.1), transparent);
                transition: left 0.6s ease;
            }}
            
            .nav-link:hover::before {{
                left: 100%;
            }}
            
            .nav-link:hover {{
                color: {COLORS['primary']};
                transform: translateY(-1px);
            }}
            
            .nav-link.active {{
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                color: {COLORS['white']};
                box-shadow: 0 4px 12px rgba(71, 53, 115, 0.3);
            }}
            
            .sub-nav {{
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(20px);
                border-bottom: 1px solid rgba(255, 255, 255, 0.3);
                box-shadow: 0 4px 20px rgba(71, 53, 115, 0.08);
            }}
            
            .sub-nav-container {{
                max-width: 1400px;
                margin: 0 auto;
                display: flex;
                gap: 8px;
                padding: 1.5rem 2rem;
                overflow-x: auto;
            }}
            
            .sub-nav-link {{
                padding: 12px 20px;
                text-decoration: none;
                border-radius: 12px;
                font-weight: 600;
                font-size: 0.9rem;
                transition: all 0.3s ease;
                color: {COLORS['gray_600']};
                background: rgba(255, 255, 255, 0.8);
                border: 1.5px solid {COLORS['gray_200']};
                white-space: nowrap;
                display: flex;
                align-items: center;
                gap: 8px;
                position: relative;
                overflow: hidden;
            }}
            
            .sub-nav-link::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(136, 186, 195, 0.1), transparent);
                transition: left 0.6s ease;
            }}
            
            .sub-nav-link:hover::before {{
                left: 100%;
            }}
            
            .sub-nav-link:hover {{
                border-color: {COLORS['accent_teal']};
                color: {COLORS['accent_teal']};
                transform: translateY(-2px);
                box-shadow: 0 6px 20px rgba(136, 186, 195, 0.2);
            }}
            
            .main-container {{
                max-width: 1400px;
                margin: 0 auto;
                padding: 2rem;
                min-height: calc(100vh - 120px);
            }}
            
            .glass-card {{
                background: rgba(255, 255, 255, 0.8);
                backdrop-filter: blur(20px);
                border-radius: 24px;
                padding: 2.5rem;
                border: 1px solid rgba(255, 255, 255, 0.3);
                box-shadow: 
                    0 8px 32px rgba(71, 53, 115, 0.1),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
                margin-bottom: 2rem;
                transition: all 0.3s ease;
                position: relative;
                overflow: hidden;
            }}
            
            .glass-card::before {{
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 1px;
                background: linear-gradient(90deg, transparent, rgba(71, 53, 115, 0.2), transparent);
            }}
            
            .glass-card:hover {{
                transform: translateY(-4px);
                box-shadow: 
                    0 20px 40px rgba(71, 53, 115, 0.15),
                    inset 0 1px 0 rgba(255, 255, 255, 0.6);
            }}
            
            .card-header {{
                display: flex;
                align-items: center;
                gap: 16px;
                margin-bottom: 2rem;
                padding-bottom: 1.5rem;
                border-bottom: 1px solid rgba(71, 53, 115, 0.1);
            }}
            
            .card-icon {{
                width: 60px;
                height: 60px;
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                border-radius: 16px;
                display: flex;
                align-items: center;
                justify-content: center;
                color: {COLORS['white']};
                font-size: 1.5rem;
                box-shadow: 0 6px 20px rgba(71, 53, 115, 0.3);
            }}
            
            .card-title {{
                font-size: 2rem;
                font-weight: 800;
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                line-height: 1.2;
            }}
            
            .card-subtitle {{
                color: {COLORS['gray_500']};
                font-size: 1.1rem;
                font-weight: 500;
                margin-top: 0.5rem;
            }}
            
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }}
            
            .stat-card {{
                background: linear-gradient(135deg, {COLORS['secondary']}, {COLORS['primary']});
                color: {COLORS['white']};
                border-radius: 20px;
                padding: 2rem;
                position: relative;
                overflow: hidden;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                box-shadow: 0 8px 32px rgba(71, 53, 115, 0.3);
            }}
            
            .stat-card::before {{
                content: '';
                position: absolute;
                top: -50%;
                right: -50%;
                width: 200%;
                height: 200%;
                background: linear-gradient(45deg, transparent, rgba(255, 255, 255, 0.1), transparent);
                transform: rotate(45deg);
                transition: all 0.6s ease;
            }}
            
            .stat-card:hover {{
                transform: translateY(-8px) scale(1.02);
                box-shadow: 0 20px 40px rgba(71, 53, 115, 0.4);
            }}
            
            .stat-card:hover::before {{
                animation: shine 1.5s ease;
            }}
            
            @keyframes shine {{
                0% {{ transform: rotate(45deg) translateX(-100%); }}
                100% {{ transform: rotate(45deg) translateX(100%); }}
            }}
            
            .stat-value {{
                font-size: 2.5rem;
                font-weight: 800;
                margin-bottom: 0.5rem;
                text-shadow: 0 2px 4px rgba(0, 0, 0, 0.2);
            }}
            
            .stat-label {{
                font-size: 0.95rem;
                opacity: 0.9;
                font-weight: 600;
            }}
            
            .stat-icon {{
                position: absolute;
                top: 1.5rem;
                right: 1.5rem;
                opacity: 0.3;
                font-size: 3rem;
            }}
            
            .btn {{
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
                padding: 14px 28px;
                border: none;
                border-radius: 14px;
                font-weight: 700;
                font-size: 0.95rem;
                text-decoration: none;
                cursor: pointer;
                transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
                position: relative;
                overflow: hidden;
                backdrop-filter: blur(10px);
            }}
            
            .btn::before {{
                content: '';
                position: absolute;
                top: 0;
                left: -100%;
                width: 100%;
                height: 100%;
                background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.3), transparent);
                transition: left 0.6s ease;
            }}
            
            .btn:hover::before {{
                left: 100%;
            }}
            
            .btn-primary {{
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                color: {COLORS['white']};
                box-shadow: 0 6px 20px rgba(71, 53, 115, 0.3);
            }}
            
            .btn-primary:hover {{
                transform: translateY(-3px) scale(1.05);
                box-shadow: 0 12px 30px rgba(71, 53, 115, 0.4);
            }}
            
            .btn-success {{
                background: linear-gradient(135deg, {COLORS['success']}, {COLORS['success_light']});
                color: {COLORS['white']};
                box-shadow: 0 6px 20px rgba(16, 185, 129, 0.3);
            }}
            
            .btn-success:hover {{
                transform: translateY(-3px) scale(1.05);
                box-shadow: 0 12px 30px rgba(16, 185, 129, 0.4);
            }}
            
            .btn-danger {{
                background: linear-gradient(135deg, {COLORS['error']}, {COLORS['error_light']});
                color: {COLORS['white']};
                box-shadow: 0 6px 20px rgba(239, 68, 68, 0.3);
            }}
            
            .btn-danger:hover {{
                transform: translateY(-3px) scale(1.05);
                box-shadow: 0 12px 30px rgba(239, 68, 68, 0.4);
            }}
            
            .form-container {{
                background: rgba(255, 255, 255, 0.6);
                backdrop-filter: blur(10px);
                border-radius: 20px;
                padding: 2rem;
                border: 1px solid rgba(255, 255, 255, 0.4);
                max-width: 500px;
                margin: 0 auto;
            }}
            
            .form-section-title {{
                font-size: 1.3rem;
                font-weight: 700;
                color: {COLORS['primary']};
                margin-bottom: 1.5rem;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid {COLORS['accent_teal_light']};
            }}
            
            .form-group {{
                margin-bottom: 1.5rem;
            }}
            
            .form-label {{
                display: block;
                margin-bottom: 0.5rem;
                font-weight: 600;
                color: {COLORS['gray_700']};
                font-size: 0.95rem;
            }}
            
            .form-input {{
                width: 100%;
                padding: 14px 16px;
                border: 2px solid {COLORS['gray_200']};
                border-radius: 12px;
                font-size: 1rem;
                transition: all 0.3s ease;
                background: rgba(255, 255, 255, 0.8);
                font-family: 'Plus Jakarta Sans', sans-serif;
            }}
            
            .form-input:focus {{
                outline: none;
                border-color: {COLORS['accent_teal']};
                box-shadow: 0 0 0 3px rgba(136, 186, 195, 0.1);
                background: rgba(255, 255, 255, 0.95);
            }}
            
            .form-control {{
                width: 100%;
                padding: 12px 16px;
                border: 2px solid {COLORS['gray_200']};
                border-radius: 12px;
                font-size: 1rem;
                transition: all 0.3s ease;
                background: rgba(255, 255, 255, 0.8);
                font-family: 'Plus Jakarta Sans', sans-serif;
            }}
            
            .table-container {{
                background: rgba(255, 255, 255, 0.7);
                backdrop-filter: blur(10px);
                border-radius: 16px;
                overflow: hidden;
                border: 1px solid rgba(255, 255, 255, 0.4);
                box-shadow: 0 4px 20px rgba(71, 53, 115, 0.08);
                overflow-x: auto;
            }}
            
            .modern-table {{
                width: 100%;
                border-collapse: collapse;
                background: transparent;
                font-size: 0.9rem;
            }}
            
            .modern-table th {{
                background: linear-gradient(135deg, {COLORS['accent_teal']}, {COLORS['accent_teal_light']});
                color: {COLORS['white']};
                padding: 1.2rem 1rem;
                text-align: left;
                font-weight: 700;
                font-size: 0.9rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            
            .modern-table td {{
                padding: 1.2rem 1rem;
                border-bottom: 1px solid rgba(71, 53, 115, 0.1);
                font-size: 0.95rem;
                background: rgba(255, 255, 255, 0.5);
            }}
            
            .modern-table tr:last-child td {{
                border-bottom: none;
            }}
            
            .modern-table tr:hover td {{
                background: rgba(136, 186, 195, 0.1);
            }}
            
            .jurnal-entry {{
                border-bottom: 1px solid #eee;
                padding: 10px 0;
            }}
            
            .jurnal-debit {{
                padding-left: 20px;
            }}
            
            .jurnal-kredit {{
                padding-left: 40px;
                color: {COLORS['secondary']};
            }}
            
            .compact-form {{
                max-width: 400px;
                margin: 0 auto;
            }}
            
            @media (max-width: 768px) {{
                .nav-container {{
                    flex-direction: column;
                    gap: 1rem;
                    padding: 1rem;
                }}
                
                .nav-links {{
                    width: 100%;
                    justify-content: center;
                }}
                
                .main-container {{
                    padding: 1rem;
                }}
                
                .glass-card {{
                    padding: 1.5rem;
                }}
                
                .stats-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .compact-form {{
                    max-width: 100%;
                }}
            }}
            
            ::-webkit-scrollbar {{
                width: 8px;
            }}
            
            ::-webkit-scrollbar-track {{
                background: rgba(71, 53, 115, 0.1);
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb {{
                background: linear-gradient(135deg, {COLORS['primary']}, {COLORS['secondary']});
                border-radius: 4px;
            }}
            
            ::-webkit-scrollbar-thumb:hover {{
                background: linear-gradient(135deg, {COLORS['primary_dark']}, {COLORS['secondary_dark']});
            }}
        </style>
    </head>
    <body>
        {{%app_entry%}}
        <footer>
            {{%config%}}
            {{%scripts%}}
            {{%renderer%}}
        </footer>
    </body>
</html>
'''

class SIBALData:
    def __init__(self):
        # Setup Supabase client
        self.url = "https://shltrwcweexbdcuogscs.supabase.co"
        self.key = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InNobHRyd2N3ZWV4YmRjdW9nc2NzIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQwNjk4MjUsImV4cCI6MjA3OTY0NTgyNX0.tVwzjiqORJ0dAZhW_f0PneVqJyummvmPOi-WFC5Wd1I"
        
        try:
            self.client: Client = create_client(self.url, self.key)
            print("✅ Supabase client connected successfully")
        except Exception as e:
            print(f"❌ Supabase client initialization failed: {e}")
            self.client = None
        
        # Inisialisasi struktur data
        self.init_data_structures()
        
        # Load data dari Supabase
        self.load_all_data()
    
    def init_data_structures(self):
        """Initialize semua struktur data"""
        # Data transaksi (semua pengguna)
        self._all_transaksi_pemasukan = []
        self._all_transaksi_pengeluaran = []
        self._all_jurnal_umum = []
        self._all_jurnal_penyesuaian = []
        self._all_kartu_persediaan = []
        # Active user id (digunakan untuk memfilter data per-akun)
        self.active_user_id = None
        
        # Data master (untuk sementara di memory)
        self.master_persediaan = [
            {'kode': 'IK001', 'nama': 'Ikan Bawal Segar', 'satuan': 'kg', 'harga_beli': 25000, 'harga_jual': 35000}
        ]
        self.suppliers = []
        # Per-user storage untuk suppliers dan buku_besar_pembantu
        self._all_suppliers = {}
        self._all_buku_besar_pembantu = {}
        
        # Data aset tetap
        self.aset_tetap = {
            'tanah': {'nilai_awal': 0, 'penyusutan': 0, 'masa_manfaat': 0, 'tahun_pembelian': datetime.now().year},
            'bangunan_gazebo': {'nilai_awal': 0, 'penyusutan': 0, 'masa_manfaat': 10, 'tahun_pembelian': datetime.now().year},
            'kendaraan': {'nilai_awal': 0, 'penyusutan': 0, 'masa_manfaat': 5, 'tahun_pembelian': datetime.now().year},
            'peralatan': {'nilai_awal': 0, 'penyusutan': 0, 'masa_manfaat': 3, 'tahun_pembelian': datetime.now().year}
        }
        
        # Daftar akun untuk dropdown dengan kode
        self.daftar_akun = [
            {'label': f"{KODE_AKUN['kas']['kode']} - {KODE_AKUN['kas']['nama']}", 'value': 'kas'},
            {'label': f"{KODE_AKUN['persediaan']['kode']} - {KODE_AKUN['persediaan']['nama']}", 'value': 'persediaan'},
            {'label': f"{KODE_AKUN['perlengkapan']['kode']} - {KODE_AKUN['perlengkapan']['nama']}", 'value': 'perlengkapan'},
            {'label': f"{KODE_AKUN['utang']['kode']} - {KODE_AKUN['utang']['nama']}", 'value': 'utang'},
            {'label': f"{KODE_AKUN['modal']['kode']} - {KODE_AKUN['modal']['nama']}", 'value': 'modal'},
            {'label': f"{KODE_AKUN['pendapatan']['kode']} - {KODE_AKUN['pendapatan']['nama']}", 'value': 'pendapatan'},
            {'label': f"{KODE_AKUN['pendapatan_tiket']['kode']} - {KODE_AKUN['pendapatan_tiket']['nama']}", 'value': 'pendapatan_tiket'},
            {'label': f"{KODE_AKUN['hpp']['kode']} - {KODE_AKUN['hpp']['nama']}", 'value': 'hpp'},
            {'label': f"{KODE_AKUN['tanah']['kode']} - {KODE_AKUN['tanah']['nama']}", 'value': 'tanah'},
            {'label': f"{KODE_AKUN['bangunan_gazebo']['kode']} - {KODE_AKUN['bangunan_gazebo']['nama']}", 'value': 'bangunan_gazebo'},
            {'label': f"{KODE_AKUN['kendaraan']['kode']} - {KODE_AKUN['kendaraan']['nama']}", 'value': 'kendaraan'},
            {'label': f"{KODE_AKUN['peralatan']['kode']} - {KODE_AKUN['peralatan']['nama']}", 'value': 'peralatan'},
            {'label': f"{KODE_AKUN['akumulasi_penyusutan_bangunan']['kode']} - {KODE_AKUN['akumulasi_penyusutan_bangunan']['nama']}", 'value': 'akumulasi_penyusutan_bangunan'},
            {'label': f"{KODE_AKUN['akumulasi_penyusutan_kendaraan']['kode']} - {KODE_AKUN['akumulasi_penyusutan_kendaraan']['nama']}", 'value': 'akumulasi_penyusutan_kendaraan'},
            {'label': f"{KODE_AKUN['akumulasi_penyusutan_peralatan']['kode']} - {KODE_AKUN['akumulasi_penyusutan_peralatan']['nama']}", 'value': 'akumulasi_penyusutan_peralatan'},
            {'label': f"{KODE_AKUN['beban_gaji']['kode']} - {KODE_AKUN['beban_gaji']['nama']}", 'value': 'beban_gaji'},
            {'label': f"{KODE_AKUN['beban_listrik']['kode']} - {KODE_AKUN['beban_listrik']['nama']}", 'value': 'beban_listrik'},
            {'label': f"{KODE_AKUN['beban_penyusutan_bangunan']['kode']} - {KODE_AKUN['beban_penyusutan_bangunan']['nama']}", 'value': 'beban_penyusutan_bangunan'},
            {'label': f"{KODE_AKUN['beban_penyusutan_kendaraan']['kode']} - {KODE_AKUN['beban_penyusutan_kendaraan']['nama']}", 'value': 'beban_penyusutan_kendaraan'},
            {'label': f"{KODE_AKUN['beban_penyusutan_peralatan']['kode']} - {KODE_AKUN['beban_penyusutan_peralatan']['nama']}", 'value': 'beban_penyusutan_peralatan'},
            {'label': f"{KODE_AKUN['beban_lainnya']['kode']} - {KODE_AKUN['beban_lainnya']['nama']}", 'value': 'beban_lainnya'}
        ]
    
    def _get_table_data(self, table_name):
        """Helper function to get all data from a table"""
        if not self.client:
            print(f"❌ Client not available for {table_name}")
            return []
        try:
            response = self.client.table(table_name).select("*").execute()
            print(f"✅ Loaded {len(response.data)} records from {table_name}")
            return response.data
        except Exception as e:
            print(f"❌ Error getting {table_name}: {e}")
            return []
    
    def _insert_table_data(self, table_name, data):
        """Helper function to insert data into a table"""
        if not self.client:
            print(f"❌ Client not available for insert to {table_name}")
            return None
        try:
            response = self.client.table(table_name).insert(data).execute()
            if response.data:
                print(f"✅ Inserted data to {table_name}")
                return response.data[0]
            else:
                print(f"❌ No data returned from insert to {table_name}")
                return None
        except Exception as e:
            print(f"❌ Error inserting to {table_name}: {e}")
            return None
    
    def load_all_data(self):
        """Memuat semua data dari Supabase"""
        print("🔄 Loading all data from Supabase...")
        
        try:
            # Load data transaksi (simpan di storage global, akan difilter per user saat diakses)
            self._all_transaksi_pemasukan = self._get_table_data('transaksi_pemasukan')
            self._all_transaksi_pengeluaran = self._get_table_data('transaksi_pengeluaran')
            self._all_jurnal_umum = self._get_table_data('jurnal_umum')
            self._all_jurnal_penyesuaian = self._get_table_data('jurnal_penyesuaian')
            self._all_kartu_persediaan = self._get_table_data('kartu_persediaan')
            
            # Load aset tetap
            assets_data = self._get_table_data('assets')
            for asset in assets_data:
                if asset['jenis_aset'] in self.aset_tetap:
                    self.aset_tetap[asset['jenis_aset']] = {
                        'nilai_awal': float(asset['nilai_awal']) if asset['nilai_awal'] else 0,
                        'penyusutan': float(asset['penyusutan']) if asset['penyusutan'] else 0,
                        'masa_manfaat': int(asset['masa_manfaat']) if asset['masa_manfaat'] else 0,
                        'tahun_pembelian': int(asset['tahun_pembelian']) if asset['tahun_pembelian'] else datetime.now().year
                    }
            
            print("✅ All data loaded successfully from Supabase")
            print(f"📊 Statistics: {len(self._all_transaksi_pemasukan)} pemasukan, {len(self._all_transaksi_pengeluaran)} pengeluaran")
            print(f"📊 Statistics: {len(self._all_jurnal_umum)} jurnal, {len(self._all_kartu_persediaan)} kartu persediaan")
            
        except Exception as e:
            print(f"❌ Error loading all data from Supabase: {e}")

    # ------------------ User-scoped access helpers ------------------
    def set_active_user(self, user_id):
        """Set active user id untuk memfilter data yang ditampilkan/diakses."""
        if user_id:
            self.active_user_id = str(user_id)
        else:
            self.active_user_id = None

    @property
    def transaksi_pemasukan(self):
        if not self.active_user_id:
            return []
        return [t for t in self._all_transaksi_pemasukan if str(t.get('user_id')) == str(self.active_user_id)]

    @property
    def transaksi_pengeluaran(self):
        if not self.active_user_id:
            return []
        return [t for t in self._all_transaksi_pengeluaran if str(t.get('user_id')) == str(self.active_user_id)]

    @property
    def jurnal_umum(self):
        if not self.active_user_id:
            return []
        return [j for j in self._all_jurnal_umum if str(j.get('user_id')) == str(self.active_user_id)]

    @property
    def jurnal_penyesuaian(self):
        if not self.active_user_id:
            return []
        return [j for j in self._all_jurnal_penyesuaian if str(j.get('user_id')) == str(self.active_user_id)]

    @property
    def kartu_persediaan(self):
        if not self.active_user_id:
            return []
        return [k for k in self._all_kartu_persediaan if str(k.get('user_id')) == str(self.active_user_id)]

    # Suppliers dan buku besar pembantu per-user
    @property
    def suppliers(self):
        uid = str(self.active_user_id) if self.active_user_id else None
        if not uid:
            return []
        if uid not in self._all_suppliers:
            self._all_suppliers[uid] = []
        return self._all_suppliers[uid]

    @suppliers.setter
    def suppliers(self, value):
        uid = str(self.active_user_id) if self.active_user_id else None
        if not uid:
            return
        self._all_suppliers[uid] = value if isinstance(value, list) else list(value)

    @property
    def buku_besar_pembantu(self):
        uid = str(self.active_user_id) if self.active_user_id else None
        if not uid:
            return {}
        if uid not in self._all_buku_besar_pembantu:
            self._all_buku_besar_pembantu[uid] = {}
        return self._all_buku_besar_pembantu[uid]

    @buku_besar_pembantu.setter
    def buku_besar_pembantu(self, value):
        uid = str(self.active_user_id) if self.active_user_id else None
        if not uid:
            return
        self._all_buku_besar_pembantu[uid] = value if isinstance(value, dict) else dict(value)


    def save_data(self):
        """Menyimpan data ke Supabase - untuk backward compatibility"""
        self.save_all_data()

    def save_all_data(self):
        """Menyimpan semua data ke Supabase"""
        try:
            print("💾 Saving all data to Supabase...")
            
            # Simpan transaksi pemasukan (semua storage, tapi sertakan user_id)
            for trans in self._all_transaksi_pemasukan:
                if 'id' not in trans:
                    data_to_save = {
                        'tanggal': trans['tanggal'],
                        'jenis': trans['jenis'],
                        'jumlah': float(trans['jumlah']),
                        'quantity': int(trans.get('quantity', 0)),
                        'hpp': float(trans.get('hpp', 0)),
                        'keterangan': trans.get('keterangan', ''),
                        'ref': trans.get('ref', ''),
                        'kode_akun_debit': trans.get('kode_akun_debit', ''),
                        'kode_akun_kredit': trans.get('kode_akun_kredit', ''),
                        'user_id': trans.get('user_id', self.active_user_id)
                    }
                    saved = self._insert_table_data('transaksi_pemasukan', data_to_save)
                    if saved:
                        trans['id'] = saved['id']

            # Simpan transaksi pengeluaran
            for trans in self._all_transaksi_pengeluaran:
                if 'id' not in trans:
                    data_to_save = {
                        'tanggal': trans['tanggal'],
                        'jenis': trans['jenis'],
                        'kode_barang': trans.get('kode_barang', ''),
                        'jumlah': float(trans['jumlah']),
                        'quantity': int(trans.get('quantity', 0)),
                        'metode_bayar': trans.get('metode_bayar', 'tunai'),
                        'supplier': trans.get('supplier', ''),
                        'keterangan': trans.get('keterangan', ''),
                        'ref': trans.get('ref', ''),
                        'kode_akun_debit': trans.get('kode_akun_debit', ''),
                        'kode_akun_kredit': trans.get('kode_akun_kredit', ''),
                        'user_id': trans.get('user_id', self.active_user_id)
                    }
                    saved = self._insert_table_data('transaksi_pengeluaran', data_to_save)
                    if saved:
                        trans['id'] = saved['id']

            # Simpan jurnal umum
            for jurnal in self._all_jurnal_umum:
                if 'id' not in jurnal:
                    data_to_save = {
                        'tanggal': jurnal['tanggal'],
                        'keterangan': jurnal['keterangan'],
                        'ref': jurnal.get('ref', ''),
                        'akun_debit': jurnal['akun_debit'],
                        'kode_akun_debit': jurnal['kode_akun_debit'],
                        'jumlah_debit': float(jurnal['jumlah_debit']),
                        'akun_kredit': jurnal['akun_kredit'],
                        'kode_akun_kredit': jurnal['kode_akun_kredit'],
                        'jumlah_kredit': float(jurnal['jumlah_kredit']),
                        'user_id': jurnal.get('user_id', self.active_user_id)
                    }
                    saved = self._insert_table_data('jurnal_umum', data_to_save)
                    if saved:
                        jurnal['id'] = saved['id']

            # Simpan jurnal penyesuaian
            for jurnal in self._all_jurnal_penyesuaian:
                if 'id' not in jurnal:
                    data_to_save = {
                        'tanggal': jurnal['tanggal'],
                        'keterangan': jurnal['keterangan'],
                        'ref': jurnal.get('ref', ''),
                        'akun_debit': jurnal['akun_debit'],
                        'kode_akun_debit': jurnal['kode_akun_debit'],
                        'jumlah_debit': float(jurnal['jumlah_debit']),
                        'akun_kredit': jurnal['akun_kredit'],
                        'kode_akun_kredit': jurnal['kode_akun_kredit'],
                        'jumlah_kredit': float(jurnal['jumlah_kredit']),
                        'user_id': jurnal.get('user_id', self.active_user_id)
                    }
                    saved = self._insert_table_data('jurnal_penyesuaian', data_to_save)
                    if saved:
                        jurnal['id'] = saved['id']

            # Simpan kartu persediaan
            for item in self._all_kartu_persediaan:
                if 'id' not in item:
                    data_to_save = {
                        'tanggal': item['tanggal'],
                        'kode_barang': item['kode_barang'],
                        'nama_barang': item['nama_barang'],
                        'masuk_qty': int(item['masuk_qty']),
                        'masuk_harga': float(item['masuk_harga']),
                        'masuk_total': float(item['masuk_total']),
                        'keluar_qty': int(item['keluar_qty']),
                        'keluar_harga': float(item['keluar_harga']),
                        'keluar_total': float(item['keluar_total']),
                        'saldo_qty': int(item['saldo_qty']),
                        'saldo_harga': float(item['saldo_harga']),
                        'saldo_total': float(item['saldo_total']),
                        'keterangan': item.get('keterangan', ''),
                        'user_id': item.get('user_id', self.active_user_id)
                    }
                    saved = self._insert_table_data('kartu_persediaan', data_to_save)
                    if saved:
                        item['id'] = saved['id']
            
            # Simpan aset tetap
            for jenis_aset, data in self.aset_tetap.items():
                if data['nilai_awal'] > 0:  # Hanya simpan aset yang sudah diisi
                    asset_data = {
                        'jenis_aset': jenis_aset,
                        'nilai_awal': float(data['nilai_awal']),
                        'penyusutan': float(data['penyusutan']),
                        'masa_manfaat': int(data['masa_manfaat']),
                        'tahun_pembelian': int(data['tahun_pembelian'])
                    }
                    
                    # Cek apakah aset sudah ada
                    existing_assets = self._get_table_data('assets')
                    existing_asset = next((a for a in existing_assets if a['jenis_aset'] == jenis_aset), None)
                    
                    if existing_asset:
                        # Update existing
                        try:
                            self.client.table('assets').update(asset_data).eq('id', existing_asset['id']).execute()
                            print(f"✅ Updated asset: {jenis_aset}")
                        except Exception as e:
                            print(f"❌ Error updating asset {jenis_aset}: {e}")
                    else:
                        # Insert new
                        saved = self._insert_table_data('assets', asset_data)
                        if saved:
                            print(f"✅ Inserted new asset: {jenis_aset}")
            
            print("✅ All data saved successfully to Supabase")
            
        except Exception as e:
            print(f"❌ Error saving all data to Supabase: {e}")

    def initialize_user_from_template(self, user_id, template_path='sibal_data.json'):
        """Initialize a new user's data by copying from a local template JSON.

        This will attach `user_id` to each record and save to Supabase and in-memory storage.
        """
        try:
            if not os.path.exists(template_path):
                print(f"⚠️ Template file not found: {template_path}")
                return False

            with open(template_path, 'r', encoding='utf-8') as f:
                # file may have markdown fences in repo, try to load JSON content
                content = f.read()
                # strip possible ```json fences
                content = content.strip()
                if content.startswith('```'):
                    # remove first and last fences
                    parts = content.split('\n')
                    # find first line that starts with ``` and remove it
                    if parts[0].startswith('```'):
                        parts = parts[1:]
                    if parts and parts[-1].startswith('```'):
                        parts = parts[:-1]
                    content = '\n'.join(parts)

                data = json.loads(content)

            # Create deterministic random generator per user to make templates unique
            uid = str(user_id)
            seed = int(hashlib.sha256(uid.encode('utf-8')).hexdigest(), 16) % (2**32)
            rng = random.Random(seed)

            # per-user overall scale (makes differences more pronounced)
            user_scale = 0.5 + rng.random() * 2.5  # range 0.5 .. 3.0

            def unique_ref(orig_ref):
                if not orig_ref:
                    orig_ref = 'REF'
                return f"{orig_ref}-{uid[:6]}-{rng.randint(100,999)}"

            def jitter_number(value, pct=0.08, apply_scale=True):
                try:
                    v = float(value)
                except Exception:
                    return value
                base = v * (user_scale if apply_scale else 1.0)
                change = (rng.random() * 2 - 1) * pct
                newv = base * (1 + change)
                # round sensible for money/ints
                if float(value).is_integer():
                    return int(round(newv))
                return float(round(newv, 2))

            # Helper to insert list of records into table and in-memory _all_ list
            def insert_list_unique(table_name, records, target_list_name):
                if not records:
                    return
                # Shuffle and take a variable sample size so different users may get different subsets
                recs = list(records)
                rng.shuffle(recs)
                sample_ratio = rng.uniform(0.5, 1.2)
                sample_size = max(1, int(len(recs) * sample_ratio))
                recs = recs[:sample_size]

                # Optionally add a few synthetic variants per user
                extra_copies = rng.randint(0, max(0, int(len(recs) * 0.3)))
                for _ in range(extra_copies):
                    pick = dict(rng.choice(records))
                    recs.append(pick)

                for rec in recs:
                    rec = dict(rec)  # copy
                    # Make some fields unique/per-user
                    if 'ref' in rec:
                        rec['ref'] = unique_ref(rec.get('ref'))
                    # jitter numeric fields more strongly and apply user scale
                    for num_field in ['jumlah', 'masuk_total', 'masuk_harga', 'keluar_total', 'saldo_total', 'jumlah_debit', 'jumlah_kredit', 'nilai_awal']:
                        if num_field in rec:
                            rec[num_field] = jitter_number(rec[num_field], pct=0.12)
                    # jitter quantity fields
                    for num_field in ['quantity', 'masuk_qty', 'keluar_qty', 'saldo_qty']:
                        if num_field in rec:
                            try:
                                rec[num_field] = int(jitter_number(rec[num_field], pct=0.25))
                            except Exception:
                                pass
                    # shift dates
                    for k in list(rec.keys()):
                        if 'tanggal' in k and isinstance(rec[k], str):
                            try:
                                dt = datetime.fromisoformat(rec[k])
                                dt = dt + timedelta(days=rng.randint(-30, 30))
                                rec[k] = dt.date().isoformat()
                            except Exception:
                                pass
                    # supplier uniqueness
                    if 'supplier' in rec and rec.get('supplier'):
                        rec['supplier'] = f"{rec.get('supplier')}-{uid[-4:]}"
                    rec['user_id'] = uid
                    # Try to insert robustly: if DB rejects unknown column, remove it and retry
                    saved = None
                    if not self.client:
                        saved = None
                    else:
                        attempts = 0
                        data_to_try = dict(rec)
                        while attempts < 5:
                            try:
                                resp = self.client.table(table_name).insert(data_to_try).execute()
                                if resp and getattr(resp, 'data', None):
                                    saved = resp.data[0]
                                break
                            except Exception as e:
                                msg = str(e)
                                import re
                                m = re.search(r"Could not find the '([a-zA-Z0-9_]+)' column", msg)
                                if m:
                                    col = m.group(1)
                                    if col in data_to_try:
                                        del data_to_try[col]
                                        attempts += 1
                                        continue
                                # fallback: stop retrying
                                break
                    if saved:
                        rec['id'] = saved.get('id')
                    # Always append to in-memory storage so per-user view exists even if DB insert failed
                    getattr(self, target_list_name).append(rec)

            insert_list_unique('transaksi_pemasukan', data.get('transaksi_pemasukan', []), '_all_transaksi_pemasukan')
            insert_list_unique('transaksi_pengeluaran', data.get('transaksi_pengeluaran', []), '_all_transaksi_pengeluaran')
            insert_list_unique('jurnal_umum', data.get('jurnal_umum', []), '_all_jurnal_umum')
            insert_list_unique('jurnal_penyesuaian', data.get('jurnal_penyesuaian', []), '_all_jurnal_penyesuaian')
            insert_list_unique('kartu_persediaan', data.get('kartu_persediaan', []), '_all_kartu_persediaan')

            # suppliers: store per-user list and append uid suffix so names are unique per user
            sups = data.get('suppliers', [])
            self._all_suppliers[uid] = [f"{s}_{uid[:6]}" for s in sups]

            # buku_besar_pembantu: copy and prefix with user_id (and adapt supplier names)
            bbp = data.get('buku_besar_pembantu', {})
            self._all_buku_besar_pembantu[uid] = {}
            for sup, items in bbp.items():
                sup_uid = f"{sup}_{uid[:6]}"
                self._all_buku_besar_pembantu[uid][sup_uid] = []
                for item in items:
                    item_copy = dict(item)
                    item_copy['user_id'] = uid
                    # jitter numeric fields in helper
                    for num_field in ['debit', 'kredit', 'saldo']:
                        if num_field in item_copy:
                            item_copy[num_field] = jitter_number(item_copy[num_field])
                    self._all_buku_besar_pembantu[uid][sup_uid].append(item_copy)

            # aset_tetap: store under user context in assets table, jitter nilai_awal a bit
            aset = data.get('aset_tetap', {})
            for jenis, asetdata in aset.items():
                asetdata_copy = dict(asetdata)
                asetdata_copy['jenis_aset'] = jenis
                # jitter nilai_awal
                if 'nilai_awal' in asetdata_copy:
                    asetdata_copy['nilai_awal'] = jitter_number(asetdata_copy['nilai_awal'], pct=0.15)
                asetdata_copy['user_id'] = uid
                # insert with same robust approach
                if self.client:
                    attempts = 0
                    data_to_try = dict(asetdata_copy)
                    while attempts < 5:
                        try:
                            resp = self.client.table('assets').insert(data_to_try).execute()
                            break
                        except Exception as e:
                            msg = str(e)
                            import re
                            m = re.search(r"Could not find the '([a-zA-Z0-9_]+)' column", msg)
                            if m:
                                col = m.group(1)
                                if col in data_to_try:
                                    del data_to_try[col]
                                    attempts += 1
                                    continue
                            break

            print(f"✅ Initialized unique template data for user {user_id}")
            return True
        except Exception as e:
            print(f"❌ Error initializing user from template: {e}")
            return False

    def kurangi_persediaan(self, kode_barang, qty, tanggal, keterangan):
        """Mengurangi persediaan saat penjualan dengan metode FIFO"""
        try:
            # Cari barang di master
            barang = next((item for item in self.master_persediaan if item['kode'] == kode_barang), None)
            if not barang:
                print(f"Barang dengan kode {kode_barang} tidak ditemukan")
                return False
            
            # Hitung saldo terakhir
            saldo_terakhir = 0
            saldo_harga = 0
            if self.kartu_persediaan:
                transaksi_barang = [t for t in self.kartu_persediaan if t['kode_barang'] == kode_barang]
                if transaksi_barang:
                    saldo_terakhir = transaksi_barang[-1]['saldo_qty']
                    saldo_harga = transaksi_barang[-1]['saldo_harga']
            
            if saldo_terakhir < qty:
                print(f"Stok tidak cukup. Stok tersedia: {saldo_terakhir}, butuh: {qty}")
                return False
            
            # Hitung dengan metode FIFO
            total_keluar = 0
            sisa_qty = qty
            transaksi_masuk = [t for t in self.kartu_persediaan 
                              if t['kode_barang'] == kode_barang and t['masuk_qty'] > 0]
            
            for trans in transaksi_masuk:
                if sisa_qty <= 0:
                    break
                
                if trans['saldo_qty'] > 0:
                    qty_keluar = min(sisa_qty, trans['saldo_qty'])
                    harga_keluar = trans['masuk_harga']  # FIFO: pakai harga pembelian pertama
                    
                    total_keluar += qty_keluar * harga_keluar
                    sisa_qty -= qty_keluar
            
            # Buat entri kartu persediaan
            saldo_qty_baru = saldo_terakhir - qty
            saldo_harga_baru = saldo_harga  # Harga rata-rata tidak berubah untuk FIFO
            
            entri_persediaan = {
                'tanggal': tanggal,
                'kode_barang': kode_barang,
                'nama_barang': barang['nama'],
                'masuk_qty': 0,
                'masuk_harga': 0,
                'masuk_total': 0,
                'keluar_qty': qty,
                'keluar_harga': total_keluar / qty if qty > 0 else 0,
                'keluar_total': total_keluar,
                'saldo_qty': saldo_qty_baru,
                'saldo_harga': saldo_harga_baru,
                'saldo_total': saldo_qty_baru * saldo_harga_baru,
                'keterangan': f'Penjualan - {keterangan}'
            }
            
            entri_persediaan['user_id'] = self.active_user_id
            self._all_kartu_persediaan.append(entri_persediaan)
            return True
            
        except Exception as e:
            print(f"Error mengurangi persediaan: {e}")
            return False
    
    # TAMBAHKAN JUGA FUNGSI INI:
    def get_harga_pokok(self, kode_barang):
        """Mendapatkan harga pokok dari master persediaan"""
        barang = next((item for item in self.master_persediaan if item['kode'] == kode_barang), None)
        return barang['harga_beli'] if barang else 0
    
sibal_data = SIBALData()

def create_top_navigation():
    # Gunakan try-except untuk handle kasus current_user None
    try:
        is_authenticated = current_user.is_authenticated
    except:
        is_authenticated = False
    
    if is_authenticated:
        user_section = html.Div([
            html.Div([
                html.Div("👤", className="avatar"),
                html.Div([
                    html.Div(current_user.username, style={'fontWeight': '600', 'fontSize': '0.95rem'}),
                    html.Div(current_user.email, style={'fontSize': '0.8rem', 'opacity': '0.7'})
                ])
            ], className="user-menu"),
            html.A(
                html.Div([
                    html.I(className="fas fa-sign-out-alt"),
                    " Logout"
                ], className="nav-link"),
                href="/auth/logout",
                style={'textDecoration': 'none'}
            )
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'})
    else:
        user_section = html.Div([
            dcc.Link([
                html.I(className="fas fa-sign-in-alt"),
                " Login"
            ], href="/login", className="nav-link"),
            dcc.Link([
                html.I(className="fas fa-user-plus"),
                " Daftar"
            ], href="/signup", className="nav-link")
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '10px'})
    
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.Img(
                        src="/assets/logo-sibal-png.png",
                        style={
                            'width': '100%',
                            'height': '100%',
                            'objectFit': 'contain'
                        }
                    )
                ], className="brand-logo"),
                html.Div("SIBAL", className="brand-text")
            ], className="nav-brand"),
            
            html.Div([
                dcc.Link([
                    html.I(className="fas fa-home"),
                    " Dashboard"
                ], href="/", className="nav-link"),
                dcc.Link([
                    html.I(className="fas fa-calculator"),
                    " Akuntansi Dasar"
                ], href="/akuntansi-dasar", className="nav-link"),
                dcc.Link([
                    html.I(className="fas fa-chart-bar"),
                    " Laporan & Analisis"
                ], href="/laporan-analisis", className="nav-link"),
            ], className="nav-links"),
            
            user_section
        ], className="nav-container"),
    ], className="glass-nav")

def create_akuntansi_sub_nav():
    return html.Div([
        html.Div([
            dcc.Link([
                html.I(className="fas fa-edit"),
                " Transaksi"
            ], href="/transaksi", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-box"),
                " Kartu Persediaan"
            ], href="/kartu-persediaan", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-book"),
                " Jurnal Umum"
            ], href="/jurnal-umum", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-book-open"),
                " Buku Besar"
            ], href="/buku-besar", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-users"),
                " Buku Besar Pembantu"
            ], href="/buku-besar-pembantu", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-building"),
                " Aset Tetap"
            ], href="/aset-tetap", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-balance-scale"),
                " Neraca Saldo"
            ], href="/neraca-saldo", className="sub-nav-link"),
        ], className="sub-nav-container"),
    ], className="sub-nav")

def create_laporan_sub_nav():
    return html.Div([
        html.Div([
            dcc.Link([
                html.I(className="fas fa-sync-alt"),
                " Jurnal Penyesuaian"
            ], href="/jurnal-penyesuaian", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-chart-line"),
                " Neraca Setelah Penyesuaian"
            ], href="/neraca-setelah-penyesuaian", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-money-bill-wave"),
                " Laporan Laba Rugi"
            ], href="/laporan-laba-rugi", className="sub-nav-link"),
            dcc.Link([
                html.I(className="fas fa-file-alt"),
                " Laporan Keuangan"
            ], href="/laporan-keuangan", className="sub-nav-link"),
        ], className="sub-nav-container"),
    ], className="sub-nav")

def dashboard_layout():
    total_pemasukan = sum(t.get('jumlah', 0) for t in sibal_data.transaksi_pemasukan)
    total_pengeluaran = sum(t.get('jumlah', 0) for t in sibal_data.transaksi_pengeluaran)
    total_jurnal = len(sibal_data.jurnal_umum)
    total_persediaan = len(sibal_data.kartu_persediaan)
    
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-gem")
                ], className="card-icon"),
                html.Div([
                    html.H1("Dashboard SIBAL", className="card-title"),
                    html.P("Sistem Informasi Berbasis Akuntansi Ikan Bawal", className="card-subtitle")
                ])
            ], className="card-header")
        ], className="glass-card"),
        
        html.Div([
            html.Div([
                html.Div("Rp {:,.0f}".format(total_pemasukan), className="stat-value"),
                html.Div("Total Pendapatan", className="stat-label"),
                html.I(className="fas fa-arrow-up stat-icon")
            ], className="stat-card"),
            html.Div([
                html.Div("Rp {:,.0f}".format(total_pengeluaran), className="stat-value"),
                html.Div("Total Pengeluaran", className="stat-label"),
                html.I(className="fas fa-arrow-down stat-icon")
            ], className="stat-card"),
            html.Div([
                html.Div("{:d}".format(total_jurnal), className="stat-value"),
                html.Div("Jurnal Umum", className="stat-label"),
                html.I(className="fas fa-book stat-icon")
            ], className="stat-card"),
            html.Div([
                html.Div("{:d}".format(total_persediaan), className="stat-value"),
                html.Div("Kartu Persediaan", className="stat-label"),
                html.I(className="fas fa-box stat-icon")
            ], className="stat-card"),
        ], className="stats-grid"),
        
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-rocket")
                ], className="card-icon"),
                html.H2("Aksi Cepat", className="card-title")
            ], className="card-header"),
            
            html.Div([
                dcc.Link([
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-calculator")
                        ], className="action-icon"),
                        html.H3("Akuntansi Dasar", className="action-title"),
                        html.P("Kelola transaksi, jurnal, dan buku besar dengan fitur lengkap", className="action-desc")
                    ])
                ], href="/akuntansi-dasar", className="action-card"),
                
                dcc.Link([
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-chart-bar")
                        ], className="action-icon"),
                        html.H3("Laporan & Analisis", className="action-title"),
                        html.P("Generate laporan keuangan lengkap dan analisis mendalam", className="action-desc")
                    ])
                ], href="/laporan-analisis", className="action-card"),
            ], className="actions-grid"),
        ], className="glass-card"),
    ], className="main-container")

def format_rupiah(amount):
    """Format number to Rupiah currency dengan pemisah ribuan"""
    if amount == 0:
        return ""
    return f"Rp{amount:,.0f}".replace(",", ".")

# ========== LAYOUT FUNCTIONS YANG DIPERBAIKI ==========

def transaksi_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-edit")
                ], className="card-icon"),
                html.H1("Transaksi Pemancingan Bawal", className="card-title")
            ], className="card-header")
        ], className="glass-card"),
        
        html.Div([
            html.H4("Pilih Tanggal Transaksi:", className="form-label"),
            dcc.DatePickerSingle(
                id='selected-date',
                date=datetime.now().date(),
                display_format='YYYY-MM-DD',
                className="form-control"
            )
        ], className="glass-card"),
        
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-arrow-down")
                ], className="card-icon"),
                html.H2("Pemasukan - Pendapatan Pemancingan", className="card-title")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.H3("Input Transaksi Pendapatan", className="form-section-title"),
                    dcc.Dropdown(
                        id='pemasukan-jenis',
                        options=[
                            {'label': 'Tiket Masuk', 'value': 'tiket_masuk'},
                            {'label': 'Penjualan Ikan Bawal', 'value': 'penjualan_ikan'},
                            {'label': 'Setoran Modal', 'value': 'modal'}
                        ],
                        placeholder='Pilih Jenis Transaksi',
                        className="form-control"
                    ),
                    # SESUDAH:
                    html.Div([
                        html.Label("Harga Jual per Unit", className="form-label"),
                        dcc.Input(
                            id='pemasukan-harga-jual',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),

                    html.Div([
                        html.Label("Quantity", className="form-label"),
                        dcc.Input(
                            id='pemasukan-qty',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),

                    html.Div([
                        html.Label("Quantity (kg) - untuk penjualan ikan", className="form-label"),
                        dcc.Input(
                            id='pemasukan-qty',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("HPP per kg (untuk penjualan ikan)", className="form-label"),
                        dcc.Input(
                            id='pemasukan-hpp',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("Keterangan Transaksi", className="form-label"),
                        dcc.Input(
                            id='pemasukan-keterangan',
                            type='text',
                            placeholder='Keterangan...',
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("Nomor Referensi", className="form-label"),
                        dcc.Input(
                            id='pemasukan-ref',
                            type='text',
                            placeholder='REF-...',
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Button(
                        "➕ Tambah Transaksi",
                        id='btn-tambah-pemasukan',
                        className="btn btn-success"
                    )
                ], className="form-container compact-form"),
                
                html.Div([
                    html.H3("Daftar Transaksi Pendapatan", className="form-section-title"),
                    html.Div(id='daftar-pemasukan', className="data-container"),
                    html.Button(
                        "🗑️ Hapus Transaksi Terpilih",
                        id='btn-hapus-pemasukan',
                        className="btn btn-danger"
                    ),
                    html.Hr(),
                    html.Button(
                        "📊 Akumulasi ke Jurnal",
                        id='btn-akumulasi-pemasukan',
                        className="btn btn-primary"
                    )
                ], className="data-container"),
            ], className="form-row"),
        ], className="glass-card"),
        
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-arrow-up")
                ], className="card-icon"),
                html.H2("Pengeluaran - Pembelian & Beban", className="card-title")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.H3("Input Pengeluaran", className="form-section-title"),
                    dcc.Dropdown(
                        id='pengeluaran-jenis',
                        options=[
                            {'label': 'Pembelian Persediaan', 'value': 'pembelian_persediaan'},
                            {'label': 'Beban Gaji', 'value': 'beban_gaji'},
                            {'label': 'Beban Listrik', 'value': 'beban_listrik'},
                            {'label': 'Beban Penyusutan Bangunan', 'value': 'beban_penyusutan_bangunan'},
                            {'label': 'Beban Penyusutan Kendaraan', 'value': 'beban_penyusutan_kendaraan'},
                            {'label': 'Beban Penyusutan Peralatan', 'value': 'beban_penyusutan_peralatan'},
                            {'label': 'Beban Lainnya', 'value': 'beban_lainnya'}
                        ],
                        placeholder='Pilih Jenis Pengeluaran',
                        className="form-control"
                    ),
                    dcc.Dropdown(
                        id='pengeluaran-barang',
                        options=[{'label': f"{item['kode']} - {item['nama']}", 'value': item['kode']} 
                                for item in sibal_data.master_persediaan],
                        placeholder='Pilih Barang (hanya untuk pembelian persediaan)',
                        className="form-control"
                    ),
                    

                    # SESUDAH:
                    html.Div([
                        html.Label("HPP per Unit", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-hpp',
                            type='number',
                            placeholder='0',
                            min=0,
                            className="form-input"
                        )
                    ], className="form-group"),

                    html.Div([
                        html.Label("Quantity", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-qty',
                            type='number',
                            placeholder='0',
                            min=1,
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("Quantity (kg) - hanya untuk pembelian persediaan", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-qty',
                            type='number',
                            placeholder='0',
                            min=1,
                            className="form-input"
                        )
                    ], className="form-group"),
                    dcc.Dropdown(
                        id='pengeluaran-metode',
                        options=[
                            {'label': 'Tunai', 'value': 'tunai'},
                            {'label': 'Kredit', 'value': 'kredit'}
                        ],
                        placeholder='Metode Pembayaran',
                        className="form-control"
                    ),
                    html.Div([
                        html.Label("Nama Supplier (jika kredit)", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-supplier',
                            type='text',
                            placeholder='Nama supplier...',
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("Keterangan Pengeluaran", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-keterangan',
                            type='text',
                            placeholder='Keterangan...',
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Div([
                        html.Label("Nomor Referensi", className="form-label"),
                        dcc.Input(
                            id='pengeluaran-ref',
                            type='text',
                            placeholder='REF-...',
                            className="form-input"
                        )
                    ], className="form-group"),
                    html.Button(
                        "➕ Tambah Pengeluaran",
                        id='btn-tambah-pengeluaran',
                        className="btn btn-danger"
                    )
                ], className="form-container compact-form"),
                
                html.Div([
                    html.H3("Daftar Pengeluaran", className="form-section-title"),
                    html.Div(id='daftar-pengeluaran', className="data-container"),
                    html.Button(
                        "🗑️ Hapus Pengeluaran Terpilih",
                        id='btn-hapus-pengeluaran',
                        className="btn btn-danger"
                    ),
                    html.Hr(),
                    html.Button(
                        "📊 Akumulasi ke Jurnal",
                        id='btn-akumulasi-pengeluaran',
                        className="btn btn-primary"
                    )
                ], className="data-container"),
            ], className="form-row"),
        ], className="glass-card"),
        
        html.Div([
            html.H3("📈 Summary Akumulasi", className="card-title"),
            html.Div(id='summary-akumulasi', className="summary-container")
        ], className="glass-card"),
    ], className="main-container")

def jurnal_umum_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-book")
                ], className="card-icon"),
                html.H1("Jurnal Umum", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Button(
                    "🔄 Refresh Data",
                    id='btn-refresh-jurnal',
                    className="btn btn-primary"
                ),
                html.Hr(),
                html.H3("Daftar Jurnal Umum", className="form-section-title"),
                html.Div(id='tabel-jurnal-umum', className="table-container"),
                html.Hr(),
                html.H3("Rekapitulasi Jurnal Umum", className="form-section-title"),
                html.Div(id='rekapitulasi-jurnal', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def kartu_persediaan_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-box")
                ], className="card-icon"),
                html.H1("Kartu Persediaan Ikan Bawal", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Button(
                    "🔄 Refresh Data",
                    id='btn-refresh-persediaan',
                    className="btn btn-primary",
                    style={'marginBottom': '20px'}
                ),
                html.Div(id='tabel-kartu-persediaan', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def buku_besar_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-book-open")
                ], className="card-icon"),
                html.H1("Buku Besar", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.H3("Pilih Akun Buku Besar", className="form-section-title"),
                    dcc.Dropdown(
                        id='dropdown-akun-buku-besar',
                        options=sibal_data.daftar_akun,
                        placeholder='Pilih Akun Buku Besar',
                        className="form-control"
                    )
                ], className="form-container compact-form"),
                html.Div(id='detail-buku-besar', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def buku_besar_pembantu_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-users")
                ], className="card-icon"),
                html.H1("Buku Besar Pembantu - Utang", className="card-title")
            ], className="card-header"),
            html.Div([
                # TOMBOL REFRESH dengan callback yang benar
                html.Div([
                    html.Button(
                        "🔄 Refresh Data",
                        id='btn-refresh-buku-pembantu',
                        className="btn btn-primary",
                        style={'marginBottom': '20px'}
                    )
                ], style={'textAlign': 'center'}),
                
                html.H3("Daftar Supplier", className="form-section-title"),
                html.Div(id='daftar-supplier', className="data-container"),
                html.Hr(),
                html.H3("Detail Utang per Supplier", className="form-section-title"),
                html.Div(id='detail-buku-besar-pembantu', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def neraca_saldo_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-balance-scale")
                ], className="card-icon"),
                html.H1("Neraca Saldo", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.Label("Periode Neraca Saldo", className="form-label"),
                    dcc.DatePickerSingle(
                        id='tanggal-neraca-saldo',
                        date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group"),
                html.Button(
                    "📊 Generate Neraca Saldo",
                    id='btn-generate-neraca-saldo',
                    className="btn btn-primary"
                ),
                html.Div(id='tabel-neraca-saldo', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def jurnal_penyesuaian_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-sync-alt")
                ], className="card-icon"),
                html.H1("Jurnal Penyesuaian", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.Label("Periode Jurnal Penyesuaian", className="form-label"),
                    dcc.DatePickerSingle(
                        id='tanggal-penyesuaian',
                        date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group"),
                html.Button(
                    "📊 Generate Jurnal Penyesuaian",
                    id='btn-generate-penyesuaian',
                    className="btn btn-primary"
                ),
                html.Div(id='daftar-jurnal-penyesuaian', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def neraca_setelah_penyesuaian_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-chart-line")
                ], className="card-icon"),
                html.H1("Neraca Setelah Penyesuaian", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.Label("Pilih Tanggal Neraca:", className="form-label"),
                    dcc.DatePickerSingle(
                        id='tanggal-neraca-penyesuaian',
                        date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group"),
                html.Button(
                    "📊 Generate Neraca Setelah Penyesuaian",
                    id='btn-generate-neraca-penyesuaian',
                    className="btn btn-primary"
                ),
                html.Div(id='tabel-neraca-penyesuaian', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def laporan_laba_rugi_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-money-bill-wave")
                ], className="card-icon"),
                html.H1("Laporan Laba Rugi", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.Label("Periode Laporan Laba Rugi", className="form-label"),
                    dcc.DatePickerSingle(
                        id='tanggal-laba-rugi',
                        date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group"),
                html.Button(
                    "📊 Generate Laporan Laba Rugi",
                    id='btn-generate-laba-rugi',
                    className="btn btn-primary"
                ),
                html.Div(id='tabel-laba-rugi', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def neraca_lajur_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-table")
                ], className="card-icon"),
                html.H1("Neraca Lajur", className="card-title"),
                html.P("Worksheet - Laporan Keuangan Komprehensif", className="card-subtitle")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.Label("Periode Neraca Lajur:", className="form-label"),
                    dcc.DatePickerRange(
                        id='periode-neraca-lajur',
                        start_date=datetime.now().date().replace(day=1),  # awal bulan
                        end_date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group", style={'marginBottom': '20px'}),
                
                html.Button(
                    "📊 Generate Neraca Lajur",
                    id='btn-generate-neraca-lajur',
                    className="btn btn-primary",
                    style={'marginBottom': '20px'}
                ),
                
                html.Div(id='tabel-neraca-lajur', className="table-container")
                
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

def neraca_lajur_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-table")
                ], className="card-icon"),
                html.H1("Neraca Lajur", className="card-title"),
                html.P("Worksheet - Laporan Keuangan Komprehensif", className="card-subtitle")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.Label("Periode Neraca Lajur:", className="form-label"),
                    dcc.DatePickerRange(
                        id='periode-neraca-lajur',
                        start_date=datetime.now().date().replace(day=1),  # awal bulan
                        end_date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group", style={'marginBottom': '20px'}),
                
                html.Button(
                    "📊 Generate Neraca Lajur",
                    id='btn-generate-neraca-lajur',
                    className="btn btn-primary",
                    style={'marginBottom': '20px'}
                ),
                
                html.Div(id='tabel-neraca-lajur', className="table-container")
                
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")


def laporan_keuangan_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-file-alt")
                ], className="card-icon"),
                html.H1("Laporan Keuangan Lengkap", className="card-title")
            ], className="card-header"),
            html.Div([
                html.Div([
                    html.Label("Pilih Tanggal Laporan:", className="form-label"),
                    dcc.DatePickerSingle(
                        id='tanggal-laporan-keuangan',
                        date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group"),
                html.Button(
                    "📊 Generate Laporan Keuangan Lengkap",
                    id='btn-generate-laporan-keuangan',
                    className="btn btn-primary"
                ),
                html.Div(id='tabel-laporan-keuangan', className="table-container")
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

# ==================== CALLBACKS YANG DIPERBAIKI ====================
# Callback untuk complete profile
@app.callback(
    [Output('complete-profile-alert', 'children'),
     Output('complete-username', 'value'),
     Output('complete-password', 'value'),
     Output('complete-confirm-password', 'value')],
    Input('btn-complete-profile', 'n_clicks'),
    [State('complete-username', 'value'),
     State('complete-password', 'value'),
     State('complete-confirm-password', 'value')],
    prevent_initial_call=True
)
def handle_complete_profile(n_clicks, username, password, confirm_password):
    if n_clicks and n_clicks > 0:
        oauth_user = session.get('oauth_user')
        
        if not oauth_user:
            return create_alert("Session expired. Silakan login kembali.", "error"), "", "", ""
        
        if not all([username, password, confirm_password]):
            return create_alert("Harap lengkapi semua field.", "error"), dash.no_update, "", ""
        
        if password != confirm_password:
            return create_alert("Password dan konfirmasi password tidak cocok.", "error"), dash.no_update, "", ""
        
        if len(password) < 6:
            return create_alert("Password minimal 6 karakter.", "error"), dash.no_update, "", ""
        
        # Create user dengan fungsi yang sudah diperbaiki
        user, message = create_user(username, oauth_user['email'], password)
        
        if not user:
            return create_alert(message, "error"), dash.no_update, "", ""
        
        # Login user dengan fungsi yang sudah diperbaiki
        login_user(user, remember=True)
        
        # Clear oauth session
        session.pop('oauth_user', None)
        
        return html.Div([
            html.P("✅ Profil berhasil disimpan! Redirecting...", 
                  style={'color': COLORS['success'], 'textAlign': 'center', 'fontWeight': 'bold'}),
            dcc.Location(href='/', id='redirect-home', refresh=True)
        ]), "", "", ""
    
        sibal_data.save_all_data()    
          
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update


from flask import request
import json

from authlib.integrations.flask_client import OAuth

# Setup OAuth
oauth = OAuth(server)

# In-memory store for temporarily keeping oauth_user keyed by state.
# This avoids losing the user data when browser cookies are restricted during OAuth redirects.
OAUTH_STATE_STORE = {}

# Konfigurasi Google OAuth - GANTI dengan credentials Anda
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = os.getenv('GOOGLE_CLIENT_SECRET')
GOOGLE_REDIRECT_URI = os.getenv('GOOGLE_REDIRECT_URI', 'http://localhost:8051/auth/callback')

# If env vars missing, try local client_secret JSON files (untracked)
if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
    cid, csec = _load_google_credentials_from_local_file()
    if cid and csec:
        GOOGLE_CLIENT_ID = GOOGLE_CLIENT_ID or cid
        GOOGLE_CLIENT_SECRET = GOOGLE_CLIENT_SECRET or csec
        # also set in environment so other parts can read it
        os.environ.setdefault('GOOGLE_CLIENT_ID', GOOGLE_CLIENT_ID)
        os.environ.setdefault('GOOGLE_CLIENT_SECRET', GOOGLE_CLIENT_SECRET)

# Debug info (do not print secrets)
print(f"🔐 Google Client ID set: {bool(GOOGLE_CLIENT_ID)}")
print(f"🔐 Google Client Secret set: {bool(GOOGLE_CLIENT_SECRET)}")

try:
    google = oauth.register(
        name='SIBAL',
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url='https://accounts.google.com/.well-known/openid_configuration',
        client_kwargs={
            'scope': 'openid email profile',
            'redirect_uri': 'http://localhost:8051/auth/callback'  # PASTIKAN INI SAMA
        }
    )
    print("✅ Google OAuth configured successfully")
except Exception as e:
    print(f"❌ Google OAuth configuration failed: {e}")
    google = None

@server.route('/auth/login')
def auth_login():
    """Redirect ke Google OAuth"""
    try:
        # Generate state untuk security
        state = secrets.token_urlsafe(16)
        # Store state in both session and in-memory store as a fallback
        session['oauth_state'] = state
        # capture action from query param so callback can behave accordingly
        try:
            action = request.args.get('action')
        except Exception:
            action = None
        OAUTH_STATE_STORE[state] = {'action': action}
        try:
            # Keep session persistent for the OAuth flow
            session.permanent = True
        except Exception:
            pass
        
        # Build Google OAuth URL
        base_url = "https://accounts.google.com/o/oauth2/v2/auth"
        params = {
            'client_id': GOOGLE_CLIENT_ID,
            'redirect_uri': GOOGLE_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile',
            'access_type': 'offline',
            'prompt': 'select_account',
            'state': state
        }
        
        auth_url = f"{base_url}?{'&'.join([f'{k}={v}' for k, v in params.items()])}"
        print(f"🔐 Redirecting to Google OAuth")
        return redirect(auth_url)
        
    except Exception as e:
        print(f"❌ Auth error: {e}")
        return redirect('/login?error=auth_failed')

@server.route('/auth/callback')
def auth_callback():
    """Handle callback dari Google OAuth - SELALU redirect ke complete profile"""
    try:
        print("🔵 Processing Google OAuth callback...")
        # Dump session and args for debugging session persistence
        try:
            print("🔎 Session before processing:", dict(session))
        except Exception:
            print("🔎 Session not printable or empty")
        try:
            print("🔎 Callback args:", dict(request.args))
        except Exception:
            pass
        
        # Verify state - allow if the state matches session or is present in the in-memory store
        state = request.args.get('state')
        sess_state = session.get('oauth_state')
        if not state:
            print("❌ Missing state parameter")
            return redirect('/login?error=invalid_state')
        if state != sess_state and state not in OAUTH_STATE_STORE:
            print("❌ Invalid state parameter")
            return redirect('/login?error=invalid_state')
        
        # Get authorization code
        code = request.args.get('code')
        if not code:
            print("❌ No authorization code")
            return redirect('/login?error=no_code')
        
        # Token exchange dengan Google
        token_url = "https://oauth2.googleapis.com/token"
        token_data = {
            'client_id': GOOGLE_CLIENT_ID,
            'client_secret': GOOGLE_CLIENT_SECRET,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': GOOGLE_REDIRECT_URI
        }
        
        print("🔄 Exchanging code for token...")
        token_response = requests.post(token_url, data=token_data)
        token_json = token_response.json()
        
        if 'error' in token_json:
            print(f"❌ Token exchange error: {token_json}")
            return redirect('/login?error=token_failed')
        
        access_token = token_json.get('access_token')
        print(f"✅ Token received successfully")
        
        # Get user info dari Google
        userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
        headers = {'Authorization': f'Bearer {access_token}'}
        userinfo_response = requests.get(userinfo_url, headers=headers)
        userinfo = userinfo_response.json()
        
        print(f"✅ User info received: {userinfo['email']}")
        
        # SELALU redirect ke complete profile, bahkan jika user sudah ada
        oauth_user_obj = {
            'id': userinfo['sub'],
            'email': userinfo['email'],
            'name': userinfo.get('name', userinfo['email'].split('@')[0]),
            'picture': userinfo.get('picture', ''),
            'auth_provider': 'google'
        }

        # Store oauth_user in the in-memory fallback store keyed by state
        try:
            if state in OAUTH_STATE_STORE and isinstance(OAUTH_STATE_STORE[state], dict):
                OAUTH_STATE_STORE[state]['oauth_user'] = oauth_user_obj
            else:
                OAUTH_STATE_STORE[state] = {'action': None, 'oauth_user': oauth_user_obj}
            print(f"🆕 Stored oauth_user in OAUTH_STATE_STORE for state {state}")
        except Exception as e:
            print(f"⚠️ Failed to store oauth_user in OAUTH_STATE_STORE: {e}")

        # Also set in session if possible
        try:
            session['oauth_user'] = oauth_user_obj
            session.permanent = True
        except Exception:
            pass

        # Decide behavior based on action stored for this state ('signup' or 'login')
        try:
            stored = OAUTH_STATE_STORE.get(state, {}) if state else {}
            action = stored.get('action') if isinstance(stored, dict) else None

            users = sibal_data._get_table_data('users')
            existing = next((u for u in users if u.get('email') == userinfo.get('email')), None)

            if action == 'signup':
                # create user if not exists, but DO NOT login automatically
                if existing:
                    print(f"🔁 User already exists for signup email: {existing.get('email')}")
                else:
                    uname = (userinfo.get('email') or '').split('@')[0]
                    user_payload = {
                        'email': userinfo.get('email'),
                        'username': uname,
                        'name': userinfo.get('name', uname),
                        'auth_provider': 'google'
                    }
                    created = sibal_data._insert_table_data('users', user_payload)
                    if created:
                        print(f"✅ Created new user (signup) in DB for {created.get('email')}")
                        try:
                            sibal_data.initialize_user_from_template(created.get('id'))
                        except Exception as e:
                            print(f"⚠️ Failed to initialize template for new user: {e}")
                    else:
                        print("❌ Failed to create user record in DB during signup flow")

                # cleanup and redirect to login page with flag
                try:
                    OAUTH_STATE_STORE.pop(state, None)
                except Exception:
                    pass
                try:
                    session.pop('oauth_user', None)
                except Exception:
                    pass
                return redirect('/login?registered=google')

            else:
                # Default/login flow: if user exists, login; if not, redirect to complete-profile
                if existing:
                    try:
                        login_user(existing, remember=True)
                        try:
                            OAUTH_STATE_STORE.pop(state, None)
                        except Exception:
                            pass
                        try:
                            session.pop('oauth_user', None)
                        except Exception:
                            pass
                        print(f"🔐 Logged in user via Google: {existing.get('email')}")
                        return redirect('/')
                    except Exception as e:
                        print(f"❌ Failed to login user after Google callback: {e}")
                        return redirect('/login?error=login_failed')
                else:
                    # No existing user: require complete profile (username/password)
                    print("ℹ️ No existing user for this Google account; redirecting to complete-profile to create account")
                    # ensure oauth_user is in store for recovery
                    if state and isinstance(OAUTH_STATE_STORE.get(state), dict):
                        OAUTH_STATE_STORE[state]['oauth_user'] = oauth_user_obj
                    return redirect(f'/complete-profile?state={state}')

        except Exception as e:
            print(f"❌ Error creating/fetching user after OAuth: {e}")
            import traceback
            traceback.print_exc()
            return redirect('/login?error=callback_failed')
            
    except Exception as e:
        print(f"❌ Callback error: {e}")
        import traceback
        traceback.print_exc()
        return redirect('/login?error=callback_failed')

@server.route('/auth/logout')
def auth_logout():
    """Logout user"""
    global current_user
    current_user = SimpleUser()
    # Clear active user from data layer
    try:
        sibal_data.set_active_user(None)
    except Exception:
        pass
    session.clear()
    return redirect('/login')

@server.route('/complete-profile')
def complete_profile_page():
    """Route untuk halaman complete profile"""
    return redirect('/')  # Dash akan handle rendering

# Layout utama
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='top-navigation'),
    html.Div(id='sub-navigation'),
    html.Div(id='page-content')
])
@app.callback(
    [Output('top-navigation', 'children'),
     Output('page-content', 'children'),
     Output('sub-navigation', 'children')],
    Input('url', 'pathname')
)
def display_page(pathname):
    print(f"🌐 Navigating to: {pathname}")
    try:
        print("🔎 Current session keys:", list(session.keys()))
    except Exception:
        pass
    
    # Update top navigation
    top_nav = create_top_navigation()
    
    # Check authentication
    is_authenticated = current_user.is_authenticated
    
    # Handle complete-profile route
    if pathname == '/complete-profile':
        # Try to recover oauth_user from query state first (fallback store), then session
        try:
            state = request.args.get('state')
        except Exception:
            state = None

        if state and state in OAUTH_STATE_STORE:
            # move oauth_user into session for the Dash rendering code
            try:
                session['oauth_user'] = OAUTH_STATE_STORE.pop(state)
                session.permanent = True
                print(f"🔁 Restored oauth_user from OAUTH_STATE_STORE for state {state}")
            except Exception:
                pass

        if session.get('oauth_user'):
            return top_nav, complete_profile_layout(), None
        else:
            return top_nav, login_layout(), None
    
    # Always allow access to login/signup pages
    if pathname in ['/login', '/signup']:
        return top_nav, login_layout() if pathname == '/login' else signup_layout(), None
    
    # Redirect to login if not authenticated
    if not is_authenticated:
        print("🔒 User not authenticated, redirecting to login")
        return top_nav, login_layout(), None
    
    # User is authenticated, show requested page
    sub_nav = None
    
    akuntansi_pages = [
        '/akuntansi-dasar', '/transaksi', '/kartu-persediaan', '/jurnal-umum',
        '/buku-besar', '/buku-besar-pembantu', '/neraca-saldo', '/aset-tetap'
    ]
    
    laporan_pages = [
        '/laporan-analisis', '/jurnal-penyesuaian', '/neraca-setelah-penyesuaian',
        '/laporan-laba-rugi', '/laporan-keuangan'
    ]
    
    if pathname in akuntansi_pages:
        sub_nav = create_akuntansi_sub_nav()
    elif pathname in laporan_pages:
        sub_nav = create_laporan_sub_nav()
    
    # Tentukan konten berdasarkan pathname
    if pathname == '/akuntansi-dasar':
        content = html.Div([
            html.H1("📊 Akuntansi Dasar", style={'textAlign': 'center', 'marginBottom': '30px'}),
            html.P("Pilih menu dari sub-navigation di atas", style={'textAlign': 'center'})
        ])
    elif pathname == '/laporan-analisis':
        content = html.Div([
            html.H1("📈 Laporan & Analisis", style={'textAlign': 'center', 'marginBottom': '30px'}),
            html.P("Pilih menu dari sub-navigation di atas", style={'textAlign': 'center'})
        ])
    elif pathname == '/transaksi':
        content = transaksi_layout()
    elif pathname == '/kartu-persediaan':
        content = kartu_persediaan_layout()
    elif pathname == '/jurnal-umum':
        content = jurnal_umum_layout()
    elif pathname == '/buku-besar':
        content = buku_besar_layout()
    elif pathname == '/buku-besar-pembantu':
        content = buku_besar_pembantu_layout()  # Pastikan ini yang dipanggil
    elif pathname == '/neraca-saldo':
        content = neraca_saldo_layout()
    elif pathname == '/aset-tetap':
        content = aset_tetap_layout()
    elif pathname == '/jurnal-penyesuaian':
        content = jurnal_penyesuaian_layout()
    elif pathname == '/neraca-setelah-penyesuaian':
        content = neraca_setelah_penyesuaian_layout()
    elif pathname == '/laporan-laba-rugi':
        content = laporan_laba_rugi_layout()
    elif pathname == '/laporan-keuangan':
        content = laporan_keuangan_layout()
    else:
        content = dashboard_layout()
        sub_nav = None
    
    return top_nav, content, sub_nav


# Callback untuk login
@app.callback(
    [Output('login-alert', 'children'),
     Output('login-identifier', 'value'),
     Output('login-password', 'value')],
    [Input('btn-login', 'n_clicks'),
     Input('btn-google-login', 'n_clicks')],
    [State('login-identifier', 'value'),
     State('login-password', 'value')],
    prevent_initial_call=True
)
def handle_login(n_login, n_google, identifier, password):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'btn-login' and n_login:
        if not identifier or not password:
            return create_alert("Harap isi username dan password", "error"), dash.no_update, dash.no_update
        
        # GUNAKAN FUNGSI authenticate_user YANG SUDAH KITA BUAT
        user, message = authenticate_user(identifier, password)
        
        if user:
            # GUNAKAN FUNGSI login_user YANG SUDAH KITA BUAT
            login_user(user, remember=True)
            return html.Div([
                html.P("✅ Login berhasil! Redirecting...", style={'color': COLORS['success']}),
                dcc.Location(href='/', id='redirect-dashboard', refresh=True)
            ], style={'textAlign': 'center'}), "", ""
        else:
            return create_alert(message, "error"), dash.no_update, ""
    
    elif button_id == 'btn-google-login' and n_google:
        # Untuk Google OAuth, kita perlu redirect ke Flask route
        return html.Div([
            html.P("Mengarahkan ke Google...", style={'color': COLORS['info']}),
            dcc.Location(id='google-redirect', href='/auth/login?action=login', refresh=True)
        ]), dash.no_update, dash.no_update
    
    return dash.no_update, dash.no_update, dash.no_update

# Callback untuk signup
@app.callback(
    [Output('signup-alert', 'children'),
     Output('signup-username', 'value'),
     Output('signup-email', 'value'),
     Output('signup-password', 'value'),
     Output('signup-confirm-password', 'value')],
    [Input('btn-signup', 'n_clicks'),
     Input('btn-google-signup', 'n_clicks')],
    [State('signup-username', 'value'),
     State('signup-email', 'value'),
     State('signup-password', 'value'),
     State('signup-confirm-password', 'value')],
    prevent_initial_call=True
)
def handle_signup(n_signup, n_google, username, email, password, confirm_password):
    ctx = dash.callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    
    if button_id == 'btn-signup' and n_signup:
        if not all([username, email, password, confirm_password]):
            return create_alert("Harap isi semua field", "error"), dash.no_update, dash.no_update, dash.no_update, dash.no_update
        
        if password != confirm_password:
            return create_alert("Password dan konfirmasi password tidak cocok", "error"), dash.no_update, dash.no_update, "", ""
        
        if len(password) < 6:
            return create_alert("Password minimal 6 karakter", "error"), dash.no_update, dash.no_update, "", ""
        
        # GUNAKAN FUNGSI create_user YANG SUDAH KITA BUAT
        user, message = create_user(username, email, password)
        
        if user:
            # Jangan auto-login setelah pendaftaran — minta user untuk login manual
            return html.Div([
                html.P("✅ Pendaftaran berhasil! Silakan login menggunakan akun Anda.", style={'color': COLORS['success']}),
                dcc.Location(href='/login', id='redirect-after-signup', refresh=True)
            ], style={'textAlign': 'center'}), "", "", "", ""
        else:
            return create_alert(message, "error"), dash.no_update, dash.no_update, "", ""
    
    elif button_id == 'btn-google-signup' and n_google:
        # Untuk Google OAuth, redirect ke Flask route
        return html.Div([
            html.P("Mengarahkan ke Google...", style={'color': COLORS['info']}),
            dcc.Location(id='google-signup-redirect', href='/auth/login?action=signup', refresh=True)
        ]), dash.no_update, dash.no_update, dash.no_update, dash.no_update
    
    return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

def create_alert(message, alert_type):
    colors = {
        'success': COLORS['success'],
        'error': COLORS['error'],
        'warning': COLORS['warning'],
        'info': COLORS['info']
    }
    
    return html.Div([
        html.P(message, style={
            'color': colors.get(alert_type, COLORS['gray_600']),
            'padding': '10px',
            'borderRadius': '5px',
            'backgroundColor': f"{colors.get(alert_type, COLORS['gray_200'])}20",
            'border': f"1px solid {colors.get(alert_type, COLORS['gray_300'])}"
        })
    ])

@app.callback(
    Output('pemasukan-jumlah-display', 'children'),
    [Input('pemasukan-harga-jual', 'value'),
     Input('pemasukan-qty', 'value')]
)
def hitung_jumlah_pemasukan(harga_jual, qty):
    """Menghitung jumlah otomatis dari harga jual × quantity"""
    if harga_jual and qty:
        jumlah = harga_jual * qty
        return html.Div([
            html.Strong(f"Total Jumlah: Rp {jumlah:,.0f}", 
                       style={'color': COLORS['success'], 'fontSize': '1.1rem'})
        ])
    return html.Div("Total Jumlah: Rp 0", style={'color': COLORS['gray_500']})

# Tambahkan ini di form pemasukan (setelah input quantity):
html.Div(id='pemasukan-jumlah-display', style={'marginBottom': '15px'})

@app.callback(
    [Output('pemasukan-harga-jual', 'value'),
     Output('pemasukan-qty', 'value'),
     Output('pemasukan-hpp', 'value'),
     Output('pemasukan-keterangan', 'value'),
     Output('pemasukan-ref', 'value')],
    Input('btn-tambah-pemasukan', 'n_clicks'),
    [State('selected-date', 'date'),
     State('pemasukan-jenis', 'value'),
     State('pemasukan-harga-jual', 'value'),
     State('pemasukan-qty', 'value'),
     State('pemasukan-hpp', 'value'),
     State('pemasukan-keterangan', 'value'),
     State('pemasukan-ref', 'value')],
    prevent_initial_call=True
)
def tambah_pemasukan(n_clicks, tanggal, jenis, harga_jual, qty, hpp, keterangan, ref):
    if n_clicks and n_clicks > 0 and harga_jual and qty and harga_jual > 0 and qty > 0:
        print(f"➕ Adding new pemasukan: {jenis} - {harga_jual} × {qty}")
        
        # HITUNG JUMLAH OTOMATIS
        jumlah = harga_jual * qty
        
        # Tentukan kode akun
        if jenis == 'tiket_masuk':
            kode_debit = KODE_AKUN['kas']['kode']
            kode_kredit = KODE_AKUN['pendapatan_tiket']['kode']
        elif jenis == 'penjualan_ikan':
            kode_debit = KODE_AKUN['kas']['kode']
            kode_kredit = KODE_AKUN['pendapatan']['kode']
        else:  # modal
            kode_debit = KODE_AKUN['kas']['kode']
            kode_kredit = KODE_AKUN['modal']['kode']
        
        # Buat transaksi baru
        transaksi_baru = {
            'tanggal': tanggal,
            'jenis': jenis,
            'jumlah': jumlah,  # Pakai jumlah yang dihitung otomatis
            'harga_jual': harga_jual,  # Simpan harga jual per unit
            'quantity': qty,
            'hpp': hpp if hpp else 0,
            'keterangan': keterangan if keterangan else f'Pendapatan {jenis}',
            'ref': ref if ref else f"REF-P-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'tipe': 'pemasukan',
            'kode_akun_debit': kode_debit,
            'kode_akun_kredit': kode_kredit
        }
        
        # Simpan ke memory (scoped ke user)
        transaksi_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_transaksi_pemasukan.append(transaksi_baru)
        
        # ✅ SIMPAN KE DATABASE
        try:
            sibal_data.save_all_data()
            print(f"✅ Pemasukan saved to database: {jenis} - {qty} × {harga_jual} = Rp{jumlah:,}")
        except Exception as e:
            print(f"❌ Failed to save pemasukan: {e}")
        
        return '', '', '', '', ''
    
    return dash.no_update

def tambah_pengeluaran(n_clicks, tanggal, jenis, kode_barang, hpp, qty, metode, supplier, keterangan, ref):
    if n_clicks and n_clicks > 0 and hpp and qty and hpp > 0 and qty > 0 and jenis:
        print(f"➖ Adding new pengeluaran: {jenis} - {hpp} × {qty}")
        
        # HITUNG JUMLAH OTOMATIS
        jumlah = hpp * qty
        
        # Default values
        metode = metode if metode else 'tunai'
        supplier = supplier if supplier else ''
        
        # Tentukan kode akun
        akun_debit_mapping = {
            'pembelian_persediaan': KODE_AKUN['persediaan']['kode'],
            'beban_gaji': KODE_AKUN['beban_gaji']['kode'],
            'beban_listrik': KODE_AKUN['beban_listrik']['kode'],
            'beban_penyusutan_bangunan': KODE_AKUN['beban_penyusutan_bangunan']['kode'],
            'beban_penyusutan_kendaraan': KODE_AKUN['beban_penyusutan_kendaraan']['kode'],
            'beban_penyusutan_peralatan': KODE_AKUN['beban_penyusutan_peralatan']['kode'],
            'beban_lainnya': KODE_AKUN['beban_lainnya']['kode']
        }
        
        kode_akun_debit = akun_debit_mapping.get(jenis, KODE_AKUN['beban_lainnya']['kode'])
        kode_akun_kredit = KODE_AKUN['kas']['kode'] if metode == 'tunai' else KODE_AKUN['utang']['kode']
        
        # ✅ UPDATE PERSEDIAAN JIKA PEMBELIAN PERSEDIAAN
        if jenis == 'pembelian_persediaan' and kode_barang:
            success = update_persediaan_pembelian(
                kode_barang, qty, hpp, tanggal, keterangan, supplier
            )
            if success:
                print(f"✅ Persediaan updated for pembelian: {kode_barang}")
            else:
                print(f"❌ Failed to update persediaan for pembelian")
        
        # ✅ TAMBAHKAN SUPPLIER KE DAFTAR JIKA KREDIT
        if metode == 'kredit' and supplier and supplier not in sibal_data.suppliers:
            sibal_data.suppliers.append(supplier)
            print(f"✅ Supplier added: {supplier}")
        
        # Buat transaksi baru
        transaksi_baru = {
            'tanggal': tanggal,
            'jenis': jenis,
            'kode_barang': kode_barang if jenis == 'pembelian_persediaan' else '',
            'jumlah': jumlah,
            'hpp': hpp,
            'quantity': qty,
            'metode_bayar': metode,
            'supplier': supplier if metode == 'kredit' else '',
            'keterangan': keterangan if keterangan else f'Pengeluaran - {jenis}',
            'ref': ref if ref else f"REF-K-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'tipe': 'pengeluaran',
            'kode_akun_debit': kode_akun_debit,
            'kode_akun_kredit': kode_akun_kredit
        }
        
        # Simpan ke memory (scoped ke user)
        transaksi_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_transaksi_pengeluaran.append(transaksi_baru)
        
        # ✅ SIMPAN KE DATABASE
        try:
            sibal_data.save_all_data()
            print(f"✅ Pengeluaran saved to database: {jenis} - {qty} × {hpp} = Rp{jumlah:,}")
        except Exception as e:
            print(f"❌ Failed to save pengeluaran: {e}")
        
        return '', '', '', '', ''
    
    return dash.no_update

@app.callback(
    Output('pengeluaran-jumlah-display', 'children'),
    [Input('pengeluaran-hpp', 'value'),
     Input('pengeluaran-qty', 'value')]
)
def hitung_jumlah_pengeluaran(hpp, qty):
    """Menghitung jumlah otomatis dari HPP × quantity"""
    if hpp and qty:
        jumlah = hpp * qty
        return html.Div([
            html.Strong(f"Total Jumlah: Rp {jumlah:,.0f}", 
                       style={'color': COLORS['error'], 'fontSize': '1.1rem'})
        ])
    return html.Div("Total Jumlah: Rp 0", style={'color': COLORS['gray_500']})

# Tambahkan ini di form pengeluaran (setelah input quantity):
html.Div(id='pengeluaran-jumlah-display', style={'marginBottom': '15px'})

@app.callback(
    [Output('pengeluaran-hpp', 'value'),
     Output('pengeluaran-qty', 'value'),
     Output('pengeluaran-keterangan', 'value'),
     Output('pengeluaran-supplier', 'value'),
     Output('pengeluaran-ref', 'value')],
    Input('btn-tambah-pengeluaran', 'n_clicks'),  # PASTIKAN ID INI ADA DI LAYOUT
    [State('selected-date', 'date'),
     State('pengeluaran-jenis', 'value'),
     State('pengeluaran-barang', 'value'),
     State('pengeluaran-hpp', 'value'),
     State('pengeluaran-qty', 'value'),
     State('pengeluaran-metode', 'value'),
     State('pengeluaran-supplier', 'value'),
     State('pengeluaran-keterangan', 'value'),
     State('pengeluaran-ref', 'value')],
    prevent_initial_call=True
)
def tambah_pengeluaran(n_clicks, tanggal, jenis, kode_barang, hpp, qty, metode, supplier, keterangan, ref):
    if n_clicks and n_clicks > 0 and hpp and qty and hpp > 0 and qty > 0 and jenis:
        print(f"➖ Adding new pengeluaran: {jenis} - {hpp} × {qty}")
        
        # HITUNG JUMLAH OTOMATIS
        jumlah = hpp * qty
        
        # Default values
        metode = metode if metode else 'tunai'
        
        # Tentukan kode akun
        akun_debit_mapping = {
            'pembelian_persediaan': {'nama': 'Persediaan Barang Dagang', 'kode': KODE_AKUN['persediaan']['kode']},
            'beban_gaji': {'nama': 'Beban Gaji', 'kode': KODE_AKUN['beban_gaji']['kode']},
            'beban_listrik': {'nama': 'Beban Listrik', 'kode': KODE_AKUN['beban_listrik']['kode']},
            'beban_penyusutan_bangunan': {'nama': 'Beban Depresiasi Bangunan', 'kode': KODE_AKUN['beban_penyusutan_bangunan']['kode']},
            'beban_penyusutan_kendaraan': {'nama': 'Beban Depresiasi Kendaraan', 'kode': KODE_AKUN['beban_penyusutan_kendaraan']['kode']},
            'beban_penyusutan_peralatan': {'nama': 'Beban Depresiasi Peralatan', 'kode': KODE_AKUN['beban_penyusutan_peralatan']['kode']},
            'beban_lainnya': {'nama': 'Beban Lainnya', 'kode': KODE_AKUN['beban_lainnya']['kode']}
        }
        
        kode_akun_debit = akun_debit_mapping.get(jenis, {'nama': 'Beban Lainnya', 'kode': KODE_AKUN['beban_lainnya']['kode']})
        kode_akun_kredit = KODE_AKUN['kas']['kode'] if metode == 'tunai' else KODE_AKUN['utang']['kode']
        
        # ✅ UPDATE PERSEDIAAN JIKA PEMBELIAN PERSEDIAAN
        if jenis == 'pembelian_persediaan' and kode_barang:
            print(f"🔄 Memanggil update_persediaan_pembelian: {kode_barang}, {qty}, {hpp}")
            success = update_persediaan_pembelian(
                kode_barang, qty, hpp, tanggal, keterangan, supplier
            )
            if success:
                print(f"✅ Persediaan updated for pembelian: {kode_barang}")
            else:
                print(f"❌ Failed to update persediaan for pembelian")
        else:
            print(f"ℹ️  Bukan pembelian persediaan, skip update persediaan")
        
        # ✅ TAMBAHKAN SUPPLIER KE DAFTAR JIKA KREDIT
        if metode == 'kredit' and supplier and supplier not in sibal_data.suppliers:
            sibal_data.suppliers.append(supplier)
            print(f"✅ Supplier added: {supplier}")
            
            # Inisialisasi buku besar pembantu untuk supplier baru
            if supplier not in sibal_data.buku_besar_pembantu:
                sibal_data.buku_besar_pembantu[supplier] = []
        
        # Buat transaksi baru
        transaksi_baru = {
            'tanggal': tanggal,
            'jenis': jenis,
            'kode_barang': kode_barang if jenis == 'pembelian_persediaan' else '',
            'jumlah': jumlah,
            'hpp': hpp,
            'quantity': qty,
            'metode_bayar': metode,
            'supplier': supplier if metode == 'kredit' else '',
            'keterangan': keterangan if keterangan else f'Pengeluaran - {jenis}',
            'ref': ref if ref else f"REF-K-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            'tipe': 'pengeluaran',
            'kode_akun_debit': kode_akun_debit['kode'],
            'kode_akun_kredit': kode_akun_kredit
        }
        
        # Simpan ke memory (scoped ke user)
        transaksi_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_transaksi_pengeluaran.append(transaksi_baru)
        
        # ✅ TAMBAHKAN KE BUKU BESAR PEMBANTU JIKA KREDIT
        if metode == 'kredit' and supplier:
            if supplier not in sibal_data.buku_besar_pembantu:
                sibal_data.buku_besar_pembantu[supplier] = []
            
            # Hitung saldo terakhir
            saldo_terakhir = 0
            if sibal_data.buku_besar_pembantu[supplier]:
                saldo_terakhir = sibal_data.buku_besar_pembantu[supplier][-1]['saldo']
            
            saldo_baru = saldo_terakhir + jumlah
            
            # Tambahkan transaksi ke buku besar pembantu
            sibal_data.buku_besar_pembantu[supplier].append({
                'tanggal': tanggal,
                'keterangan': f"{jenis} - {keterangan}",
                'debit': 0,
                'kredit': jumlah,
                'saldo': saldo_baru
            })
            print(f"✅ Added to buku besar pembantu: {supplier} - Rp {jumlah:,}")
        
        # ✅ SIMPAN KE DATABASE
        try:
            sibal_data.save_all_data()
            print(f"✅ Pengeluaran saved to database: {jenis} - {qty} × {hpp} = Rp{jumlah:,}")
        except Exception as e:
            print(f"❌ Failed to save pengeluaran: {e}")
        
        return '', '', '', '', ''
    
    return dash.no_update

@app.callback(
    Output('daftar-pemasukan', 'children', allow_duplicate=True),
    Input('btn-hapus-pemasukan', 'n_clicks'),
    [State('selected-date', 'date'),
     State({'type': 'pemasukan-check', 'index': dash.ALL}, 'value')],
    prevent_initial_call=True
)
def hapus_pemasukan(n_clicks, tanggal, checklists):
    if n_clicks and n_clicks > 0:
        transaksi_hari_ini = [t for t in sibal_data.transaksi_pemasukan if t['tanggal'] == tanggal]
        indices_to_delete = []
        
        for i, checked in enumerate(checklists):
            if checked and 'selected' in checked and i < len(transaksi_hari_ini):
                indices_to_delete.append(i)
        
        if indices_to_delete:
            # Hapus dari belakang untuk menghindari index error
            deleted_count = 0
            for i in sorted(indices_to_delete, reverse=True):
                if i < len(transaksi_hari_ini):
                    transaksi_to_delete = transaksi_hari_ini[i]
                    sibal_data.transaksi_pemasukan.remove(transaksi_to_delete)
                    deleted_count += 1
            
            sibal_data.save_all_data()
            return update_daftar_transaksi(tanggal, None, None, None, None)[0]
        
    return dash.no_update

@app.callback(
    Output('daftar-pengeluaran', 'children', allow_duplicate=True),
    Input('btn-hapus-pengeluaran', 'n_clicks'),
    [State('selected-date', 'date'),
     State({'type': 'pengeluaran-check', 'index': dash.ALL}, 'value')],
    prevent_initial_call=True
)
def hapus_pengeluaran(n_clicks, tanggal, checklists):
    if n_clicks and n_clicks > 0:
        transaksi_hari_ini = [t for t in sibal_data.transaksi_pengeluaran if t['tanggal'] == tanggal]
        indices_to_delete = []
        
        for i, checked in enumerate(checklists):
            if checked and 'selected' in checked and i < len(transaksi_hari_ini):
                indices_to_delete.append(i)
        
        if indices_to_delete:
            # Hapus dari belakang untuk menghindari index error
            deleted_count = 0
            for i in sorted(indices_to_delete, reverse=True):
                if i < len(transaksi_hari_ini):
                    transaksi_to_delete = transaksi_hari_ini[i]
                    sibal_data.transaksi_pengeluaran.remove(transaksi_to_delete)
                    deleted_count += 1
            
            sibal_data.save_all_data()
            return update_daftar_transaksi(tanggal, None, None, None, None)[1]
    
    return dash.no_update

@app.callback(
    [Output('daftar-pemasukan', 'children'),
     Output('daftar-pengeluaran', 'children')],
    [Input('selected-date', 'date'),
     Input('btn-tambah-pemasukan', 'n_clicks'),
     Input('btn-tambah-pengeluaran', 'n_clicks'),
     Input('btn-hapus-pemasukan', 'n_clicks'),
     Input('btn-hapus-pengeluaran', 'n_clicks')]
)
def update_daftar_transaksi(tanggal, n_pemasukan, n_pengeluaran, n_hapus_pemasukan, n_hapus_pengeluaran):
    """Update daftar transaksi untuk tanggal terpilih"""
    
    # Tampilkan transaksi pemasukan untuk tanggal terpilih
    transaksi_pemasukan_hari_ini = [t for t in sibal_data.transaksi_pemasukan if t['tanggal'] == tanggal]
    
    if transaksi_pemasukan_hari_ini:
        items_pemasukan = []
        for i, trans in enumerate(transaksi_pemasukan_hari_ini):
            harga_jual = trans.get('harga_jual', 0)
            quantity = trans.get('quantity', 0)
            jumlah = trans.get('jumlah', 0)
            
            items_pemasukan.append(html.Div([
                dcc.Checklist(
                    id={'type': 'pemasukan-check', 'index': i},
                    options=[{'label': '', 'value': 'selected'}],
                    value=[],
                    style={'display': 'inline-block', 'marginRight': '10px'}
                ),
                html.Strong(f"{trans.get('jenis', 'N/A').replace('_', ' ').title()}"),
                html.Br(),
                html.Small(f"Qty: {quantity} × Rp {harga_jual:,} = Rp {jumlah:,}"),
                html.Br(),
                html.Small(f"Ref: {trans.get('ref', '-')} | {trans.get('keterangan', '')}"),
                html.Hr(style={'margin': '5px 0'})
            ]))
        daftar_pemasukan = items_pemasukan
    else:
        daftar_pemasukan = html.P("Belum ada transaksi pendapatan untuk tanggal ini", style={'color': '#6c757d'})
    
    # Tampilkan transaksi pengeluaran untuk tanggal terpilih
    transaksi_pengeluaran_hari_ini = [t for t in sibal_data.transaksi_pengeluaran if t['tanggal'] == tanggal]
    
    if transaksi_pengeluaran_hari_ini:
        items_pengeluaran = []
        for i, trans in enumerate(transaksi_pengeluaran_hari_ini):
            hpp = trans.get('hpp', 0)
            quantity = trans.get('quantity', 0)
            jumlah = trans.get('jumlah', 0)
            jenis_label = trans['jenis'].replace('_', ' ').title()
            metode = trans.get('metode_bayar', 'tunai')
            
            items_pengeluaran.append(html.Div([
                dcc.Checklist(
                    id={'type': 'pengeluaran-check', 'index': i},
                    options=[{'label': '', 'value': 'selected'}],
                    value=[],
                    style={'display': 'inline-block', 'marginRight': '10px'}
                ),
                html.Strong(f"{jenis_label}"),
                html.Br(),
                html.Small(f"Qty: {quantity} × Rp {hpp:,} = Rp {jumlah:,}"),
                html.Br(),
                html.Small(f"{trans.get('keterangan', 'N/A')} | Metode: {metode.title()}"),
                html.Hr(style={'margin': '5px 0'})
            ]))
        daftar_pengeluaran = items_pengeluaran
    else:
        daftar_pengeluaran = html.P("Belum ada transaksi pengeluaran untuk tanggal ini", style={'color': '#6c757d'})
    
    return daftar_pemasukan, daftar_pengeluaran

def update_persediaan_pembelian(kode_barang, qty, harga, tanggal, keterangan, supplier=""):
    """Update kartu persediaan saat pembelian - sistem sederhana"""
    try:
        # Cari barang di master
        barang = next((item for item in sibal_data.master_persediaan if item['kode'] == kode_barang), None)
        if not barang:
            print(f"❌ Barang dengan kode {kode_barang} tidak ditemukan")
            return False
        
        # Hitung saldo terakhir
        transaksi_sebelumnya = [t for t in sibal_data.kartu_persediaan if t['kode_barang'] == kode_barang]
        
        saldo_qty_sebelumnya = 0
        saldo_total_sebelumnya = 0
        
        if transaksi_sebelumnya:
            last_trans = transaksi_sebelumnya[-1]
            saldo_qty_sebelumnya = last_trans['saldo_qty']
            saldo_total_sebelumnya = last_trans['saldo_total']
        
        # Hitung saldo baru
        saldo_qty_baru = saldo_qty_sebelumnya + qty
        saldo_total_baru = saldo_total_sebelumnya + (qty * harga)
        saldo_harga_baru = saldo_total_baru / saldo_qty_baru if saldo_qty_baru > 0 else 0
        
        print(f"📊 PEMBELIAN: {saldo_qty_sebelumnya} + {qty} = {saldo_qty_baru} kg")
        print(f"📊 NILAI: Rp{saldo_total_sebelumnya:,} + Rp{qty * harga:,} = Rp{saldo_total_baru:,}")
        
        # Buat entri baru
        entri_baru = {
            'tanggal': tanggal,
            'kode_barang': kode_barang,
            'nama_barang': barang['nama'],
            'masuk_qty': qty,
            'masuk_harga': harga,
            'masuk_total': qty * harga,
            'keluar_qty': 0,
            'keluar_harga': 0,
            'keluar_total': 0,
            'saldo_qty': saldo_qty_baru,
            'saldo_harga': saldo_harga_baru,
            'saldo_total': saldo_total_baru,
            'keterangan': f'Pembelian - {keterangan}' + (f' - {supplier}' if supplier else '')
        }
        
        entri_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_kartu_persediaan.append(entri_baru)
        print(f"✅ BERHASIL: {kode_barang} +{qty}kg, Saldo: {saldo_qty_baru}kg @ Rp{saldo_harga_baru:,.0f}")
        return True
        
    except Exception as e:
        print(f"❌ GAGAL: {e}")
        return False

def update_persediaan_penjualan(kode_barang, qty, tanggal, keterangan):
    """Update kartu persediaan saat penjualan - sistem sederhana"""
    try:
        # Cari barang di master
        barang = next((item for item in sibal_data.master_persediaan if item['kode'] == kode_barang), None)
        if not barang:
            print(f"❌ Barang dengan kode {kode_barang} tidak ditemukan")
            return False, 0
        
        # Hitung saldo terakhir
        transaksi_sebelumnya = [t for t in sibal_data.kartu_persediaan if t['kode_barang'] == kode_barang]
        
        if not transaksi_sebelumnya:
            print(f"❌ Tidak ada stok untuk {kode_barang}")
            return False, 0
            
        last_trans = transaksi_sebelumnya[-1]
        saldo_qty_sebelumnya = last_trans['saldo_qty']
        saldo_total_sebelumnya = last_trans['saldo_total']
        saldo_harga_sebelumnya = last_trans['saldo_harga']
        
        # Cek stok cukup
        if saldo_qty_sebelumnya < qty:
            print(f"❌ Stok tidak cukup: {saldo_qty_sebelumnya} < {qty}")
            return False, 0
        
        # Hitung HPP
        hpp_total = qty * saldo_harga_sebelumnya
        
        # Hitung saldo baru
        saldo_qty_baru = saldo_qty_sebelumnya - qty
        saldo_total_baru = saldo_total_sebelumnya - hpp_total
        saldo_harga_baru = saldo_total_baru / saldo_qty_baru if saldo_qty_baru > 0 else 0
        
        print(f"📊 PENJUALAN: {saldo_qty_sebelumnya} - {qty} = {saldo_qty_baru} kg")
        print(f"📊 NILAI: Rp{saldo_total_sebelumnya:,} - Rp{hpp_total:,} = Rp{saldo_total_baru:,}")
        
        # Buat entri baru
        entri_baru = {
            'tanggal': tanggal,
            'kode_barang': kode_barang,
            'nama_barang': barang['nama'],
            'masuk_qty': 0,
            'masuk_harga': 0,
            'masuk_total': 0,
            'keluar_qty': qty,
            'keluar_harga': saldo_harga_sebelumnya,
            'keluar_total': hpp_total,
            'saldo_qty': saldo_qty_baru,
            'saldo_harga': saldo_harga_baru,
            'saldo_total': saldo_total_baru,
            'keterangan': f'Penjualan - {keterangan}'
        }
        
        entri_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_kartu_persediaan.append(entri_baru)
        print(f"✅ BERHASIL: {kode_barang} -{qty}kg, HPP: Rp{hpp_total:,}, Saldo: {saldo_qty_baru}kg")
        return True, hpp_total
        
    except Exception as e:
        print(f"❌ GAGAL: {e}")
        return False, 0
    
def hitung_ulang_semua_saldo():
    """Hitung ulang semua saldo dari transaksi pertama - untuk memperbaiki data yang rusak"""
    print("🔄 MENGHITUNG ULANG SEMUA SALDO...")
    
    # Kelompokkan berdasarkan kode barang
    transaksi_per_barang = {}
    for item in sibal_data.kartu_persediaan:
        kode = item['kode_barang']
        if kode not in transaksi_per_barang:
            transaksi_per_barang[kode] = []
        transaksi_per_barang[kode].append(item)
    
    # Urutkan setiap barang berdasarkan tanggal
    for kode_barang in transaksi_per_barang:
        transaksi_per_barang[kode_barang].sort(key=lambda x: x['tanggal'])
    
    # Hapus semua data kartu persediaan
    sibal_data.kartu_persediaan.clear()
    
    # Hitung ulang dari transaksi pertama
    for kode_barang, transaksi_list in transaksi_per_barang.items():
        saldo_qty = 0
        saldo_total = 0
        
        for i, transaksi in enumerate(transaksi_list):
            # Simpan data asli masuk/keluar
            masuk_qty = transaksi['masuk_qty']
            masuk_harga = transaksi['masuk_harga'] 
            masuk_total = transaksi['masuk_total']
            keluar_qty = transaksi['keluar_qty']
            keluar_harga = transaksi['keluar_harga']
            keluar_total = transaksi['keluar_total']
            
            # Update saldo
            saldo_qty += masuk_qty - keluar_qty
            saldo_total += masuk_total - keluar_total
            saldo_harga = saldo_total / saldo_qty if saldo_qty > 0 else 0
            
            # Buat entri baru dengan saldo yang benar
            entri_baru = {
                'tanggal': transaksi['tanggal'],
                'kode_barang': kode_barang,
                'nama_barang': transaksi['nama_barang'],
                'masuk_qty': masuk_qty,
                'masuk_harga': masuk_harga,
                'masuk_total': masuk_total,
                'keluar_qty': keluar_qty,
                'keluar_harga': keluar_harga,
                'keluar_total': keluar_total,
                'saldo_qty': saldo_qty,
                'saldo_harga': saldo_harga,
                'saldo_total': saldo_total,
                'keterangan': transaksi['keterangan']
            }
            
            entri_baru['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
            sibal_data._all_kartu_persediaan.append(entri_baru)
            print(f"🔁 {kode_barang} Transaksi {i+1}: Saldo = {saldo_qty}kg @ Rp{saldo_harga:,.0f}")
    
    print("✅ SELESAI menghitung ulang semua saldo")

# Callback untuk menampilkan jurnal umum dengan format yang rapi
@app.callback(
    [Output('tabel-jurnal-umum', 'children'),
     Output('rekapitulasi-jurnal', 'children')],
    Input('btn-refresh-jurnal', 'n_clicks')
)
def update_jurnal_umum(n_clicks):
    # Tampilkan jurnal umum dalam format yang rapi
    if sibal_data.jurnal_umum:
        jurnal_entries = []
        
        for jurnal in sibal_data.jurnal_umum:
            # Entry untuk debit
            jurnal_entries.append(html.Div([
                html.Span(jurnal['tanggal'], style={'fontWeight': 'bold', 'minWidth': '100px', 'display': 'inline-block'}),
                html.Span(jurnal['akun_debit'], style={'minWidth': '200px', 'display': 'inline-block'}),
                html.Span("", style={'minWidth': '100px', 'display': 'inline-block'}),
                html.Span(format_rupiah(jurnal['jumlah_debit']), 
                         style={'textAlign': 'right', 'minWidth': '150px', 'display': 'inline-block', 'paddingLeft': '20px'}),
                html.Span("", style={'minWidth': '150px', 'display': 'inline-block'})
            ], className="jurnal-entry"))
            
            # Entry untuk kredit (dengan indentasi)
            jurnal_entries.append(html.Div([
                html.Span("", style={'minWidth': '100px', 'display': 'inline-block'}),
                html.Span(jurnal['akun_kredit'], 
                         style={'minWidth': '200px', 'display': 'inline-block', 'paddingLeft': '40px', 'color': COLORS['secondary']}),
                html.Span("", style={'minWidth': '100px', 'display': 'inline-block'}),
                html.Span("", style={'minWidth': '150px', 'display': 'inline-block'}),
                html.Span(format_rupiah(jurnal['jumlah_kredit']), 
                         style={'textAlign': 'right', 'minWidth': '150px', 'display': 'inline-block', 'color': COLORS['secondary']})
            ], className="jurnal-entry jurnal-kredit"))
            
            # Tambahkan spasi antara jurnal
            jurnal_entries.append(html.Div(style={'height': '10px'}))
        
        tabel_jurnal = html.Div(jurnal_entries)
        
        # Buat rekapitulasi jurnal
        rekapitulasi_data = {}
        for jurnal in sibal_data.jurnal_umum:
            # Debit
            akun_debit = f"{jurnal['kode_akun_debit']} - {jurnal['akun_debit']}"
            if akun_debit not in rekapitulasi_data:
                rekapitulasi_data[akun_debit] = {'debit': 0, 'kredit': 0}
            rekapitulasi_data[akun_debit]['debit'] += jurnal['jumlah_debit']
            
            # Kredit
            akun_kredit = f"{jurnal['kode_akun_kredit']} - {jurnal['akun_kredit']}"
            if akun_kredit not in rekapitulasi_data:
                rekapitulasi_data[akun_kredit] = {'debit': 0, 'kredit': 0}
            rekapitulasi_data[akun_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Buat tabel rekapitulasi
        header_rekapitulasi = html.Tr([
            html.Th("Akun Debit"),
            html.Th("Kode"),
            html.Th("Debit"),
            html.Th("Akun Kredit"),
            html.Th("Kode"),
            html.Th("Kredit")
        ])
        
        rows_rekapitulasi = []
        total_debit = 0
        total_kredit = 0
        
        # Gabungkan data debit dan kredit dalam satu baris
        akun_list = list(rekapitulasi_data.keys())
        max_rows = max(len([akun for akun in akun_list if rekapitulasi_data[akun]['debit'] > 0]),
                      len([akun for akun in akun_list if rekapitulasi_data[akun]['kredit'] > 0]))
        
        debit_akun = [akun for akun in akun_list if rekapitulasi_data[akun]['debit'] > 0]
        kredit_akun = [akun for akun in akun_list if rekapitulasi_data[akun]['kredit'] > 0]
        
        for i in range(max_rows):
            debit_row = debit_akun[i] if i < len(debit_akun) else ""
            kredit_row = kredit_akun[i] if i < len(kredit_akun) else ""
            
            debit_kode = debit_row.split(' - ')[0] if debit_row else ""
            debit_nama = debit_row.split(' - ')[1] if debit_row else ""
            debit_jumlah = rekapitulasi_data[debit_row]['debit'] if debit_row else 0
            
            kredit_kode = kredit_row.split(' - ')[0] if kredit_row else ""
            kredit_nama = kredit_row.split(' - ')[1] if kredit_row else ""
            kredit_jumlah = rekapitulasi_data[kredit_row]['kredit'] if kredit_row else 0
            
            total_debit += debit_jumlah
            total_kredit += kredit_jumlah
            
            rows_rekapitulasi.append(html.Tr([
                html.Td(debit_nama),
                html.Td(debit_kode),
                html.Td(format_rupiah(debit_jumlah) if debit_jumlah > 0 else ""),
                html.Td(kredit_nama),
                html.Td(kredit_kode),
                html.Td(format_rupiah(kredit_jumlah) if kredit_jumlah > 0 else "")
            ]))
        
        # Baris total
        rows_rekapitulasi.append(html.Tr([
            html.Td("TOTAL", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
            html.Td(format_rupiah(total_debit), style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
            html.Td("TOTAL", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
            html.Td(format_rupiah(total_kredit), style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
        ]))
        
        tabel_rekapitulasi = html.Table(
            [header_rekapitulasi] + rows_rekapitulasi,
            className="modern-table"
        )
        
        return tabel_jurnal, tabel_rekapitulasi
    else:
        return html.P("Belum ada data jurnal umum", style={'color': '#6c757d'}), html.P("Belum ada data rekapitulasi", style={'color': '#6c757d'})

@app.callback(
    [Output('summary-akumulasi', 'children'),
     Output('selected-date', 'date')],
    [Input('btn-akumulasi-pemasukan', 'n_clicks'),
     Input('btn-akumulasi-pengeluaran', 'n_clicks')],
    [State('selected-date', 'date')],
    prevent_initial_call=True
)
def akumulasi_ke_jurnal(n_pemasukan, n_pengeluaran, tanggal):
    ctx = dash.callback_context
    if not ctx.triggered:
        return html.P("Klik tombol akumulasi untuk mencatat transaksi ke jurnal umum"), dash.no_update
    
    button_id = ctx.triggered[0]['prop_id'].split('.')[0]
    jurnal_created = []
    
    print(f"🔧 DEBUG: Processing accumulation for {button_id} on date {tanggal}")
    
    # Hitung tanggal berikutnya
    if tanggal:
        current_date = datetime.strptime(tanggal, '%Y-%m-%d')
        next_date = current_date + timedelta(days=1)
        next_date_str = next_date.strftime('%Y-%m-%d')
    else:
        next_date_str = datetime.now().date().isoformat()
    
    if button_id == 'btn-akumulasi-pemasukan' and n_pemasukan:
        # Akumulasi pemasukan
        transaksi_pemasukan = [t for t in sibal_data.transaksi_pemasukan if t['tanggal'] == tanggal]
        
        print(f"📊 DEBUG: Found {len(transaksi_pemasukan)} pemasukan transactions")
        
        for trans in transaksi_pemasukan:
            print(f"🔍 DEBUG: Processing pemasukan - {trans['jenis']} - Rp {trans['jumlah']:,}")
            
            if trans['jenis'] == 'tiket_masuk':
                jurnal = {
                    'tanggal': tanggal,
                    'keterangan': f"{trans['keterangan']}",
                    'ref': trans.get('ref', ''),
                    'akun_debit': 'Kas',
                    'kode_akun_debit': KODE_AKUN['kas']['kode'],
                    'jumlah_debit': trans['jumlah'],
                    'akun_kredit': 'Pendapatan Tiket',
                    'kode_akun_kredit': KODE_AKUN['pendapatan_tiket']['kode'],
                    'jumlah_kredit': trans['jumlah']
                }
                jurnal['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
                sibal_data._all_jurnal_umum.append(jurnal)
                jurnal_created.append(jurnal)
                print(f"✅ Created jurnal for tiket masuk")
            # Dalam callback akumulasi_ke_jurnal, perbaiki bagian penjualan ikan:
            elif trans['jenis'] == 'penjualan_ikan':
                # Jurnal penjualan
                jurnal_penjualan = {
                    'tanggal': tanggal,
                    'keterangan': f"{trans['keterangan']}",
                    'ref': trans.get('ref', ''),
                    'akun_debit': 'Kas',
                    'kode_akun_debit': KODE_AKUN['kas']['kode'],
                    'jumlah_debit': trans['jumlah'],
                    'akun_kredit': 'Penjualan',
                    'kode_akun_kredit': KODE_AKUN['pendapatan']['kode'],
                    'jumlah_kredit': trans['jumlah']
                }
                jurnal_penjualan['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
                sibal_data._all_jurnal_umum.append(jurnal_penjualan)
                jurnal_created.append(jurnal_penjualan)
                print(f"✅ Created jurnal for penjualan")
                
                # Jurnal HPP dan pengurangan persediaan
                kode_barang = 'IK001'  # Ikan Bawal Segar
                qty_terjual = trans.get('quantity', 0)
                
                print(f"🔧 DEBUG: Attempting to reduce inventory - {qty_terjual}kg")
                
                if qty_terjual > 0:
                    # Kurangi persediaan fisik dengan fungsi yang sudah diperbaiki
                    success, total_hpp = update_persediaan_penjualan(kode_barang, qty_terjual, tanggal, trans['keterangan'])
                    
                    if success:
                        print(f"✅ Successfully reduced inventory, HPP: Rp{total_hpp:,}")
                        
                        # Buat jurnal HPP
                        jurnal_hpp = {
                            'tanggal': tanggal,
                            'keterangan': f"HPP - {trans['keterangan']}",
                            'ref': trans.get('ref', '') + '-HPP',
                            'akun_debit': 'Harga Pokok Produksi',
                            'kode_akun_debit': KODE_AKUN['hpp']['kode'],
                            'jumlah_debit': total_hpp,
                            'akun_kredit': 'Persediaan Barang Dagang',
                            'kode_akun_kredit': KODE_AKUN['persediaan']['kode'],
                            'jumlah_kredit': total_hpp
                        }
                        jurnal_hpp['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
                        sibal_data._all_jurnal_umum.append(jurnal_hpp)
                        jurnal_created.append(jurnal_hpp)
                        print(f"✅ Created HPP jurnal: Rp {total_hpp:,}")
                    else:
                        print(f"❌ Failed to reduce inventory")
            
            elif trans['jenis'] == 'modal':
                jurnal = {
                    'tanggal': tanggal,
                    'keterangan': f"{trans['keterangan']}",
                    'ref': trans.get('ref', ''),
                    'akun_debit': 'Kas',
                    'kode_akun_debit': KODE_AKUN['kas']['kode'],
                    'jumlah_debit': trans['jumlah'],
                    'akun_kredit': 'Modal',
                    'kode_akun_kredit': KODE_AKUN['modal']['kode'],
                    'jumlah_kredit': trans['jumlah']
                }
                jurnal['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
                sibal_data._all_jurnal_umum.append(jurnal)
                jurnal_created.append(jurnal)
                print(f"✅ Created jurnal for modal")
        
        # Simpan data setelah semua jurnal dibuat
        if jurnal_created:
            sibal_data.save_all_data()
            return html.Div([
                html.H4("✅ Akumulasi Pemasukan Berhasil!", style={'color': '#28a745'}),
                html.P(f"{len(jurnal_created)} jurnal telah dibuat untuk transaksi pemasukan tanggal {tanggal}"),
                html.P(f"Tanggal otomatis berubah ke {next_date_str}", style={'fontWeight': 'bold', 'color': '#007bff'})
            ]), next_date_str
        else:
            return html.Div([
                html.H4("❌ Tidak ada transaksi pemasukan", style={'color': '#dc3545'}),
                html.P(f"Tidak ada transaksi pemasukan untuk tanggal {tanggal}"),
                html.P("Silakan buat transaksi pemasukan terlebih dahulu")
            ]), dash.no_update
    
    elif button_id == 'btn-akumulasi-pengeluaran' and n_pengeluaran:
        # Akumulasi pengeluaran
        transaksi_pengeluaran = [t for t in sibal_data.transaksi_pengeluaran if t['tanggal'] == tanggal]
        
        print(f"📊 DEBUG: Found {len(transaksi_pengeluaran)} pengeluaran transactions")
        
        for trans in transaksi_pengeluaran:
            print(f"🔍 DEBUG: Processing pengeluaran - {trans['jenis']} - Rp {trans['jumlah']:,}")
            
            # Tentukan akun debit berdasarkan jenis pengeluaran
            akun_debit_mapping = {
                'pembelian_persediaan': {'nama': 'Persediaan Barang Dagang', 'kode': KODE_AKUN['persediaan']['kode']},
                'beban_gaji': {'nama': 'Beban Gaji', 'kode': KODE_AKUN['beban_gaji']['kode']},
                'beban_listrik': {'nama': 'Beban Listrik', 'kode': KODE_AKUN['beban_listrik']['kode']},
                'beban_penyusutan_bangunan': {'nama': 'Beban Depresiasi Bangunan', 'kode': KODE_AKUN['beban_penyusutan_bangunan']['kode']},
                'beban_penyusutan_kendaraan': {'nama': 'Beban Depresiasi Kendaraan', 'kode': KODE_AKUN['beban_penyusutan_kendaraan']['kode']},
                'beban_penyusutan_peralatan': {'nama': 'Beban Depresiasi Peralatan', 'kode': KODE_AKUN['beban_penyusutan_peralatan']['kode']},
                'beban_lainnya': {'nama': 'Beban Lainnya', 'kode': KODE_AKUN['beban_lainnya']['kode']}
            }
            
            akun_debit = akun_debit_mapping.get(trans['jenis'], {'nama': 'Beban Lainnya', 'kode': KODE_AKUN['beban_lainnya']['kode']})
            
            # Tentukan akun kredit berdasarkan metode pembayaran
            if trans.get('metode_bayar') == 'tunai':
                akun_kredit = {'nama': 'Kas', 'kode': KODE_AKUN['kas']['kode']}
            else:
                akun_kredit = {'nama': 'Utang Dagang', 'kode': KODE_AKUN['utang']['kode']}
            
            jurnal = {
                'tanggal': tanggal,
                'keterangan': f"{trans['keterangan']}",
                'ref': trans.get('ref', ''),
                'akun_debit': akun_debit['nama'],
                'kode_akun_debit': akun_debit['kode'],
                'jumlah_debit': trans['jumlah'],
                'akun_kredit': akun_kredit['nama'],
                'kode_akun_kredit': akun_kredit['kode'],
                'jumlah_kredit': trans['jumlah']
            }
            
            jurnal['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
            sibal_data._all_jurnal_umum.append(jurnal)
            jurnal_created.append(jurnal)
            print(f"✅ Created jurnal for {trans['jenis']}")
            
            # TAMBAHKAN KE BUKU BESAR PEMBANTU JIKA KREDIT
            if trans.get('metode_bayar') == 'kredit' and trans.get('supplier'):
                supplier = trans['supplier']
                print(f"🔧 DEBUG: Adding to buku besar pembantu for supplier: {supplier}")
                
                # Inisialisasi jika belum ada
                if supplier not in sibal_data.buku_besar_pembantu:
                    sibal_data.buku_besar_pembantu[supplier] = []
                
                # Hitung saldo terakhir
                saldo_terakhir = 0
                if sibal_data.buku_besar_pembantu[supplier]:
                    saldo_terakhir = sibal_data.buku_besar_pembantu[supplier][-1]['saldo']
                
                saldo_baru = saldo_terakhir + trans['jumlah']
                
                # Tambahkan transaksi
                sibal_data.buku_besar_pembantu[supplier].append({
                    'tanggal': tanggal,
                    'keterangan': f"{trans['jenis']} - {trans['keterangan']}",
                    'debit': 0,
                    'kredit': trans['jumlah'],
                    'saldo': saldo_baru
                })
                print(f"✅ Added to buku besar pembantu: {supplier} - Rp {trans['jumlah']:,}")
        
        # Simpan data setelah semua jurnal dibuat
        if jurnal_created:
            sibal_data.save_all_data()
            return html.Div([
                html.H4("✅ Akumulasi Pengeluaran Berhasil!", style={'color': '#28a745'}),
                html.P(f"{len(jurnal_created)} jurnal telah dibuat untuk transaksi pengeluaran tanggal {tanggal}"),
                html.P(f"Tanggal otomatis berubah ke {next_date_str}", style={'fontWeight': 'bold', 'color': '#007bff'})
            ]), next_date_str
        else:
            return html.Div([
                html.H4("❌ Tidak ada transaksi pengeluaran", style={'color': '#dc3545'}),
                html.P(f"Tidak ada transaksi pengeluaran untuk tanggal {tanggal}"),
                html.P("Silakan buat transaksi pengeluaran terlebih dahulu")
            ]), dash.no_update
    
    return html.P("Klik tombol akumulasi untuk mencatat transaksi ke jurnal"), dash.no_update

# Fungsi untuk akumulasi pengeluaran ke jurnal
def akumulasi_pengeluaran_ke_jurnal(tanggal):
    transaksi_hari_ini = [t for t in sibal_data.transaksi_pengeluaran if t['tanggal'] == tanggal]
    
    if transaksi_hari_ini:
        for trans in transaksi_hari_ini:
            jenis = trans['jenis']
            jumlah = trans['jumlah']
            metode = trans['metode_bayar']
            keterangan = trans['keterangan']
            ref = trans.get('ref', '')
            
            # Tentukan akun berdasarkan kode akun yang sudah disimpan
            akun_debit = trans.get('kode_akun_debit', '')
            akun_debit_nama = next((v['nama'] for k, v in KODE_AKUN.items() if v['kode'] == akun_debit), 'Beban Lainnya')
            
            akun_kredit = trans.get('kode_akun_kredit', '')
            akun_kredit_nama = next((v['nama'] for k, v in KODE_AKUN.items() if v['kode'] == akun_kredit), 'Kas')
            
            # Buat jurnal
            entri_jurnal = {
                'tanggal': tanggal,
                'keterangan': f"{keterangan}",
                'ref': ref,
                'akun_debit': akun_debit_nama,
                'kode_akun_debit': akun_debit,
                'jumlah_debit': jumlah,
                'akun_kredit': akun_kredit_nama,
                'kode_akun_kredit': akun_kredit,
                'jumlah_kredit': jumlah
            }
            entri_jurnal['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
            sibal_data._all_jurnal_umum.append(entri_jurnal)
        
        sibal_data.save_data()
        return html.Div([
            html.H4("✅ Akumulasi Berhasil!", style={'color': '#28a745'}),
            html.P(f"Transaksi pengeluaran tanggal {tanggal} telah dicatat ke Jurnal Umum")
        ])
    
    return html.P("Belum ada transaksi pengeluaran untuk diakumulasi")

@app.callback(
    Output('tabel-kartu-persediaan', 'children'),
    Input('btn-refresh-persediaan', 'n_clicks')
)
def update_kartu_persediaan(n_clicks):
    """Update kartu persediaan dengan perhitungan real-time"""
    print(f"🔄 Memperbarui kartu persediaan...")
    
    # HITUNG ULANG SALDO SEBELUM MENAMPILKAN
    hitung_ulang_semua_saldo()
    
    if sibal_data.kartu_persediaan:
        # Kelompokkan berdasarkan kode barang
        transaksi_per_barang = {}
        for item in sibal_data.kartu_persediaan:
            kode = item['kode_barang']
            if kode not in transaksi_per_barang:
                transaksi_per_barang[kode] = []
            transaksi_per_barang[kode].append(item)
        
        all_tables = []
        
        for kode_barang, transaksi_list in transaksi_per_barang.items():
            # Urutkan transaksi berdasarkan tanggal
            transaksi_list.sort(key=lambda x: x['tanggal'])
            
            barang_pertama = transaksi_list[0]
            
            # BUAT HEADER
            header = html.Tr([
                html.Th("Tanggal", style={'backgroundColor': COLORS['primary'], 'color': 'white', 'padding': '8px'}),
                html.Th("Keterangan", style={'backgroundColor': COLORS['primary'], 'color': 'white', 'padding': '8px'}),
                html.Th("Masuk", style={'backgroundColor': COLORS['success'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['success'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['success'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("Keluar", style={'backgroundColor': COLORS['error'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['error'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['error'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("Saldo", style={'backgroundColor': COLORS['info'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['info'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'}),
                html.Th("", style={'backgroundColor': COLORS['info'], 'color': 'white', 'padding': '8px', 'textAlign': 'center'})
            ])
            
            sub_header = html.Tr([
                html.Th("", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("Qty", style={'backgroundColor': COLORS['success_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Harga", style={'backgroundColor': COLORS['success_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Total", style={'backgroundColor': COLORS['success_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Qty", style={'backgroundColor': COLORS['error_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Harga", style={'backgroundColor': COLORS['error_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Total", style={'backgroundColor': COLORS['error_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Qty", style={'backgroundColor': COLORS['info_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Harga", style={'backgroundColor': COLORS['info_light'], 'color': 'white', 'textAlign': 'center'}),
                html.Th("Total", style={'backgroundColor': COLORS['info_light'], 'color': 'white', 'textAlign': 'center'})
            ])
            
            rows = []
            total_masuk_qty = 0
            total_masuk_nilai = 0
            total_keluar_qty = 0
            total_keluar_nilai = 0
            
            for item in transaksi_list:
                def format_angka(angka):
                    return f"{angka:,.0f}" if angka > 0 else ""
                
                def format_rupiah(angka):
                    return f"Rp{angka:,.0f}".replace(",", ".") if angka > 0 else ""
                
                rows.append(html.Tr([
                    html.Td(item['tanggal'], style={'padding': '6px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'fontSize': '12px'}),
                    html.Td(item['keterangan'], style={'padding': '6px', 'border': '1px solid #dee2e6', 'fontSize': '12px'}),
                    html.Td(format_angka(item['masuk_qty']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e8f5e8', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['masuk_harga']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e8f5e8', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['masuk_total']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e8f5e8', 'fontSize': '12px'}),
                    html.Td(format_angka(item['keluar_qty']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#f8d7da', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['keluar_harga']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#f8d7da', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['keluar_total']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#f8d7da', 'fontSize': '12px'}),
                    html.Td(format_angka(item['saldo_qty']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#d1ecf1', 'fontWeight': 'bold', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['saldo_harga']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#d1ecf1', 'fontSize': '12px'}),
                    html.Td(format_rupiah(item['saldo_total']), style={'padding': '6px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#d1ecf1', 'fontWeight': 'bold', 'fontSize': '12px'})
                ]))
                
                total_masuk_qty += item['masuk_qty']
                total_masuk_nilai += item['masuk_total']
                total_keluar_qty += item['keluar_qty']
                total_keluar_nilai += item['keluar_total']
            
            # BARIS TOTAL
            last_trans = transaksi_list[-1]
            rows.append(html.Tr([
                html.Td("TOTAL", colSpan=2, style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'borderTop': '2px solid #000', 'fontSize': '12px'}),
                html.Td(f"{total_masuk_qty}", style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td("", style={'padding': '8px', 'border': '1px solid #dee2e6', 'borderTop': '2px solid #000'}),
                html.Td(format_rupiah(total_masuk_nilai), style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td(f"{total_keluar_qty}", style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td("", style={'padding': '8px', 'border': '1px solid #dee2e6', 'borderTop': '2px solid #000'}),
                html.Td(format_rupiah(total_keluar_nilai), style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td(f"{last_trans['saldo_qty']}", style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td(format_rupiah(last_trans['saldo_harga']), style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'}),
                html.Td(format_rupiah(last_trans['saldo_total']), style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'borderTop': '2px solid #000', 'textAlign': 'right', 'fontSize': '12px'})
            ]))
            
            table = html.Div([
                html.H4(f"📦 {kode_barang} - {barang_pertama['nama_barang']}", 
                       style={'color': COLORS['primary'], 'marginBottom': '10px', 'fontSize': '16px'}),
                html.Table(
                    [header, sub_header] + rows,
                    style={
                        'width': '100%', 
                        'borderCollapse': 'collapse',
                        'border': '1px solid #dee2e6',
                        'fontSize': '11px'
                    }
                )
            ], style={'marginBottom': '20px', 'overflowX': 'auto'})
            
            all_tables.append(table)
        
        return html.Div(all_tables)
    else:
        return html.Div([
            html.P("📭 Belum ada data kartu persediaan", 
                  style={'textAlign': 'center', 'color': COLORS['gray_600'], 'fontSize': '16px', 'marginBottom': '10px'}),
            html.P("💡 Buat transaksi pembelian persediaan terlebih dahulu", 
                  style={'textAlign': 'center', 'color': COLORS['gray_500'], 'fontSize': '14px'})
        ])
    
@app.callback(
    Output('detail-buku-besar', 'children'),
    Input('dropdown-akun-buku-besar', 'value')
)
def update_buku_besar(akun):
    if akun:
        # Cari nama akun dari value
        akun_nama = next((item['label'].split(' - ')[1] for item in sibal_data.daftar_akun if item['value'] == akun), akun)
        akun_kode = next((item['label'].split(' - ')[0] for item in sibal_data.daftar_akun if item['value'] == akun), "")
        
        # Hitung saldo
        saldo = 0
        transaksi_akun = []
        
        # Gabungkan semua jurnal
        semua_jurnal = sibal_data.jurnal_umum + sibal_data.jurnal_penyesuaian
        
        for jurnal in semua_jurnal:
            if jurnal['kode_akun_debit'] == akun_kode:
                saldo += jurnal['jumlah_debit']
                transaksi_akun.append({
                    'tanggal': jurnal['tanggal'],
                    'keterangan': jurnal['keterangan'],
                    'debit': jurnal['jumlah_debit'],
                    'kredit': 0,
                    'saldo': saldo
                })
            elif jurnal['kode_akun_kredit'] == akun_kode:
                saldo -= jurnal['jumlah_kredit']
                transaksi_akun.append({
                    'tanggal': jurnal['tanggal'],
                    'keterangan': jurnal['keterangan'],
                    'debit': 0,
                    'kredit': jurnal['jumlah_kredit'],
                    'saldo': saldo
                })
        
        if transaksi_akun:
            header = html.Tr([
                html.Th("Tanggal"),
                html.Th("Keterangan"),
                html.Th("Debit"),
                html.Th("Kredit"),
                html.Th("Saldo")
            ])
            
            rows = []
            for trans in transaksi_akun:
                rows.append(html.Tr([
                    html.Td(trans['tanggal']),
                    html.Td(trans['keterangan']),
                    html.Td(format_rupiah(trans['debit']) if trans['debit'] > 0 else ""),
                    html.Td(format_rupiah(trans['kredit']) if trans['kredit'] > 0 else ""),
                    html.Td(format_rupiah(trans['saldo']))
                ]))
            
            return html.Div([
                html.H4(f"Buku Besar: {akun_nama} ({akun_kode})", style={'marginBottom': '20px'}),
                html.Table([header] + rows, className="modern-table")
            ])
        else:
            return html.P(f"Belum ada transaksi untuk akun {akun_nama}", style={'color': '#6c757d'})
    else:
        return html.P("Pilih akun untuk melihat buku besar", style={'color': '#6c757d'})

# Tambahkan callback khusus untuk auto-refresh setelah transaksi
@app.callback(
    Output('btn-refresh-persediaan', 'children'),  # Update tombol refresh sebagai trigger
    [Input('btn-tambah-pengeluaran', 'n_clicks'),
     Input('btn-akumulasi-pengeluaran', 'n_clicks')],
    prevent_initial_call=True
)
def trigger_persediaan_refresh(n_pengeluaran, n_akumulasi):
    """Trigger refresh kartu persediaan setelah transaksi"""
    ctx = dash.callback_context
    if ctx.triggered:
        print(f"🔄 Triggering persediaan refresh from {ctx.triggered[0]['prop_id']}")
        return "🔄 Refresh Data (Updated)"
    return "🔄 Refresh Data"

@app.callback(
    [Output('daftar-supplier', 'children'),
     Output('detail-buku-besar-pembantu', 'children')],
    Input('btn-refresh-buku-pembantu', 'n_clicks')
)
def refresh_buku_besar_pembantu(n_clicks):
    """Refresh data buku besar pembantu"""
    print(f"🔧 DEBUG: Refreshing buku besar pembantu...")
    
    # PROSES DATA UTANG DARI TRANSAKSI KREDIT
    sibal_data.buku_besar_pembantu = {}  # Reset dulu
    
    # Kumpulkan semua supplier dari transaksi kredit
    suppliers_set = set()
    for trans in sibal_data.transaksi_pengeluaran:
        if trans.get('metode_bayar') == 'kredit' and trans.get('supplier'):
            suppliers_set.add(trans['supplier'])
    
    sibal_data.suppliers = list(suppliers_set)
    
    # Proses transaksi untuk setiap supplier
    for supplier in sibal_data.suppliers:
        sibal_data.buku_besar_pembantu[supplier] = []
        
        # Cari semua transaksi kredit untuk supplier ini
        transaksi_supplier = [t for t in sibal_data.transaksi_pengeluaran 
                            if t.get('supplier') == supplier and t.get('metode_bayar') == 'kredit']
        
        saldo = 0
        for trans in transaksi_supplier:
            jumlah = trans['jumlah']
            saldo += jumlah
            
            # Tambahkan transaksi utang
            sibal_data.buku_besar_pembantu[supplier].append({
                'tanggal': trans['tanggal'],
                'keterangan': f"{trans['jenis']} - {trans['keterangan']}",
                'debit': 0,  # Pembayaran akan mengurangi utang (debit)
                'kredit': jumlah,  # Utang bertambah (kredit)
                'saldo': saldo
            })
    
    # Daftar supplier
    if sibal_data.suppliers:
        daftar_supplier = html.Div([
            html.H4("📋 Daftar Supplier dengan Utang", style={'color': COLORS['primary'], 'marginBottom': '20px'}),
            html.Div([
                html.Div([
                    html.Div([
                        html.I(className="fas fa-building", style={'fontSize': '2rem', 'color': COLORS['secondary']}),
                        html.Div([
                            html.Strong(supplier, style={'fontSize': '1.1rem'}),
                            html.Br(),
                            html.Small(f"Total Utang: {format_rupiah(sum(t['kredit'] - t['debit'] for t in sibal_data.buku_besar_pembantu.get(supplier, [])))}")
                        ], style={'marginLeft': '10px'})
                    ], style={'display': 'flex', 'alignItems': 'center', 'padding': '15px'})
                ], style={
                    'backgroundColor': COLORS['white'],
                    'borderRadius': '10px',
                    'boxShadow': '0 2px 5px rgba(0,0,0,0.1)',
                    'marginBottom': '10px',
                    'borderLeft': f'4px solid {COLORS["secondary"]}'
                })
                for supplier in sibal_data.suppliers 
                if supplier in sibal_data.buku_besar_pembantu and sibal_data.buku_besar_pembantu[supplier]
            ])
        ])
    else:
        daftar_supplier = html.Div([
            html.I(className="fas fa-info-circle", style={'fontSize': '3rem', 'color': COLORS['gray_400'], 'display': 'block', 'textAlign': 'center', 'marginBottom': '10px'}),
            html.P("Belum ada supplier dengan utang", style={'textAlign': 'center', 'color': COLORS['gray_600']})
        ])
    
    # Detail per supplier
    detail_supplier = []
    for supplier in sibal_data.suppliers:
        if supplier in sibal_data.buku_besar_pembantu and sibal_data.buku_besar_pembantu[supplier]:
            transaksi = sibal_data.buku_besar_pembantu[supplier]
            
            header = html.Tr([
                html.Th("Tanggal", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("Keterangan", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("Pembayaran (Debit)", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("Utang (Kredit)", style={'backgroundColor': COLORS['primary'], 'color': 'white'}),
                html.Th("Saldo Utang", style={'backgroundColor': COLORS['primary'], 'color': 'white'})
            ])
            
            rows = []
            saldo = 0
            for t in transaksi:
                saldo = saldo + t['kredit'] - t['debit']
                rows.append(html.Tr([
                    html.Td(t['tanggal']),
                    html.Td(t['keterangan']),
                    html.Td(format_rupiah(t['debit']) if t['debit'] > 0 else "-", 
                          style={'color': COLORS['success'], 'textAlign': 'right'}),
                    html.Td(format_rupiah(t['kredit']) if t['kredit'] > 0 else "-",
                          style={'color': COLORS['error'], 'textAlign': 'right'}),
                    html.Td(format_rupiah(saldo), 
                          style={
                              'fontWeight': 'bold', 
                              'color': COLORS['error'] if saldo > 0 else COLORS['success'],
                              'textAlign': 'right'
                          })
                ]))
            
            total_utang = saldo
            detail_supplier.append(html.Div([
                html.H4(f"📊 Buku Besar Pembantu: {supplier}", 
                       style={'color': COLORS['secondary'], 'marginBottom': '20px'}),
                html.Table([header] + rows, className="modern-table"),
                html.Div([
                    html.Strong(f"Total Utang: {format_rupiah(total_utang)}"),
                ], style={
                    'padding': '15px', 
                    'backgroundColor': COLORS['error_light'] if total_utang > 0 else COLORS['success_light'],
                    'color': 'white',
                    'borderRadius': '8px',
                    'textAlign': 'center',
                    'marginTop': '15px',
                    'fontSize': '1.1rem'
                }),
                html.Hr(style={'margin': '30px 0', 'borderColor': COLORS['gray_300']})
            ], style={'marginBottom': '30px'}))
    
    if not detail_supplier:
        detail_supplier = html.Div([
            html.I(className="fas fa-receipt", style={'fontSize': '3rem', 'color': COLORS['gray_400'], 'display': 'block', 'textAlign': 'center', 'marginBottom': '10px'}),
            html.P("Belum ada transaksi utang", style={'textAlign': 'center', 'color': COLORS['gray_600']})
        ])
    else:
        detail_supplier = html.Div(detail_supplier)
    
    return daftar_supplier, detail_supplier

def bayar_utang_supplier(supplier, jumlah, tanggal, keterangan=""):
    """Mencatat pembayaran utang kepada supplier"""
    try:
        if supplier not in sibal_data.buku_besar_pembantu:
            print(f"❌ Supplier {supplier} tidak ditemukan")
            return False
        
        # Hitung saldo terakhir
        saldo_terakhir = 0
        if sibal_data.buku_besar_pembantu[supplier]:
            saldo_terakhir = sibal_data.buku_besar_pembantu[supplier][-1]['saldo']
        
        if jumlah > saldo_terakhir:
            print(f"❌ Jumlah pembayaran melebihi utang. Utang: {saldo_terakhir}, Bayar: {jumlah}")
            return False
        
        saldo_baru = saldo_terakhir - jumlah
        
        # Tambahkan transaksi pembayaran
        sibal_data.buku_besar_pembantu[supplier].append({
            'tanggal': tanggal,
            'keterangan': keterangan if keterangan else f'Pembayaran utang',
            'debit': jumlah,  # Pembayaran mengurangi utang
            'kredit': 0,
            'saldo': saldo_baru
        })
        
        # Buat jurnal untuk pembayaran
        jurnal_pembayaran = {
            'tanggal': tanggal,
            'keterangan': f'Pembayaran utang kepada {supplier}',
            'ref': f'PAY-{supplier}',
            'akun_debit': KODE_AKUN['utang']['nama'],
            'kode_akun_debit': KODE_AKUN['utang']['kode'],
            'jumlah_debit': jumlah,
            'akun_kredit': KODE_AKUN['kas']['nama'],
            'kode_akun_kredit': KODE_AKUN['kas']['kode'],
            'jumlah_kredit': jumlah
        }
        jurnal_pembayaran['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_jurnal_umum.append(jurnal_pembayaran)
        
        print(f"✅ Pembayaran utang {supplier}: Rp{jumlah:,}, sisa: Rp{saldo_baru:,}")
        sibal_data.save_all_data()
        return True
        
    except Exception as e:
        print(f"❌ Error bayar utang: {e}")
        return False
    
@app.callback(
    Output('hidden-trigger-buku-pembantu', 'children'),
    [Input('url', 'pathname'),
     Input('btn-refresh-buku-pembantu', 'n_clicks')],
    prevent_initial_call=True
)
def trigger_buku_pembantu_update(pathname, n_clicks):
    """Trigger untuk memuat ulang data buku besar pembantu"""
    if pathname == '/buku-besar-pembantu' or n_clicks:
        # Process ulang data utang dari transaksi
        sibal_data.buku_besar_pembantu = {}
        sibal_data.suppliers = []
        
        # Kumpulkan semua supplier dari transaksi kredit
        suppliers_set = set()
        for trans in sibal_data.transaksi_pengeluaran:
            if trans.get('metode_bayar') == 'kredit' and trans.get('supplier'):
                suppliers_set.add(trans['supplier'])
        
        sibal_data.suppliers = list(suppliers_set)
        
        # Process transaksi untuk setiap supplier
        for supplier in sibal_data.suppliers:
            sibal_data.buku_besar_pembantu[supplier] = []
            
            # Cari semua transaksi kredit untuk supplier ini
            transaksi_supplier = [t for t in sibal_data.transaksi_pengeluaran 
                                if t.get('supplier') == supplier and t.get('metode_bayar') == 'kredit']
            
            saldo = 0
            for trans in transaksi_supplier:
                jumlah = trans['jumlah']
                saldo += jumlah
                
                # Tambahkan transaksi utang
                sibal_data.buku_besar_pembantu[supplier].append({
                    'tanggal': trans['tanggal'],
                    'keterangan': f"{trans['jenis']} - {trans['keterangan']}",
                    'debit': 0,
                    'kredit': jumlah,
                    'saldo': saldo
                })
        
        return f"updated-{datetime.now().timestamp()}"
    
    return dash.no_update

# Callback untuk menyimpan aset tetap
@app.callback(
    [Output('nilai-aset', 'value'),
     Output('masa-manfaat', 'value'),
     Output('nilai-residu', 'value')],
    Input('btn-simpan-aset', 'n_clicks'),
    [State('jenis-aset', 'value'),
     State('nilai-aset', 'value'),
     State('tanggal-perolehan', 'date'),
     State('masa-manfaat', 'value'),
     State('metode-penyusutan', 'value'),
     State('nilai-residu', 'value')],
    prevent_initial_call=True
)
def simpan_aset_tetap(n_clicks, jenis_aset, nilai_aset, tanggal_perolehan, masa_manfaat, metode, nilai_residu):
    if n_clicks and n_clicks > 0 and jenis_aset and nilai_aset and masa_manfaat:
        # Simpan ke data aset tetap
        sibal_data.aset_tetap[jenis_aset] = {
            'nilai_awal': nilai_aset,
            'penyusutan': 0,  # Akan dihitung nanti
            'masa_manfaat': masa_manfaat,
            'tahun_pembelian': datetime.fromisoformat(tanggal_perolehan).year,
            'metode_penyusutan': metode,
            'nilai_residu': nilai_residu if nilai_residu else 0,
            'tanggal_perolehan': tanggal_perolehan
        }
        
        # Buat jurnal untuk pembelian aset
        if jenis_aset == 'tanah':
            kode_akun_debit = KODE_AKUN['tanah']['kode']
            nama_akun_debit = KODE_AKUN['tanah']['nama']
        elif jenis_aset == 'bangunan_gazebo':
            kode_akun_debit = KODE_AKUN['bangunan_gazebo']['kode']
            nama_akun_debit = KODE_AKUN['bangunan_gazebo']['nama']
        elif jenis_aset == 'kendaraan':
            kode_akun_debit = KODE_AKUN['kendaraan']['kode']
            nama_akun_debit = KODE_AKUN['kendaraan']['nama']
        else:  # peralatan
            kode_akun_debit = KODE_AKUN['peralatan']['kode']
            nama_akun_debit = KODE_AKUN['peralatan']['nama']
        
        # Jurnal pembelian aset
        entri_jurnal = {
            'tanggal': tanggal_perolehan,
            'keterangan': f'Pembelian {nama_akun_debit}',
            'ref': f'AST-{jenis_aset.upper()}',
            'akun_debit': nama_akun_debit,
            'kode_akun_debit': kode_akun_debit,
            'jumlah_debit': nilai_aset,
            'akun_kredit': KODE_AKUN['kas']['nama'],
            'kode_akun_kredit': KODE_AKUN['kas']['kode'],
            'jumlah_kredit': nilai_aset
        }
        entri_jurnal['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
        sibal_data._all_jurnal_umum.append(entri_jurnal)
        
        sibal_data.save_data()
        return '', '', ''
    
    return dash.no_update

# Callback untuk menampilkan daftar aset tetap
@app.callback(
    Output('daftar-aset-tetap', 'children'),
    [Input('btn-simpan-aset', 'n_clicks'),
     Input('btn-hitung-penyusutan', 'n_clicks')]
)
def update_daftar_aset(n_clicks_simpan, n_clicks_hitung):
    if sibal_data.aset_tetap:
        header = html.Tr([
            html.Th("Jenis Aset"),
            html.Th("Nilai Awal"),
            html.Th("Penyusutan"),
            html.Th("Nilai Buku"),
            html.Th("Masa Manfaat"),
            html.Th("Tahun Pembelian")
        ])
        
        rows = []
        for jenis_aset, data in sibal_data.aset_tetap.items():
            if data['nilai_awal'] > 0:  # Hanya tampilkan aset yang sudah diisi
                nilai_buku = data['nilai_awal'] - data['penyusutan']
                rows.append(html.Tr([
                    html.Td(jenis_aset.replace('_', ' ').title()),
                    html.Td(format_rupiah(data['nilai_awal'])),
                    html.Td(format_rupiah(data['penyusutan'])),
                    html.Td(format_rupiah(nilai_buku)),
                    html.Td(f"{data['masa_manfaat']} tahun"),
                    html.Td(data['tahun_pembelian'])
                ]))
        
        if rows:
            return html.Table([header] + rows, className="modern-table")
    
    return html.P("Belum ada data aset tetap", style={'color': '#6c757d'})

@app.callback(
    Output('tabel-neraca-saldo', 'children'),
    Input('btn-generate-neraca-saldo', 'n_clicks'),
    State('tanggal-neraca-saldo', 'date'),
    prevent_initial_call=True
)
def generate_neraca_saldo(n_clicks, tanggal):
    if n_clicks and n_clicks > 0:
        # Hitung saldo setiap akun dari jurnal umum
        saldo_akun = {}
        
        for jurnal in sibal_data.jurnal_umum:
            # Proses akun debit
            kode_debit = jurnal['kode_akun_debit']
            if kode_debit not in saldo_akun:
                saldo_akun[kode_debit] = {'debit': 0, 'kredit': 0, 'nama': jurnal['akun_debit']}
            saldo_akun[kode_debit]['debit'] += jurnal['jumlah_debit']
            
            # Proses akun kredit
            kode_kredit = jurnal['kode_akun_kredit']
            if kode_kredit not in saldo_akun:
                saldo_akun[kode_kredit] = {'debit': 0, 'kredit': 0, 'nama': jurnal['akun_kredit']}
            saldo_akun[kode_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Buat tabel neraca saldo
        header = html.Tr([
            html.Th("Kode Akun"),
            html.Th("Nama Akun"),
            html.Th("Debit"),
            html.Th("Kredit")
        ])
        
        rows = []
        total_debit = 0
        total_kredit = 0
        
        for kode_akun, data in sorted(saldo_akun.items()):
            saldo_debit = max(0, data['debit'] - data['kredit'])
            saldo_kredit = max(0, data['kredit'] - data['debit'])
            
            total_debit += saldo_debit
            total_kredit += saldo_kredit
            
            rows.append(html.Tr([
                html.Td(kode_akun),
                html.Td(data['nama']),
                html.Td(format_rupiah(saldo_debit) if saldo_debit > 0 else ""),
                html.Td(format_rupiah(saldo_kredit) if saldo_kredit > 0 else "")
            ]))
        
        # Baris total
        rows.append(html.Tr([
            html.Td("TOTAL", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
            html.Td(format_rupiah(total_debit), style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
            html.Td(format_rupiah(total_kredit), style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
        ]))
        
        return html.Table([header] + rows, className="modern-table")
    
    return html.P("Klik 'Generate Neraca Saldo' untuk melihat neraca saldo", style={'color': '#6c757d'})

# Callback untuk menghitung penyusutan
@app.callback(
    Output('kalkulator-penyusutan', 'children'),
    Input('btn-hitung-penyusutan', 'n_clicks'),
    prevent_initial_call=True
)
def hitung_penyusutan(n_clicks):
    if n_clicks and n_clicks > 0:
        jurnal_penyesuaian_aset = []
        
        for jenis_aset, data in sibal_data.aset_tetap.items():
            if data['nilai_awal'] > 0 and jenis_aset != 'tanah':  # Tanah tidak disusutkan
                # Hitung penyusutan tahunan dengan metode garis lurus
                nilai_penyusutan = data['nilai_awal'] / data['masa_manfaat']
                
                # Update data penyusutan
                sibal_data.aset_tetap[jenis_aset]['penyusutan'] += nilai_penyusutan
                
                # Buat jurnal penyesuaian untuk penyusutan
                if jenis_aset == 'bangunan_gazebo':
                    kode_akun_beban = KODE_AKUN['beban_penyusutan_bangunan']['kode']
                    nama_akun_beban = KODE_AKUN['beban_penyusutan_bangunan']['nama']
                    kode_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_bangunan']['kode']
                    nama_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_bangunan']['nama']
                elif jenis_aset == 'kendaraan':
                    kode_akun_beban = KODE_AKUN['beban_penyusutan_kendaraan']['kode']
                    nama_akun_beban = KODE_AKUN['beban_penyusutan_kendaraan']['nama']
                    kode_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_kendaraan']['kode']
                    nama_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_kendaraan']['nama']
                else:  # peralatan
                    kode_akun_beban = KODE_AKUN['beban_penyusutan_peralatan']['kode']
                    nama_akun_beban = KODE_AKUN['beban_penyusutan_peralatan']['nama']
                    kode_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_peralatan']['kode']
                    nama_akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_peralatan']['nama']
                
                jurnal_penyesuaian = {
                    'tanggal': datetime.now().date().isoformat(),
                    'keterangan': f'Penyusutan {jenis_aset.replace("_", " ").title()}',
                    'ref': f'DEP-{jenis_aset.upper()}',
                    'akun_debit': nama_akun_beban,
                    'kode_akun_debit': kode_akun_beban,
                    'jumlah_debit': nilai_penyusutan,
                    'akun_kredit': nama_akun_akumulasi,
                    'kode_akun_kredit': kode_akun_akumulasi,
                    'jumlah_kredit': nilai_penyusutan
                }
                jurnal_penyesuaian_aset.append(jurnal_penyesuaian)
                jurnal_penyesuaian['user_id'] = current_user.get_id() if current_user and current_user.get_id() else None
                sibal_data._all_jurnal_penyesuaian.append(jurnal_penyesuaian)
        
        sibal_data.save_data()
        
        # Tampilkan hasil perhitungan
        if jurnal_penyesuaian_aset:
            header = html.Tr([
                html.Th("Jenis Aset"),
                html.Th("Penyusutan Tahunan"),
                html.Th("Akun Beban"),
                html.Th("Akun Akumulasi")
            ])
            
            rows = []
            for jurnal in jurnal_penyesuaian_aset:
                jenis_aset = jurnal['keterangan'].split(' ')[1]
                rows.append(html.Tr([
                    html.Td(jenis_aset),
                    html.Td(format_rupiah(jurnal['jumlah_debit'])),
                    html.Td(jurnal['akun_debit']),
                    html.Td(jurnal['akun_kredit'])
                ]))
            
            return html.Div([
                html.H4("✅ Penyusutan Berhasil Dihitung!", style={'color': '#28a745'}),
                html.Table([header] + rows, className="modern-table")
            ])
    
    return html.P("Klik 'Hitung Penyusutan' untuk menghitung penyusutan aset", style={'color': '#6c757d'})

@app.callback(
    Output('daftar-jurnal-penyesuaian', 'children'),
    Input('btn-generate-penyesuaian', 'n_clicks'),
    State('tanggal-penyesuaian', 'date'),
    prevent_initial_call=True
)
def generate_jurnal_penyesuaian(n_clicks, tanggal):
    if n_clicks and n_clicks > 0:
        # Otomatis buat jurnal penyesuaian untuk penyusutan aset
        jurnal_penyesuaian = []
        
        # 1. Jurnal penyesuaian untuk penyusutan aset
        for jenis_aset, data in sibal_data.aset_tetap.items():
            if data['nilai_awal'] > 0 and jenis_aset != 'tanah':
                # Hitung penyusutan
                nilai_penyusutan = data['nilai_awal'] / data['masa_manfaat']
                
                if jenis_aset == 'bangunan_gazebo':
                    akun_beban = KODE_AKUN['beban_penyusutan_bangunan']['nama']
                    akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_bangunan']['nama']
                elif jenis_aset == 'kendaraan':
                    akun_beban = KODE_AKUN['beban_penyusutan_kendaraan']['nama']
                    akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_kendaraan']['nama']
                else:  # peralatan
                    akun_beban = KODE_AKUN['beban_penyusutan_peralatan']['nama']
                    akun_akumulasi = KODE_AKUN['akumulasi_penyusutan_peralatan']['nama']
                
                jurnal_penyesuaian.append({
                    'tanggal': tanggal,
                    'keterangan': f'Penyusutan {jenis_aset.replace("_", " ").title()}',
                    'akun_debit': akun_beban,
                    'debit': nilai_penyusutan,
                    'akun_kredit': akun_akumulasi,
                    'kredit': nilai_penyusutan
                })
        
        # 2. Jurnal penyesuaian untuk beban yang masih harus dibayar
        # (Contoh: Beban gaji yang belum dibayar)
        total_beban_gaji = sum(t['jumlah'] for t in sibal_data.transaksi_pengeluaran 
                              if t['jenis'] == 'beban_gaji' and t['metode_bayar'] == 'kredit')
        if total_beban_gaji > 0:
            jurnal_penyesuaian.append({
                'tanggal': tanggal,
                'keterangan': 'Beban gaji yang masih harus dibayar',
                'akun_debit': KODE_AKUN['beban_gaji']['nama'],
                'debit': total_beban_gaji,
                'akun_kredit': KODE_AKUN['utang_gaji']['nama'],
                'kredit': total_beban_gaji
            })
        
        # Tampilkan jurnal penyesuaian
        if jurnal_penyesuaian:
            header = html.Tr([
                html.Th("Tanggal"),
                html.Th("Keterangan"),
                html.Th("Akun Debit"),
                html.Th("Debit"),
                html.Th("Akun Kredit"),
                html.Th("Kredit")
            ])
            
            rows = []
            for jurnal in jurnal_penyesuaian:
                rows.append(html.Tr([
                    html.Td(jurnal['tanggal']),
                    html.Td(jurnal['keterangan']),
                    html.Td(jurnal['akun_debit']),
                    html.Td(format_rupiah(jurnal['debit'])),
                    html.Td(jurnal['akun_kredit']),
                    html.Td(format_rupiah(jurnal['kredit']))
                ]))
            
            return html.Table([header] + rows, className="modern-table")
        else:
            return html.P("Tidak ada jurnal penyesuaian yang diperlukan", style={'color': '#6c757d'})
    
    return html.P("Klik 'Generate Jurnal Penyesuaian' untuk membuat jurnal penyesuaian", style={'color': '#6c757d'})

@app.callback(
    Output('tabel-neraca-penyesuaian', 'children'),
    Input('btn-generate-neraca-penyesuaian', 'n_clicks'),
    State('tanggal-neraca-penyesuaian', 'date'),
    prevent_initial_call=True
)
def generate_neraca_setelah_penyesuaian(n_clicks, tanggal):
    if n_clicks and n_clicks > 0:
        # Hitung saldo setiap akun dari jurnal umum + jurnal penyesuaian
        saldo_akun = {}
        
        # Proses jurnal umum
        for jurnal in sibal_data.jurnal_umum:
            kode_debit = jurnal['kode_akun_debit']
            if kode_debit not in saldo_akun:
                saldo_akun[kode_debit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_debit'],
                    'tipe': 'aktiva' if kode_debit.startswith('1') else 'pasiva' if kode_debit.startswith('2') else 'modal' if kode_debit.startswith('3') else 'pendapatan' if kode_debit.startswith('4') else 'beban'
                }
            saldo_akun[kode_debit]['debit'] += jurnal['jumlah_debit']
            
            kode_kredit = jurnal['kode_akun_kredit']
            if kode_kredit not in saldo_akun:
                saldo_akun[kode_kredit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_kredit'],
                    'tipe': 'aktiva' if kode_kredit.startswith('1') else 'pasiva' if kode_kredit.startswith('2') else 'modal' if kode_kredit.startswith('3') else 'pendapatan' if kode_kredit.startswith('4') else 'beban'
                }
            saldo_akun[kode_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Proses jurnal penyesuaian
        for jurnal in sibal_data.jurnal_penyesuaian:
            kode_debit = jurnal['kode_akun_debit']
            if kode_debit not in saldo_akun:
                saldo_akun[kode_debit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_debit'],
                    'tipe': 'aktiva' if kode_debit.startswith('1') else 'pasiva' if kode_debit.startswith('2') else 'modal' if kode_debit.startswith('3') else 'pendapatan' if kode_debit.startswith('4') else 'beban'
                }
            saldo_akun[kode_debit]['debit'] += jurnal['jumlah_debit']
            
            kode_kredit = jurnal['kode_akun_kredit']
            if kode_kredit not in saldo_akun:
                saldo_akun[kode_kredit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_kredit'],
                    'tipe': 'aktiva' if kode_kredit.startswith('1') else 'pasiva' if kode_kredit.startswith('2') else 'modal' if kode_kredit.startswith('3') else 'pendapatan' if kode_kredit.startswith('4') else 'beban'
                }
            saldo_akun[kode_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Kelompokkan akun berdasarkan tipe
        aktiva = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'aktiva'}
        pasiva = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'pasiva'}
        modal = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'modal'}
        pendapatan = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'pendapatan'}
        beban = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'beban'}
        
        # Hitung total aktiva
        total_aktiva = 0
        rows_aktiva = []
        
        for kode, data in sorted(aktiva.items()):
            saldo = data['debit'] - data['kredit']
            if saldo != 0:  # Hanya tampilkan akun dengan saldo
                total_aktiva += saldo
                rows_aktiva.append(html.Tr([
                    html.Td(kode),
                    html.Td(data['nama']),
                    html.Td(format_rupiah(saldo))
                ]))
        
        # Hitung total pasiva + modal
        total_pasiva_modal = 0
        rows_pasiva = []
        rows_modal = []
        
        for kode, data in sorted(pasiva.items()):
            saldo = data['kredit'] - data['debit']
            if saldo != 0:
                total_pasiva_modal += saldo
                rows_pasiva.append(html.Tr([
                    html.Td(kode),
                    html.Td(data['nama']),
                    html.Td(format_rupiah(saldo))
                ]))
        
        for kode, data in sorted(modal.items()):
            saldo = data['kredit'] - data['debit']
            if saldo != 0:
                total_pasiva_modal += saldo
                rows_modal.append(html.Tr([
                    html.Td(kode),
                    html.Td(data['nama']),
                    html.Td(format_rupiah(saldo))
                ]))
        
        # Hitung laba/rugi dari pendapatan dan beban
        total_pendapatan = sum(data['kredit'] - data['debit'] for data in pendapatan.values())
        total_beban = sum(data['debit'] - data['kredit'] for data in beban.values())
        laba_rugi = total_pendapatan - total_beban
        
        # Tambahkan laba/rugi ke modal
        if laba_rugi != 0:
            total_pasiva_modal += laba_rugi
            rows_modal.append(html.Tr([
                html.Td(""),
                html.Td("Laba (Rugi) Berjalan", style={'fontStyle': 'italic'}),
                html.Td(format_rupiah(laba_rugi))
            ]))
        
        # Buat tabel neraca
        return html.Div([
            html.H4(f"Neraca Setelah Penyesuaian per {tanggal}", 
                   style={'textAlign': 'center', 'marginBottom': '30px', 'color': COLORS['primary']}),
            
            html.Div([
                html.Div([
                    html.H5("AKTIVA", style={'color': COLORS['primary'], 'marginBottom': '20px'}),
                    html.Table([
                        html.Tr([html.Th("Kode"), html.Th("Nama Akun"), html.Th("Saldo")])
                    ] + rows_aktiva + [
                        html.Tr([
                            html.Td("", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
                            html.Td(format_rupiah(total_aktiva), 
                                   style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
                        ])
                    ], className="modern-table", style={'width': '100%'})
                ], style={'flex': 1, 'marginRight': '20px'}),
                
                html.Div([
                    html.H5("PASIVA & MODAL", style={'color': COLORS['secondary'], 'marginBottom': '20px'}),
                    
                    html.H6("Kewajiban", style={'color': COLORS['gray_600'], 'marginTop': '15px'}),
                    html.Table([
                        html.Tr([html.Th("Kode"), html.Th("Nama Akun"), html.Th("Saldo")])
                    ] + rows_pasiva, className="modern-table", style={'width': '100%'}),
                    
                    html.H6("Modal", style={'color': COLORS['gray_600'], 'marginTop': '15px'}),
                    html.Table([
                        html.Tr([html.Th("Kode"), html.Th("Nama Akun"), html.Th("Saldo")])
                    ] + rows_modal + [
                        html.Tr([
                            html.Td("", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
                            html.Td(format_rupiah(total_pasiva_modal), 
                                   style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
                        ])
                    ], className="modern-table", style={'width': '100%'})
                ], style={'flex': 1})
            ], style={'display': 'flex', 'gap': '20px'}),
            
            html.Div([
                html.H5("KESEIMBANGAN NERACA", style={
                    'textAlign': 'center', 
                    'color': COLORS['success'] if abs(total_aktiva - total_pasiva_modal) < 0.01 else COLORS['error'],
                    'marginTop': '30px'
                }),
                html.P(f"Total Aktiva: {format_rupiah(total_aktiva)}", 
                      style={'textAlign': 'center', 'fontWeight': 'bold'}),
                html.P(f"Total Pasiva + Modal: {format_rupiah(total_pasiva_modal)}", 
                      style={'textAlign': 'center', 'fontWeight': 'bold'}),
                html.P("✅ Neraca Seimbang" if abs(total_aktiva - total_pasiva_modal) < 0.01 else "❌ Neraca Tidak Seimbang", 
                      style={'textAlign': 'center', 'fontWeight': 'bold', 
                            'color': COLORS['success'] if abs(total_aktiva - total_pasiva_modal) < 0.01 else COLORS['error']})
            ])
        ])
    
    return html.P("Klik 'Generate Neraca Setelah Penyesuaian' untuk melihat neraca", style={'color': '#6c757d'})

@app.callback(
    Output('tabel-laba-rugi', 'children'),
    Input('btn-generate-laba-rugi', 'n_clicks'),
    State('tanggal-laba-rugi', 'date'),
    prevent_initial_call=True
)
def generate_laporan_laba_rugi(n_clicks, tanggal):
    if n_clicks and n_clicks > 0:
        # Hitung saldo setiap akun dari jurnal umum + jurnal penyesuaian
        saldo_akun = {}
        
        # Proses semua jurnal
        semua_jurnal = sibal_data.jurnal_umum + sibal_data.jurnal_penyesuaian
        
        for jurnal in semua_jurnal:
            # Akun debit
            kode_debit = jurnal['kode_akun_debit']
            if kode_debit not in saldo_akun:
                saldo_akun[kode_debit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_debit'],
                    'tipe': 'pendapatan' if kode_debit.startswith('4') else 'beban' if kode_debit.startswith('5') or kode_debit.startswith('6') else 'lainnya'
                }
            saldo_akun[kode_debit]['debit'] += jurnal['jumlah_debit']
            
            # Akun kredit
            kode_kredit = jurnal['kode_akun_kredit']
            if kode_kredit not in saldo_akun:
                saldo_akun[kode_kredit] = {
                    'debit': 0, 
                    'kredit': 0, 
                    'nama': jurnal['akun_kredit'],
                    'tipe': 'pendapatan' if kode_kredit.startswith('4') else 'beban' if kode_kredit.startswith('5') or kode_kredit.startswith('6') else 'lainnya'
                }
            saldo_akun[kode_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Kelompokkan pendapatan dan beban
        pendapatan = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'pendapatan'}
        beban = {k: v for k, v in saldo_akun.items() if v['tipe'] == 'beban'}
        
        # Hitung total pendapatan
        total_pendapatan = 0
        rows_pendapatan = []
        
        for kode, data in sorted(pendapatan.items()):
            saldo = data['kredit'] - data['debit']  # Pendapatan di kredit
            if saldo != 0:
                total_pendapatan += saldo
                rows_pendapatan.append(html.Tr([
                    html.Td(kode),
                    html.Td(data['nama']),
                    html.Td(format_rupiah(saldo))
                ]))
        
        # Hitung total beban
        total_beban = 0
        rows_beban = []
        
        for kode, data in sorted(beban.items()):
            saldo = data['debit'] - data['kredit']  # Beban di debit
            if saldo != 0:
                total_beban += saldo
                rows_beban.append(html.Tr([
                    html.Td(kode),
                    html.Td(data['nama']),
                    html.Td(format_rupiah(saldo))
                ]))
        
        # Hitung laba/rugi
        laba_rugi = total_pendapatan - total_beban
        margin_keuntungan = (laba_rugi / total_pendapatan * 100) if total_pendapatan > 0 else 0
        
        return html.Div([
            html.H4(f"Laporan Laba Rugi per {tanggal}", 
                   style={'textAlign': 'center', 'marginBottom': '30px', 'color': COLORS['primary']}),
            
            # Bagian Pendapatan
            html.Div([
                html.H5("PENDAPATAN", style={'color': COLORS['success'], 'marginBottom': '15px'}),
                html.Table([
                    html.Tr([html.Th("Kode"), html.Th("Jenis Pendapatan"), html.Th("Jumlah")])
                ] + rows_pendapatan + [
                    html.Tr([
                        html.Td("", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
                        html.Td(format_rupiah(total_pendapatan), 
                               style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
                    ])
                ], className="modern-table")
            ], style={'marginBottom': '30px'}),
            
            # Bagian Beban
            html.Div([
                html.H5("BEBAN", style={'color': COLORS['error'], 'marginBottom': '15px'}),
                html.Table([
                    html.Tr([html.Th("Kode"), html.Th("Jenis Beban"), html.Th("Jumlah")])
                ] + rows_beban + [
                    html.Tr([
                        html.Td("", colSpan=2, style={'fontWeight': 'bold', 'borderTop': '2px solid #000'}),
                        html.Td(format_rupiah(total_beban), 
                               style={'fontWeight': 'bold', 'borderTop': '2px solid #000'})
                    ])
                ], className="modern-table")
            ], style={'marginBottom': '30px'}),
            
            # Hasil Laba/Rugi
            html.Div([
                html.H4("HASIL USAHA", style={
                    'textAlign': 'center', 
                    'color': COLORS['success'] if laba_rugi >= 0 else COLORS['error'],
                    'padding': '20px',
                    'backgroundColor': COLORS['accent_mint'] if laba_rugi >= 0 else COLORS['accent_mint_light'],
                    'borderRadius': '15px',
                    'border': f'2px solid {COLORS["success"] if laba_rugi >= 0 else COLORS["error"]}'
                }),
                
                html.Div([
                    html.Div([
                        html.P("Total Pendapatan", style={'fontWeight': 'bold'}),
                        html.P(format_rupiah(total_pendapatan), style={'fontSize': '1.2rem', 'color': COLORS['success']})
                    ], style={'textAlign': 'center', 'flex': 1}),
                    
                    html.Div([
                        html.P("➖", style={'fontSize': '2rem', 'margin': '0 20px'})
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    
                    html.Div([
                        html.P("Total Beban", style={'fontWeight': 'bold'}),
                        html.P(format_rupiah(total_beban), style={'fontSize': '1.2rem', 'color': COLORS['error']})
                    ], style={'textAlign': 'center', 'flex': 1}),
                    
                    html.Div([
                        html.P("🟰", style={'fontSize': '2rem', 'margin': '0 20px'})
                    ], style={'display': 'flex', 'alignItems': 'center'}),
                    
                    html.Div([
                        html.P("Laba (Rugi) Bersih", style={'fontWeight': 'bold'}),
                        html.P(format_rupiah(abs(laba_rugi)), 
                              style={'fontSize': '1.5rem', 'fontWeight': 'bold', 
                                    'color': COLORS['success'] if laba_rugi >= 0 else COLORS['error']})
                    ], style={'textAlign': 'center', 'flex': 1})
                ], style={'display': 'flex', 'justifyContent': 'center', 'alignItems': 'center', 'marginTop': '20px'}),
                
                html.Div([
                    html.P(f"Margin Keuntungan: {margin_keuntungan:.1f}%", 
                          style={'textAlign': 'center', 'fontSize': '1.1rem', 'color': COLORS['gray_600']})
                ], style={'marginTop': '15px'})
            ])
        ])
    
    return html.P("Klik 'Generate Laporan Laba Rugi' untuk melihat laporan", style={'color': '#6c757d'})

def neraca_lajur_layout():
    return html.Div([
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-table")
                ], className="card-icon"),
                html.H1("Neraca Lajur", className="card-title"),
                html.P("Worksheet - Laporan Keuangan Komprehensif", className="card-subtitle")
            ], className="card-header"),
            
            html.Div([
                html.Div([
                    html.Label("Periode Neraca Lajur:", className="form-label"),
                    dcc.DatePickerRange(
                        id='periode-neraca-lajur',
                        start_date=datetime.now().date().replace(day=1),  # awal bulan
                        end_date=datetime.now().date(),
                        display_format='YYYY-MM-DD',
                        className="form-control"
                    )
                ], className="form-group", style={'marginBottom': '20px'}),
                
                html.Button(
                    "📊 Generate Neraca Lajur",
                    id='btn-generate-neraca-lajur',
                    className="btn btn-primary",
                    style={'marginBottom': '20px'}
                ),
                
                html.Div(id='tabel-neraca-lajur', className="table-container")
                
            ], className="card-content")
        ], className="glass-card")
    ], className="main-container")

# Callback untuk generate neraca lajur
@app.callback(
    Output('tabel-neraca-lajur', 'children'),
    Input('btn-generate-neraca-lajur', 'n_clicks'),
    [State('periode-neraca-lajur', 'start_date'),
     State('periode-neraca-lajur', 'end_date')]
)
def generate_neraca_lajur(n_clicks, start_date, end_date):
    if n_clicks and n_clicks > 0:
        return create_neraca_lajur_table(start_date, end_date)
    
    return html.P("Pilih periode dan klik 'Generate Neraca Lajur'", style={'color': '#6c757d'})

def create_neraca_lajur_table(start_date, end_date):
    """Membuat tabel neraca lajur dari data aktual"""
    
    # Hitung saldo dari semua akun sebelum penyesuaian (hanya jurnal umum)
    saldo_neraca_saldo = calculate_saldo_akun_periode(sibal_data.jurnal_umum, start_date, end_date)
    
    # Hitung saldo penyesuaian (hanya jurnal penyesuaian)
    saldo_penyesuaian = calculate_saldo_akun_periode(sibal_data.jurnal_penyesuaian, start_date, end_date)
    
    # Hitung saldo setelah penyesuaian (gabungan jurnal umum + penyesuaian)
    saldo_setelah_penyesuaian = calculate_saldo_akun_periode(
        sibal_data.jurnal_umum + sibal_data.jurnal_penyesuaian, start_date, end_date
    )
    
    # Klasifikasikan akun untuk laba rugi dan posisi keuangan
    akun_laba_rugi = ['pendapatan', 'pendapatan_tiket', 'hpp', 'beban_gaji', 'beban_listrik', 
                      'beban_penyusutan_bangunan', 'beban_penyusutan_kendaraan', 
                      'beban_penyusutan_peralatan', 'beban_lainnya']
    
    akun_posisi_keuangan = ['kas', 'persediaan', 'perlengkapan', 'peralatan', 'tanah', 
                           'bangunan_gazebo', 'akumulasi_penyusutan_bangunan', 'kendaraan',
                           'akumulasi_penyusutan_kendaraan', 'akumulasi_penyusutan_peralatan',
                           'utang', 'utang_gaji', 'modal']
    
    # Header tabel
    header = html.Tr([
        html.Th("Kode Akun", rowSpan=2, style={'backgroundColor': '#343a40', 'color': 'white', 'padding': '10px', 'minWidth': '80px'}),
        html.Th("Nama Akun", rowSpan=2, style={'backgroundColor': '#343a40', 'color': 'white', 'padding': '10px', 'minWidth': '200px'}),
        html.Th("Neraca Saldo Sebelum Penyesuaian", colSpan=2, style={'backgroundColor': '#007bff', 'color': 'white', 'textAlign': 'center'}),
        html.Th("Penyesuaian", colSpan=2, style={'backgroundColor': '#28a745', 'color': 'white', 'textAlign': 'center'}),
        html.Th("Neraca Saldo Setelah Penyesuaian", colSpan=2, style={'backgroundColor': '#ffc107', 'color': 'white', 'textAlign': 'center'}),
        html.Th("Laporan Laba Rugi", colSpan=2, style={'backgroundColor': '#dc3545', 'color': 'white', 'textAlign': 'center'}),
        html.Th("Laporan Posisi Keuangan", colSpan=2, style={'backgroundColor': '#6f42c1', 'color': 'white', 'textAlign': 'center'})
    ])
    
    sub_header = html.Tr([
        html.Th("", style={'backgroundColor': '#343a40', 'color': 'white'}),  # Kode Akun
        html.Th("", style={'backgroundColor': '#343a40', 'color': 'white'}),  # Nama Akun
        html.Th("Debit", style={'backgroundColor': '#007bff', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Kredit", style={'backgroundColor': '#007bff', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Debit", style={'backgroundColor': '#28a745', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Kredit", style={'backgroundColor': '#28a745', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Debit", style={'backgroundColor': '#ffc107', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Kredit", style={'backgroundColor': '#ffc107', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Debit", style={'backgroundColor': '#dc3545', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Kredit", style={'backgroundColor': '#dc3545', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Debit", style={'backgroundColor': '#6f42c1', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'}),
        html.Th("Kredit", style={'backgroundColor': '#6f42c1', 'color': 'white', 'textAlign': 'right', 'minWidth': '120px'})
    ])
    
    rows = []
    
    # Kumpulkan semua akun yang ada saldo
    semua_akun = set(saldo_neraca_saldo.keys()).union(
        set(saldo_penyesuaian.keys()), 
        set(saldo_setelah_penyesuaian.keys())
    )
    
    # Urutkan akun berdasarkan kode
    akun_terurut = []
    for akun in semua_akun:
        kode = KODE_AKUN.get(akun, {}).get('kode', '')
        akun_terurut.append((kode, akun))
    akun_terurut.sort()
    
    # Variabel untuk total
    total_debit_neraca = 0
    total_kredit_neraca = 0
    total_debit_penyesuaian = 0
    total_kredit_penyesuaian = 0
    total_debit_setelah = 0
    total_kredit_setelah = 0
    total_debit_laba_rugi = 0
    total_kredit_laba_rugi = 0
    total_debit_posisi = 0
    total_kredit_posisi = 0
    
    # Buat baris untuk setiap akun
    for kode, akun in akun_terurut:
        nama_akun = KODE_AKUN.get(akun, {}).get('nama', akun)
        
        # Saldo neraca saldo (sebelum penyesuaian)
        saldo_ns = saldo_neraca_saldo.get(akun, 0)
        debit_ns = saldo_ns if saldo_ns > 0 else 0
        kredit_ns = abs(saldo_ns) if saldo_ns < 0 else 0
        
        # Saldo penyesuaian
        saldo_pen = saldo_penyesuaian.get(akun, 0)
        debit_pen = saldo_pen if saldo_pen > 0 else 0
        kredit_pen = abs(saldo_pen) if saldo_pen < 0 else 0
        
        # Saldo setelah penyesuaian
        saldo_setelah = saldo_setelah_penyesuaian.get(akun, 0)
        debit_setelah = saldo_setelah if saldo_setelah > 0 else 0
        kredit_setelah = abs(saldo_setelah) if saldo_setelah < 0 else 0
        
        # Klasifikasi untuk laba rugi dan posisi keuangan
        if akun in akun_laba_rugi:
            debit_lr = debit_setelah
            kredit_lr = kredit_setelah
            debit_pk = 0
            kredit_pk = 0
        elif akun in akun_posisi_keuangan:
            debit_lr = 0
            kredit_lr = 0
            debit_pk = debit_setelah
            kredit_pk = kredit_setelah
        else:
            # Default: masukkan ke posisi keuangan
            debit_lr = 0
            kredit_lr = 0
            debit_pk = debit_setelah
            kredit_pk = kredit_setelah
        
        # Tambahkan ke total
        total_debit_neraca += debit_ns
        total_kredit_neraca += kredit_ns
        total_debit_penyesuaian += debit_pen
        total_kredit_penyesuaian += kredit_pen
        total_debit_setelah += debit_setelah
        total_kredit_setelah += kredit_setelah
        total_debit_laba_rugi += debit_lr
        total_kredit_laba_rugi += kredit_lr
        total_debit_posisi += debit_pk
        total_kredit_posisi += kredit_pk
        
        # Buat baris
        rows.append(html.Tr([
            html.Td(kode, style={'padding': '8px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold'}),
            html.Td(nama_akun, style={'padding': '8px', 'border': '1px solid #dee2e6'}),
            html.Td(format_currency(debit_ns), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e3f2fd'}),
            html.Td(format_currency(kredit_ns), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e3f2fd'}),
            html.Td(format_currency(debit_pen), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e8f5e8'}),
            html.Td(format_currency(kredit_pen), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e8f5e8'}),
            html.Td(format_currency(debit_setelah), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#fff3cd'}),
            html.Td(format_currency(kredit_setelah), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#fff3cd'}),
            html.Td(format_currency(debit_lr), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#f8d7da'}),
            html.Td(format_currency(kredit_lr), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#f8d7da'}),
            html.Td(format_currency(debit_pk), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e2e3f5'}),
            html.Td(format_currency(kredit_pk), style={'padding': '8px', 'border': '1px solid #dee2e6', 'textAlign': 'right', 'backgroundColor': '#e2e3f5'})
        ]))
    
    # Baris jumlah
    rows.append(html.Tr([
        html.Td("", colSpan=2, style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'center', 'backgroundColor': '#e9ecef'}, children=["Jumlah"]),
        html.Td(format_currency(total_debit_neraca), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_neraca), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_debit_penyesuaian), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_penyesuaian), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_debit_setelah), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_setelah), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_debit_laba_rugi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_laba_rugi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_debit_posisi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_posisi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'})
    ]))
    
    # Baris laba (rugi) bersih
    laba_bersih = total_kredit_laba_rugi - total_debit_laba_rugi
    rows.append(html.Tr([
        html.Td("", colSpan=8, style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'center', 'backgroundColor': '#f8f9fa'}, children=["Laba (Rugi) Bersih"]),
        html.Td(format_currency(laba_bersih), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#f8f9fa'}),
        html.Td("", style={'padding': '10px', 'border': '1px solid #dee2e6', 'backgroundColor': '#f8f9fa'}),
        html.Td(format_currency(laba_bersih), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#f8f9fa'}),
        html.Td("", style={'padding': '10px', 'border': '1px solid #dee2e6', 'backgroundColor': '#f8f9fa'})
    ]))
    
    # Baris jumlah akhir
    rows.append(html.Tr([
        html.Td("", colSpan=8, style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'center', 'backgroundColor': '#e9ecef'}, children=["Jumlah"]),
        html.Td(format_currency(total_kredit_laba_rugi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_laba_rugi), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_debit_posisi + laba_bersih), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'}),
        html.Td(format_currency(total_kredit_posisi + laba_bersih), style={'padding': '10px', 'border': '1px solid #dee2e6', 'fontWeight': 'bold', 'textAlign': 'right', 'backgroundColor': '#e9ecef', 'borderTop': '2px solid #000'})
    ]))
    
    # Cek balancing
    is_balanced = (total_debit_neraca == total_kredit_neraca and 
                   total_debit_penyesuaian == total_kredit_penyesuaian and
                   total_debit_setelah == total_kredit_setelah and
                   total_debit_laba_rugi + laba_bersih == total_kredit_laba_rugi and
                   total_debit_posisi + laba_bersih == total_kredit_posisi)
    
    status_message = html.Div([
        html.H4("✅ NERACA LAJUR BALANCE" if is_balanced else "❌ NERACA LAJUR TIDAK BALANCE", 
               style={'color': '#28a745' if is_balanced else '#dc3545', 'textAlign': 'center', 'marginTop': '20px'})
    ])
    
    return html.Div([
        html.H4(f"NERACA LAJUR - Periode {start_date} s/d {end_date}", style={
            'textAlign': 'center', 
            'color': '#007bff', 
            'marginBottom': '20px'
        }),
        html.Div([
            html.Table(
                [header, sub_header] + rows,
                style={
                    'width': '100%', 
                    'borderCollapse': 'collapse',
                    'border': '1px solid #dee2e6',
                    'fontSize': '11px',
                    'overflowX': 'auto'
                }
            )
        ], style={'overflowX': 'auto', 'width': '100%'}),
        status_message
    ])

def calculate_saldo_akun_periode(jurnal_data, start_date, end_date):
    """Hitung saldo akun untuk periode tertentu dari data jurnal"""
    saldo_akun = {}
    
    # Filter jurnal berdasarkan tanggal
    jurnal_periode = [j for j in jurnal_data if start_date <= j['tanggal'] <= end_date]
    
    for jurnal in jurnal_periode:
        # Debit
        akun_debit = jurnal['akun_debit']
        if akun_debit not in saldo_akun:
            saldo_akun[akun_debit] = 0
        saldo_akun[akun_debit] += jurnal['jumlah_debit']
        
        # Kredit
        akun_kredit = jurnal['akun_kredit']
        if akun_kredit not in saldo_akun:
            saldo_akun[akun_kredit] = 0
        saldo_akun[akun_kredit] -= jurnal['jumlah_kredit']
    
    return saldo_akun

def format_currency(amount):
    """Format currency dengan pemisah ribuan"""
    if amount == 0:
        return ""
    return f"Rp{amount:,.0f}"
    
@app.callback(
    Output('tabel-laporan-keuangan', 'children'),
    Input('btn-generate-laporan-keuangan', 'n_clicks'),
    State('tanggal-laporan-keuangan', 'date'),
    prevent_initial_call=True
)
def generate_laporan_keuangan_lengkap(n_clicks, tanggal):
    if n_clicks and n_clicks > 0:
        # Reuse functions from previous callbacks to get data
        saldo_akun = {}
        
        # Process all journals
        semua_jurnal = sibal_data.jurnal_umum + sibal_data.jurnal_penyesuaian
        
        for jurnal in semua_jurnal:
            kode_debit = jurnal['kode_akun_debit']
            if kode_debit not in saldo_akun:
                saldo_akun[kode_debit] = {
                    'debit': 0, 'kredit': 0, 'nama': jurnal['akun_debit'],
                    'tipe': 'aktiva' if kode_debit.startswith('1') else 'pasiva' if kode_debit.startswith('2') else 'modal' if kode_debit.startswith('3') else 'pendapatan' if kode_debit.startswith('4') else 'beban'
                }
            saldo_akun[kode_debit]['debit'] += jurnal['jumlah_debit']
            
            kode_kredit = jurnal['kode_akun_kredit']
            if kode_kredit not in saldo_akun:
                saldo_akun[kode_kredit] = {
                    'debit': 0, 'kredit': 0, 'nama': jurnal['akun_kredit'],
                    'tipe': 'aktiva' if kode_kredit.startswith('1') else 'pasiva' if kode_kredit.startswith('2') else 'modal' if kode_kredit.startswith('3') else 'pendapatan' if kode_kredit.startswith('4') else 'beban'
                }
            saldo_akun[kode_kredit]['kredit'] += jurnal['jumlah_kredit']
        
        # Calculate financial ratios and summaries
        aktiva_lancar = sum(data['debit'] - data['kredit'] for kode, data in saldo_akun.items() 
                           if data['tipe'] == 'aktiva' and kode in ['1-110', '1-120', '1-130'])  # Kas, Persediaan, Perlengkapan
        
        aktiva_tetap = sum(data['debit'] - data['kredit'] for kode, data in saldo_akun.items() 
                          if data['tipe'] == 'aktiva' and kode in ['1-210', '1-220', '1-230', '1-240'])  # Aset tetap
        
        kewajiban_lancar = sum(data['kredit'] - data['debit'] for kode, data in saldo_akun.items() 
                              if data['tipe'] == 'pasiva' and kode in ['2-110', '2-120'])  # Utang
        
        modal = sum(data['kredit'] - data['debit'] for kode, data in saldo_akun.items() 
                   if data['tipe'] == 'modal')
        
        pendapatan = sum(data['kredit'] - data['debit'] for kode, data in saldo_akun.items() 
                        if data['tipe'] == 'pendapatan')
        
        beban = sum(data['debit'] - data['kredit'] for kode, data in saldo_akun.items() 
                   if data['tipe'] == 'beban')
        
        laba_bersih = pendapatan - beban
        
        # Financial ratios
        rasio_likuiditas = aktiva_lancar / kewajiban_lancar if kewajiban_lancar > 0 else float('inf')
        margin_laba = (laba_bersih / pendapatan * 100) if pendapatan > 0 else 0
        roa = (laba_bersih / (aktiva_lancar + aktiva_tetap) * 100) if (aktiva_lancar + aktiva_tetap) > 0 else 0
        
        return html.Div([
            html.H4(f"LAPORAN KEUANGAN LENGKAP", 
                   style={'textAlign': 'center', 'marginBottom': '10px', 'color': COLORS['primary']}),
            html.H5(f"Periode sampai dengan {tanggal}", 
                   style={'textAlign': 'center', 'marginBottom': '30px', 'color': COLORS['gray_600']}),
            
            # Laporan Laba Rugi Section
            html.Div([
                html.H5("1. LAPORAN LABA RUGI", style={'color': COLORS['primary'], 'borderBottom': f'2px solid {COLORS["primary"]}', 'paddingBottom': '10px'}),
                
                html.Div([
                    html.Div([
                        html.P("Pendapatan Usaha", style={'fontWeight': 'bold'}),
                        html.P(format_rupiah(pendapatan), style={'fontSize': '1.1rem', 'color': COLORS['success']})
                    ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '10px'}),
                    
                    html.Div([
                        html.P("Beban Usaha", style={'fontWeight': 'bold'}),
                        html.P(format_rupiah(beban), style={'fontSize': '1.1rem', 'color': COLORS['error']})
                    ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '10px'}),
                    
                    html.Hr(),
                    
                    html.Div([
                        html.P("LABA (RUGI) BERSIH", style={'fontWeight': 'bold', 'fontSize': '1.2rem'}),
                        html.P(format_rupiah(laba_bersih), 
                              style={'fontSize': '1.3rem', 'fontWeight': 'bold', 
                                    'color': COLORS['success'] if laba_bersih >= 0 else COLORS['error']})
                    ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginTop': '10px'})
                ], style={'backgroundColor': COLORS['gray_50'], 'padding': '20px', 'borderRadius': '10px', 'marginTop': '15px'})
            ], style={'marginBottom': '30px'}),
            
            # Neraca Section
            html.Div([
                html.H5("2. NERACA", style={'color': COLORS['secondary'], 'borderBottom': f'2px solid {COLORS["secondary"]}', 'paddingBottom': '10px'}),
                
                html.Div([
                    html.Div([
                        html.H6("AKTIVA", style={'color': COLORS['primary']}),
                        
                        html.Div([
                            html.P("Aktiva Lancar", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(aktiva_lancar))
                        ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}),
                        
                        html.Div([
                            html.P("Aktiva Tetap", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(aktiva_tetap))
                        ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}),
                        
                        html.Hr(),
                        
                        html.Div([
                            html.P("TOTAL AKTIVA", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(aktiva_lancar + aktiva_tetap), style={'fontWeight': 'bold'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between'})
                    ], style={'flex': 1, 'padding': '15px', 'backgroundColor': COLORS['accent_mint'], 'borderRadius': '10px', 'marginRight': '10px'}),
                    
                    html.Div([
                        html.H6("PASIVA & MODAL", style={'color': COLORS['secondary']}),
                        
                        html.Div([
                            html.P("Kewajiban Lancar", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(kewajiban_lancar))
                        ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}),
                        
                        html.Div([
                            html.P("Modal", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(modal))
                        ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}),
                        
                        html.Div([
                            html.P("Laba Ditahan", style={'fontWeight': 'bold', 'fontStyle': 'italic'}),
                            html.P(format_rupiah(laba_bersih), style={'fontStyle': 'italic'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between', 'marginBottom': '5px'}),
                        
                        html.Hr(),
                        
                        html.Div([
                            html.P("TOTAL PASIVA & MODAL", style={'fontWeight': 'bold'}),
                            html.P(format_rupiah(kewajiban_lancar + modal + laba_bersih), style={'fontWeight': 'bold'})
                        ], style={'display': 'flex', 'justifyContent': 'space-between'})
                    ], style={'flex': 1, 'padding': '15px', 'backgroundColor': COLORS['accent_mint_light'], 'borderRadius': '10px', 'marginLeft': '10px'})
                ], style={'display': 'flex', 'marginTop': '15px'})
            ], style={'marginBottom': '30px'}),
            
            # Analisis Rasio Keuangan
            html.Div([
                html.H5("3. ANALISIS RASIO KEUANGAN", style={'color': COLORS['accent_teal'], 'borderBottom': f'2px solid {COLORS["accent_teal"]}', 'paddingBottom': '10px'}),
                
                html.Div([
                    html.Div([
                        html.Div([
                            html.H6("Rasio Likuiditas", style={'color': COLORS['primary']}),
                            html.P(f"{rasio_likuiditas:.2f}", style={'fontSize': '1.5rem', 'fontWeight': 'bold', 'color': COLORS['success'] if rasio_likuiditas >= 1 else COLORS['warning']}),
                            html.Small("Aktiva Lancar / Kewajiban Lancar", style={'color': COLORS['gray_600']}),
                            html.Br(),
                            html.Small("✅ Baik" if rasio_likuiditas >= 1 else "⚠️ Perlu Perhatian", 
                                     style={'color': COLORS['success'] if rasio_likuiditas >= 1 else COLORS['warning']})
                        ], style={'textAlign': 'center', 'padding': '15px', 'backgroundColor': COLORS['white'], 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'})
                    ], style={'flex': 1, 'margin': '0 10px'}),
                    
                    html.Div([
                        html.Div([
                            html.H6("Margin Laba Bersih", style={'color': COLORS['primary']}),
                            html.P(f"{margin_laba:.1f}%", style={'fontSize': '1.5rem', 'fontWeight': 'bold', 'color': COLORS['success'] if margin_laba >= 10 else COLORS['warning'] if margin_laba >= 5 else COLORS['error']}),
                            html.Small("(Laba Bersih / Pendapatan) × 100%", style={'color': COLORS['gray_600']}),
                            html.Br(),
                            html.Small("✅ Excellent" if margin_laba >= 15 else "👍 Baik" if margin_laba >= 10 else "⚠️ Cukup" if margin_laba >= 5 else "❌ Perlu Perbaikan", 
                                     style={'color': COLORS['success'] if margin_laba >= 15 else COLORS['info'] if margin_laba >= 10 else COLORS['warning'] if margin_laba >= 5 else COLORS['error']})
                        ], style={'textAlign': 'center', 'padding': '15px', 'backgroundColor': COLORS['white'], 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'})
                    ], style={'flex': 1, 'margin': '0 10px'}),
                    
                    html.Div([
                        html.Div([
                            html.H6("Return on Assets (ROA)", style={'color': COLORS['primary']}),
                            html.P(f"{roa:.1f}%", style={'fontSize': '1.5rem', 'fontWeight': 'bold', 'color': COLORS['success'] if roa >= 5 else COLORS['warning'] if roa >= 2 else COLORS['error']}),
                            html.Small("(Laba Bersih / Total Aset) × 100%", style={'color': COLORS['gray_600']}),
                            html.Br(),
                            html.Small("✅ Excellent" if roa >= 8 else "👍 Baik" if roa >= 5 else "⚠️ Cukup" if roa >= 2 else "❌ Perlu Perbaikan", 
                                     style={'color': COLORS['success'] if roa >= 8 else COLORS['info'] if roa >= 5 else COLORS['warning'] if roa >= 2 else COLORS['error']})
                        ], style={'textAlign': 'center', 'padding': '15px', 'backgroundColor': COLORS['white'], 'borderRadius': '10px', 'boxShadow': '0 2px 10px rgba(0,0,0,0.1)'})
                    ], style={'flex': 1, 'margin': '0 10px'})
                ], style={'display': 'flex', 'marginTop': '15px'})
            ], style={'marginBottom': '30px'}),
            
            # Ringkasan Eksekutif
            html.Div([
                html.H5("4. RINGKASAN EKSEKUTIF", style={'color': COLORS['accent_lavender'], 'borderBottom': f'2px solid {COLORS["accent_lavender"]}', 'paddingBottom': '10px'}),
                
                html.Div([
                    html.P("🔍 **Tinjauan Kinerja:**", style={'fontWeight': 'bold'}),
                    html.Ul([
                        html.Li(f"Perusahaan {'mencapai laba' if laba_bersih >= 0 else 'mengalami rugi'} sebesar {format_rupiah(abs(laba_bersih))}"),
                        html.Li(f"Margin laba bersih sebesar {margin_laba:.1f}% {'di atas rata-rata industri' if margin_laba >= 15 else 'sesuai ekspektasi' if margin_laba >= 8 else 'perlu peningkatan'}"),
                        html.Li(f"Total aset perusahaan senilai {format_rupiah(aktiva_lancar + aktiva_tetap)}"),
                    ]),
                    
                    html.P("💡 **Rekomendasi:**", style={'fontWeight': 'bold', 'marginTop': '15px'}),
                    html.Ul([
                        html.Li("Pertahankan pertumbuhan pendapatan dengan strategi pemasaran yang efektif"),
                        html.Li("Optimalkan pengelolaan persediaan untuk meningkatkan likuiditas"),
                        html.Li("Monitor beban operasional untuk efisiensi yang lebih baik"),
                    ]) if laba_bersih >= 0 else html.Ul([
                        html.Li("Lakukan review terhadap struktur biaya operasional"),
                        html.Li("Tingkatkan efisiensi dalam pengelolaan persediaan"),
                        html.Li("Evaluasi strategi penetapan harga jual"),
                    ])
                ], style={'backgroundColor': COLORS['gray_50'], 'padding': '20px', 'borderRadius': '10px', 'marginTop': '15px'})
            ])
        ])
    
    return html.P("Klik 'Generate Laporan Keuangan Lengkap' untuk melihat laporan", style={'color': '#6c757d'})


if __name__ == '__main__':
    print("🚀 Starting SIBAL Application...")
    print("📊 Debug mode: ON")
    print("🌐 Server will be available at: http://127.0.0.1:8051")
    print("⏳ Please wait for server to start...")
    
    try:
        app.run(debug=True, port=8051)
        print("✅ Server started successfully!")
    except Exception as e:
        print(f"❌ Error starting server: {e}")
        print("💡 Try changing port to 8052")
