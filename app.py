from flask import Flask, render_template, request, redirect, url_for, send_file, jsonify, session
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
from PyPDF2 import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from io import BytesIO
import os
import re
from datetime import datetime
import json
import math
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from io import BytesIO
from datetime import timedelta
from ftplib import FTP
import secrets
from flask_wtf.csrf import CSRFProtect
from functools import wraps
from flask_talisman import Talisman

# Uygulama oluşturma
app = Flask(__name__)

# Güvenli rastgele secret key oluşturma
app.secret_key = secrets.token_hex(16)  # Her başlatmada yeni bir secret key (daha güvenli)

# CSRF koruması ekleme
csrf = CSRFProtect(app)

# Oturum süresini 30 dakika olarak güncelleme
app.permanent_session_lifetime = timedelta(minutes=30)

# Güvenlik başlıklarını ekleyen Talisman
talisman = Talisman(
    app,
    content_security_policy={
        'default-src': ['\'self\''],
        'script-src': ['\'self\'', '\'unsafe-inline\''],
        'style-src': ['\'self\'', '\'unsafe-inline\'']
    },
    force_https=False,  # Geliştirme için False, üretimde True
    session_cookie_secure=False,  # Geliştirme için False, üretimde True
    session_cookie_http_only=True
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Kullanıcı yetkilendirme dekoratörü
def admin_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        
        if session.get('authority') != 'admin':
            return render_template('error.html', message="Bu sayfaya erişim yetkiniz bulunmamaktadır."), 403
            
        return func(*args, **kwargs)
    return decorated_function

# Oturum aktivitesi kontrol fonksiyonu
def check_session_activity():
    """Kullanıcı oturum aktivitesini kontrol eder ve oturum süresi dolmuş ise oturumu kapatır"""
    
    # Kullanıcı giriş yapmamışsa atla
    if not session.get('logged_in'):
        return
        
    # Son aktivite zamanını kontrol et
    last_activity = session.get('last_activity')
    if not last_activity:
        session['last_activity'] = datetime.now().isoformat()
        return
        
    # Son aktivite üzerinden geçen süre
    last_time = datetime.fromisoformat(last_activity)
    time_diff = (datetime.now() - last_time).total_seconds()
    
    # Oturum süresi dolmuşsa (varsayılan 30 dk)
    timeout = 30 * 60  # 30 dakika
    
    # Güvenlik ayarlarından oturum zaman aşımını al
    try:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT session_timeout_minutes FROM security_settings ORDER BY id DESC LIMIT 1")
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            timeout = result[0] * 60  # dakika -> saniye
    except:
        # Veritabanı hatası durumunda varsayılan değeri kullan
        pass
    
    if time_diff > timeout:
        # Oturumu sonlandır
        session.clear()
        return redirect(url_for('login', message="Oturumunuz süresi dolduğu için sonlandırıldı. Lütfen tekrar giriş yapın."))
        
    # Son aktivite zamanını güncelle
    session['last_activity'] = datetime.now().isoformat()
    return None

# Her istek öncesinde çalışacak fonksiyon
@app.before_request
def before_request():
    # Oturum aktivitesi kontrolü
    redirect_response = check_session_activity()
    if redirect_response:
        return redirect_response

# quotes dizinine giden yolu ayarlayın
QUOTE_DB_PATH = os.path.join(BASE_DIR, 'quotes')

# Yeni global değişkenler
click_logs = []
islmdvm = 0

@app.route('/set_customer', methods=['POST'])
def set_customer():
    try:
        data = request.get_json()
        customer_id = data.get('customer_id')
        customer_name = data.get('customer_name')

        if not customer_id or not customer_name:
            return jsonify({'status': 'error', 'message': 'Eksik müşteri bilgileri.'}), 400

        # Müşteri bilgilerini oturumda sakla
        session['customer_id'] = customer_id
        session['customer_name'] = customer_name

        return jsonify({'status': 'success', 'message': 'Müşteri bilgileri başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata:", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

# Yeni endpoint
@app.route('/log_click', methods=['POST'])
def log_click():
    try:
        data = request.get_json()
        user = data.get('user', 'Unknown User')
        user_id = data.get('user_id', 'Unknown ID')
        time = datetime.now().isoformat()
        
        global click_logs
        now = datetime.now()
        click_logs = [log for log in click_logs 
                     if (now - datetime.fromisoformat(log['time'])).total_seconds() <= 60]
        
        click_logs.append({
            'user': user,
            'user_id': user_id,
            'time': time  # Zaman damgası eklendi
        })
        
        recent_clicks = [log for log in click_logs 
                        if (now - datetime.fromisoformat(log['time'])).total_seconds() <= 1]
        
        return jsonify({
            'status': 'success',
            'recent_clicks': recent_clicks  # Zaman damgası içeren veri
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

@app.route('/reset_islmdvm', methods=['POST'])
def reset_islmdvm():
    global islmdvm
    islmdvm = 0  # islmdvm değerini sıfırla
    return jsonify({'status': 'success', 'message': 'islmdvm sıfırlandı.'})

@app.route('/check_islmdvm', methods=['GET'])
def check_islmdvm():
    global islmdvm
    if islmdvm == 1:
        return jsonify({'status': 'busy'})
    else:
        islmdvm = 1
        return jsonify({'status': 'free'})

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Brüt Kuvvet saldırılarına karşı koruma - başarısız giriş sayılarını takip etme
        ip_address = request.remote_addr
        failed_attempts = session.get('failed_attempts', {})
        
        # IP adresinden yapılan başarısız deneme sayısını kontrol et
        if ip_address in failed_attempts and failed_attempts[ip_address]['count'] >= 5:
            last_attempt_time = failed_attempts[ip_address]['time']
            time_diff = (datetime.now() - datetime.fromisoformat(last_attempt_time)).total_seconds()
            
            # 15 dakika boyunca kilitli tut
            if time_diff < 900:  # 15 dakika = 900 saniye
                error = "Çok fazla başarısız deneme. Lütfen 15 dakika sonra tekrar deneyin."
                return render_template('login.html', error=error), 429  # Too Many Requests
        
        # XSS koruması için girdiyi temizle
        username = username.strip()
        
        # SQL enjeksiyonuna karşı parametre kullanımı (zaten doğru yapılmış)
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, password, authority, status, name, surname FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        login_successful = False
        
        if user:
            if user[3] != "active":
                conn.close()
                error = "Giriş yetkiniz iptal edilmiş. Lütfen yönetici ile iletişime geçin."
                return render_template('login.html', error=error)
                
            if check_password_hash(user[1], password):
                login_successful = True
                # Başarılı giriş - başarısız deneme sayacını sıfırla
                if ip_address in failed_attempts:
                    del failed_attempts[ip_address]
                session['failed_attempts'] = failed_attempts
                
                session.permanent = True
                session['user'] = username
                session['user_id'] = user[0]
                session['authority'] = user[2] 
                session['full_name'] = f"{user[4]} {user[5]}" if user[4] and user[5] else username  # Ad ve soyad bilgisini kaydet
                session['logged_in'] = True
                session['last_activity'] = datetime.now().isoformat()  # Aktivite takibi
                
                # Aynı kullanıcının eski oturumlarını sil
                cursor.execute("DELETE FROM active_users WHERE user_id = ?", (user[0],))
                cursor.execute("""
                    INSERT INTO active_users (user_id, username, login_time) 
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user[0], username))
                
                # Güvenlik logu tut
                try:
                    cursor.execute("""
                        INSERT INTO login_logs (user_id, username, ip_address, success, timestamp)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (user[0], username, ip_address, 1))
                except sqlite3.OperationalError:
                    # Tablo yoksa oluştur ve tekrar dene
                    cursor.execute('''
                    CREATE TABLE IF NOT EXISTS login_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        username TEXT,
                        ip_address TEXT,
                        success INTEGER,
                        timestamp DATETIME
                    )
                    ''')
                    cursor.execute("""
                        INSERT INTO login_logs (user_id, username, ip_address, success, timestamp)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                    """, (user[0], username, ip_address, 1))
                
                conn.commit()
                conn.close()
                return redirect(url_for('menu'))
        
        # Başarısız giriş - sayacı artır
        conn.close()
        if not login_successful:
            if ip_address not in failed_attempts:
                failed_attempts[ip_address] = {'count': 1, 'time': datetime.now().isoformat()}
            else:
                failed_attempts[ip_address]['count'] += 1
                failed_attempts[ip_address]['time'] = datetime.now().isoformat()
                
            session['failed_attempts'] = failed_attempts
            
            # Güvenlik logu tut (failed attempt)
            try:
                conn = sqlite3.connect('users.db')
                cursor = conn.cursor()
                user_id = None
                if user:
                    user_id = user[0]
                cursor.execute("""
                    INSERT INTO login_logs (user_id, username, ip_address, success, timestamp)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                """, (user_id, username, ip_address, 0))
                conn.commit()
                conn.close()
            except Exception as e:
                pass  # Log tutma başarısız olsa bile giriş işlemine devam et
            
            # Genel hata mesajı (brute force'a karşı)
            error = "Kullanıcı adı veya şifre hatalı."
            return render_template('login.html', error=error)

    return render_template('login.html', message=request.args.get('message'))


@app.route('/', methods=['GET', 'POST'])
def menu():
    if 'user' not in session:
        return redirect(url_for('login'))  # Eğer oturum açılmamışsa login sayfasına yönlendir

    # Veritabanından verileri alıyoruz
    data = get_data_from_db()

    # Excel'den de veri alınıyor
    df = pd.read_excel('dgrtbl.xlsx', sheet_name='tbl1_1')
    options = {f'combobox{i}': df.iloc[:, i].dropna().tolist() for i in range(df.shape[1])}

    # Kullanıcı adının ilk harfi
    user_initial = session['user'][0].upper()  # Kullanıcı adının ilk harfini al ve büyük harfe çevir

    # Dosya yolundaki en büyük numaralı dosyayı bulma
    try:
        files = os.listdir(QUOTE_DB_PATH)
        numbered_files = [
            #(f, int(''.join(filter(str.isdigit, f)))) for f in files if f.startswith(f"{user_initial}Q_") and f.endswith(".db")
            (f, int(''.join(filter(str.isdigit, f)))) for f in files if  f.endswith(".db")
        ]
        
        # En büyük numarayı bul
        if numbered_files:
            largest_num = max(numbered_files, key=lambda x: x[1])[1]
            # En büyük numarayı bir artırarak yeni dosya ismini oluştur
            next_file_num = largest_num + 1
            #largest_file = f"{user_initial}Q_{next_file_num:08d}"  # 8 haneli sıfırlarla formatla
            largest_file = f"{next_file_num:08d}"  # 8 haneli sıfırlarla formatla
        else:
            # Kullanıcı için ilk dosyayı oluştur
            #largest_file = f"{user_initial}Q_00000001"
            largest_file = f"00000001"
    except Exception as e:
        largest_file = f"Error: {str(e)}"

    # Şablona veri gönderme
        # Kullanıcı bilgilerini şablona gönderiyoruz
    return render_template(
        'menu.html',
        user=session['user'],
        user_id=session.get('user_id', 'Unknown ID'),
        largest_file=largest_file,
        data=data,
        options=options
    )

@app.route('/logout')
def logout():
    global islmdvm
    islmdvm = 0
    user_id = session.get('user_id')
    if user_id:
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("DELETE FROM active_users WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()
    session.clear()
    return redirect(url_for('login'))

@app.route('/add_user', methods=['POST'])
def add_user():
    if 'user' not in session or session.get('authority') != 'admin':
        return redirect(url_for('login'))

    username = request.form['username']
    name = request.form['name']
    surname = request.form['surname']
    password = request.form['password']
    authority = request.form['authority']
    status = request.form['status']

    hashed_password = generate_password_hash(password)

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, name, surname, password, authority, status) VALUES (?, ?, ?, ?, ?, ?)",
        (username, name, surname, hashed_password, authority, status)
    )
    conn.commit()
    conn.close()
    return redirect(url_for('active_users'))
@app.route('/update_user', methods=['POST'])
def update_user():
    if 'user' not in session or session.get('authority') != 'admin':
        return '', 403
    data = request.get_json()
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    if data['password']:
        from werkzeug.security import generate_password_hash
        hashed_password = generate_password_hash(data['password'])
        cursor.execute(
            "UPDATE users SET username=?, name=?, surname=?, password=?, authority=?, status=? WHERE id=?",
            (data['username'], data['name'], data['surname'], hashed_password, data['authority'], data['status'], data['id'])
        )
    else:
        cursor.execute(
            "UPDATE users SET username=?, name=?, surname=?, authority=?, status=? WHERE id=?",
            (data['username'], data['name'], data['surname'], data['authority'], data['status'], data['id'])
        )
    conn.commit()
    conn.close()
    return '', 204

@app.route('/kick_user/<int:user_id>', methods=['POST'])
def kick_user(user_id):
    if 'user' not in session or session.get('authority') != 'admin':
        return '', 403
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM active_users WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    return '', 204

@app.route('/is_session_active')
def is_session_active():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'active': False})
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM active_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return jsonify({'active': bool(result)})

def is_user_kicked():
    user_id = session.get('user_id')
    if not user_id:
        return True
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM active_users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return not bool(result)

@app.before_request
def check_kicked():
    # login ve static gibi bazı endpointleri hariç tutmak için:
    if request.endpoint in ['login', 'static']:
        return
    # Oturum yoksa veya admin paneli ise atla
    if 'user' not in session:
        return
    if is_user_kicked():
        session.clear()
        # AJAX istekleri için JSON, normal istekler için redirect
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'logout': True, 'message': 'Oturum sonlandırıldı.'}), 401
        else:
            return redirect(url_for('login'))

@app.route('/active-users', methods=['GET'])
def active_users():
    if 'user' not in session or session.get('authority') != 'admin':
        return redirect(url_for('login'))

    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    # user_id de gelsin!
    cursor.execute("SELECT username, login_time, user_id FROM active_users")
    users = cursor.fetchall()
    cursor.execute("SELECT id, username, name, surname, password, authority, status FROM users")
    all_users = cursor.fetchall()
    conn.close()

    return render_template('active_users.html', users=users, all_users=all_users)


@app.route('/update_width', methods=['POST'])
def update_width():
    global islmdvm
    islmdvm = 1  # update_width fonksiyonu başladığında değeri 1 yap
    try:
        # Veritabanına bağlan ve cursor oluştur
        conn = sqlite3.connect('wall.db')
        cursor = conn.cursor()

        # Tüm alanları sıfırlama işlemi
        cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = 0, HEIGHT = 0, DEPTH = 0, ADET = 0, ITEM_NAME = NULL, UNIT_TYPE = NULL, SIRA = 0
        ''')
        cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = 0, HEIGHT = 0, DEPTH = 0, ADET = 0, ITEM_NAME = NULL, UNIT_TYPE = NULL, SIRA = 0
        ''')
        cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 0, DEPTH = 0, ADET = 0, ITEM_NAME = NULL, UNIT_TYPE = NULL, SIRA = 0
        ''')
        cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 0, DEPTH = 0, ADET = 0, ITEM_NAME = NULL, UNIT_TYPE = NULL, SIRA = 0
        ''')

        # Değişiklikleri geçici olarak kaydet
        conn.commit()

        # Gelen verileri al
        data = request.get_json()

        # Her bir alanı al, boş stringse varsayılan değeri kullan, ondalıklı değerleri tamsayıya dönüştür
        
        row_index = int(float(data.get('row_index', 0) or 0)) 
        # row_index = f"1.{row_index}"  # İstenilen formata dönüştür
        row_index = int(1000 + int(row_index))  # row_index artık "140"
        unit_piece = int(float(data.get('unit_piece', 0) or 0))  # Boşsa varsayılan olarak 1
        unit_type = str(data.get('unit_type', '') or '')
        height = int(float(data.get('height', 0) or 0))          # Boşsa varsayılan olarak 0
        width = int(float(data.get('width', 0) or 0))            # Boşsa varsayılan olarak 0
        base_shelf = int(float(data.get('base_shelf', 0) or 0))  # Boşsa varsayılan olarak 0
        qty = int(float(data.get('qty', 0) or 0))                # Boşsa varsayılan olarak 0
        shelf_size = int(float(data.get('shelf_size', 0) or 0))  # Boşsa varsayılan olarak 0

        # Eklenen yeni değerler
        qty_option8 = int(float(data.get('qty_option8', 0) or 0))
        shelf_size_option9 = int(float(data.get('shelf_size_option9', 0) or 0))
        qty_option10 = int(float(data.get('qty_option10', 0) or 0))
        shelf_size_option11 = int(float(data.get('shelf_size_option11', 0) or 0))
        plane40 = int(float(data.get('plane40', 0) or 0))
        perf40 = int(float(data.get('perf40', 0) or 0))
        plane30 = int(float(data.get('plane30', 0) or 0))
        perf30 = int(float(data.get('perf30', 0) or 0))
        plane20 = int(float(data.get('plane20', 0) or 0))
        perf20 = int(float(data.get('perf20', 0) or 0))
        plane10 = int(float(data.get('plane10', 0) or 0))
        perf10 = int(float(data.get('perf10', 0) or 0))
        largest_file = str(data.get('largest_file', '') or '')

        clean_string = largest_file.replace("Quotation Number: ", "").strip()
        #return clean_string

        if unit_type == "Wall Unit":

                # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri
            if width == 0 or base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (width, base_shelf, birshelf, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri
            if shelf_size == 0 or qty == 0:
                ikishelf = 0
            else:
                ikishelf = qty * unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece

            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, ucshelf, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, dortshelf, unit_type, row_index))

            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', (qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri

            if width == 0 or base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=1
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme
            if width == 0 or base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt, unit_type, row_index))        


            # 12. satırdaki Pilinth için width güncellemesi
            if width == 0 or base_shelf == 0:
                plntadt = 0  # birshelf değerini sıfırla
            else:
                plntadt=unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, plntadt, unit_type, row_index))

            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (width, plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (width, perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (width, plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (width, perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (width, plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (width, perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (width, plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (width, perf10 * unit_piece, unit_type, row_index))

            cursor.execute('''
            UPDATE wall_parca
            SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 22
            ''', (unit_piece, unit_type, row_index))
            
        elif unit_type == "End / Wall Unit":
            # Case 2: End / Wall Unit işlemleri
            # "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
                UPDATE wall_parca
                SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # "Baseleg" için Depth ve Adet güncelleme
            if  base_shelf == 0:
                legadt1 = 0  # birshelf değerini sıfırla
            else:
                legadt1=unit_piece
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt1, unit_type, row_index))

            cursor.execute('''
            UPDATE wall_parca
            SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 22
            ''', (unit_piece, unit_type, row_index))

        elif unit_type == "Double Gondola":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri
            if width == 0 or base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece*2

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (width, base_shelf, birshelf, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri

            if shelf_size == 0:
                ikishelf = 0  # birshelf değerini sıfırla
            else:
                ikishelf = qty * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece

            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, ucshelf, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece

            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, dortshelf, unit_type, row_index))

            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', (qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri

            if width == 0 or base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=2
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme

            if width == 0 or base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece*2
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt, unit_type, row_index))        

            # 12. satırdaki Pilinth için width güncellemesi

            if width == 0 or base_shelf == 0:
                plntadt = 0  # birshelf değerini sıfırla
            else:
                plntadt=unit_piece*2
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, plntadt, unit_type, row_index))

            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (width, plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (width, perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (width, plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (width, perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (width, plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (width, perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (width, plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (width, perf10 * unit_piece, unit_type, row_index))

            # cursor.execute('''
            # UPDATE wall_parca
            # SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            # WHERE rowid = 22
            # ''', (unit_piece, unit_type, row_index))

        elif unit_type == "End / Double Gondola":
            # Case 2: End / Wall Unit işlemleri
            # "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
                UPDATE wall_parca
                SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))


             # "Baseleg" için Depth ve Adet güncelleme
            if  base_shelf == 0:
                legadt1 = 0  # birshelf değerini sıfırla
            else:
                legadt1=unit_piece*2
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt1, unit_type, row_index))

        elif unit_type == "Single Gondola":

            if width == 0 or base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (width, base_shelf, birshelf, unit_type, row_index))



            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri
            if shelf_size == 0:
                ikishelf = 0  # birshelf değerini sıfırla
            else:
                ikishelf = qty * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, ucshelf, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, dortshelf, unit_type, row_index))

            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', (qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET DEPTH = (SELECT DEPTH FROM wall_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri
            if width == 0 or base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=1
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))


            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme
            if width == 0 or base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt, unit_type, row_index))        

            # 12. satırdaki Pilinth için width güncellemesi
            if width == 0 or base_shelf == 0:
                plntadt = 0  # birshelf değerini sıfırla
            else:
                plntadt=unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, plntadt, unit_type, row_index))

            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (width, plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (width, perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (width, plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (width, perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (width, plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (width, perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (width, plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (width, perf10 * unit_piece, unit_type, row_index))
            
            # # wall fix
            # cursor.execute('''  
            # UPDATE wall_parca
            # SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            # WHERE rowid = 22
            # ''', (unit_piece, unit_type, row_index))

        elif unit_type == "End / Single Gondola":
            # Case 2: End / Wall Unit işlemleri
            # "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
                UPDATE wall_parca
                SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # "Baseleg" için Depth ve Adet güncelleme
            if  base_shelf == 0:
                legadt1 = 0  # birshelf değerini sıfırla
            else:
                legadt1=unit_piece
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt1, unit_type, row_index))

        elif unit_type == "Vegetable Unit":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri

            if width == 0 or base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece

            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (width, base_shelf, birshelf, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri

            if shelf_size == 0 or qty == 0:
                ikishelf = 0  
            else:
                ikishelf = qty * unit_piece
            
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, ucshelf, unit_type, row_index))


            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, dortshelf, unit_type, row_index))


            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE veg_parca
            SET DEPTH = (SELECT DEPTH FROM veg_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', (qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET DEPTH = (SELECT DEPTH FROM veg_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET DEPTH = (SELECT DEPTH FROM veg_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri
            if width == 0 or base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=1
            cursor.execute('''
            UPDATE veg_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * ( birprc)), unit_type, row_index))
            # (width, (unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))
            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE veg_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme

            if width == 0 or base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece
            cursor.execute('''
            UPDATE veg_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt, unit_type, row_index)) 

            # 12. satırdaki Pilinth için width güncellemesi

            if width == 0 or base_shelf == 0:
                plntadt = 0  # birshelf değerini sıfırla
            else:
                plntadt=unit_piece
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, plntadt, unit_type, row_index))

            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (width, plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (width, perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (width, plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (width, perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (width, plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (width, perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (width, plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (width, perf10 * unit_piece, unit_type, row_index))

        elif unit_type == "End / Vegetable Unit":
            # Case 2: End / Wall Unit işlemleri
            # "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
                UPDATE veg_parca
                SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

             # "Baseleg" için Depth ve Adet güncelleme
            if  base_shelf == 0:
                legadt1 = 0  # birshelf değerini sıfırla
            else:
                legadt1=unit_piece
            cursor.execute('''
                UPDATE veg_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt1, unit_type, row_index))

        elif unit_type == "Internal Corner":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri

            if base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece

            cursor.execute('''
            UPDATE inter_parca
            SET  DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (base_shelf, birshelf, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri

            if shelf_size == 0 or qty == 0:
                ikishelf = 0  # birshelf değerini sıfırla
            else:
                ikishelf = qty * unit_piece
            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (shelf_size_option9, ucshelf, unit_type, row_index))


            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (shelf_size_option11, dortshelf, unit_type, row_index))


            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = (SELECT DEPTH FROM inter_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', ( qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = (SELECT DEPTH FROM inter_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET DEPTH = (SELECT DEPTH FROM inter_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri
            if base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=1
            cursor.execute('''
            UPDATE inter_parca
            SET adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Int. Corner Price Holder '
            ''', ((unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE inter_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece*2, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme

            if base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece
            cursor.execute('''
            UPDATE inter_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt*2, unit_type, row_index)) 

            # 12. satırdaki Pilinth için width güncellemesi



            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET  HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE inter_parca
            SET HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (perf10 * unit_piece, unit_type, row_index))

        elif unit_type == "External Corner":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri

            if base_shelf == 0:
                birshelf = 0  # birshelf değerini sıfırla
            else:
                birshelf = unit_piece

            cursor.execute('''
            UPDATE exter_parca
            SET  DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
             WHERE rowid = 1
            ''', (base_shelf, birshelf, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri

            if shelf_size == 0 or qty == 0:
                ikishelf = 0  # birshelf değerini sıfırla
            else:
                ikishelf = qty * unit_piece
            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = 0
            else:
                ucshelf = qty_option8 * unit_piece

            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (shelf_size_option9, ucshelf, unit_type, row_index))


            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * unit_piece
            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (shelf_size_option11, dortshelf, unit_type, row_index))


            # Bracket satırları için depth ayarları
            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = (SELECT DEPTH FROM exter_parca WHERE rowid = 2), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 5
            ''', ( qty * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = (SELECT DEPTH FROM exter_parca WHERE rowid = 3), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 6
            ''', (qty_option8 * 2 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET DEPTH = (SELECT DEPTH FROM exter_parca WHERE rowid = 4), ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 7
            ''', (qty_option10 * 2 * unit_piece, unit_type, row_index))

            # 5. "Price Holder" için Width ve Adet güncellemeleri
            if base_shelf == 0:
                birprc = 0  # birshelf değerini sıfırla
            else:
                birprc=1
            cursor.execute('''
            UPDATE exter_parca
            SET adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Ext. Corner Price Holder '
            ''', ((unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE exter_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme

            if base_shelf == 0:
                legadt = 0  # birshelf değerini sıfırla
            else:
                legadt=unit_piece
            cursor.execute('''
            UPDATE exter_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, legadt, unit_type, row_index)) 

            # 12. satırdaki Pilinth için width güncellemesi



            # 13-20 satırları için Back Panel ve Perforated Back Panel güncellemeleri
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 12
            ''', (plane40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET  HEIGHT = 40, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 13
            ''', (perf40  * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 14
            ''', (plane30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 30, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 15
            ''', (perf30 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 16
            ''', (plane20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 20, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 17
            ''', (perf20 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 18
            ''', (plane10 * unit_piece, unit_type, row_index))
            cursor.execute('''
            UPDATE exter_parca
            SET HEIGHT = 10, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 19
            ''', (perf10 * unit_piece, unit_type, row_index))

        else:
            # Farklı bir değer geldiğinde hata döndür
            conn.close()
            return jsonify({'message': 'Geçersiz UNIT_TYPE değeri.'}), 400

            # ITEM_NAME sütununu güncelleme: Birleştirilecek değerler
        cursor.execute('''
            UPDATE wall_parca
            SET ITEM_NAME = 
                CASE
                    WHEN UNIT_ITEMS IS NOT NULL THEN UNIT_ITEMS || ''
                    ELSE ''
                END ||
                CASE
                    WHEN WIDTH > 0 THEN '' || CAST(WIDTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN1 IS NOT NULL THEN '' || SIGN1 || ''
                    ELSE ''
                END ||       
                CASE
                    WHEN HEIGHT > 0 THEN '' || CAST(HEIGHT AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN2 IS NOT NULL THEN '' || SIGN2 || ''
                    ELSE ''
                END ||
                CASE
                    WHEN DEPTH > 0 THEN '' || CAST(DEPTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN EK IS NOT NULL THEN '' || EK || ''
                    ELSE ''
                END
        ''')

        cursor.execute('''
            UPDATE veg_parca
            SET ITEM_NAME = 
                CASE
                    WHEN UNIT_ITEMS IS NOT NULL THEN UNIT_ITEMS || ''
                    ELSE ''
                END ||
                CASE
                    WHEN WIDTH > 0 THEN '' || CAST(WIDTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN1 IS NOT NULL THEN '' || SIGN1 || ''
                    ELSE ''
                END ||       
                CASE
                    WHEN HEIGHT > 0 THEN '' || CAST(HEIGHT AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN2 IS NOT NULL THEN '' || SIGN2 || ''
                    ELSE ''
                END ||
                CASE
                    WHEN DEPTH > 0 THEN '' || CAST(DEPTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN EK IS NOT NULL THEN '' || EK || ''
                    ELSE ''
                END
        ''')
        cursor.execute('''
            UPDATE inter_parca
            SET ITEM_NAME = 
                CASE
                    WHEN UNIT_ITEMS IS NOT NULL THEN UNIT_ITEMS || ''
                    ELSE ''
                END ||
                CASE
                    WHEN WIDTH > 0 THEN '' || CAST(WIDTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN1 IS NOT NULL THEN '' || SIGN1 || ''
                    ELSE ''
                END ||       
                CASE
                    WHEN HEIGHT > 0 THEN '' || CAST(HEIGHT AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN2 IS NOT NULL THEN '' || SIGN2 || ''
                    ELSE ''
                END ||
                CASE
                    WHEN DEPTH > 0 THEN '' || CAST(DEPTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN EK IS NOT NULL THEN '' || EK || ''
                    ELSE ''
                END
        ''')
        cursor.execute('''
            UPDATE exter_parca
            SET ITEM_NAME = 
                CASE
                    WHEN UNIT_ITEMS IS NOT NULL THEN UNIT_ITEMS || ''
                    ELSE ''
                END ||
                CASE
                    WHEN WIDTH > 0 THEN '' || CAST(WIDTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN1 IS NOT NULL THEN '' || SIGN1 || ''
                    ELSE ''
                END ||       
                CASE
                    WHEN HEIGHT > 0 THEN '' || CAST(HEIGHT AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN SIGN2 IS NOT NULL THEN '' || SIGN2 || ''
                    ELSE ''
                END ||
                CASE
                    WHEN DEPTH > 0 THEN '' || CAST(DEPTH AS TEXT) || ''
                    ELSE ''
                END ||
                CASE
                    WHEN EK IS NOT NULL THEN '' || EK || ''
                    ELSE ''
                END
        ''')

        # Değişiklikleri kaydet
        conn.commit()
        
        create_quote_list(clean_string)

        response_message = f'Tüm gerekli güncellemeler başarıyla tamamlandı. Width değeri {width} olarak güncellendi.'

        # Bağlantıyı kapat
        conn.close()

        # İşlem sonucunu döndür
        return jsonify({
            'message': response_message,
            'updated_value': width
        }), 200

    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({'message': f'Hata: {str(e)}'}), 500
    except ValueError as e:
        print("Dönüşüm hatası:", str(e))
        return jsonify({'message': f'Dönüşüm hatası: {str(e)}'}), 400
    #finally:
        #islmdvm = 0  # İşlem tamamlandığında değeri tekrar 0 yap

@app.route('/clear_list_table', methods=['POST'])
def clear_list_table():
    try:
        # JSON verisini al
        data = request.get_json()
        db_name = data.get('db_name')  # Frontend'den gelen veritabanı adı

        if not db_name:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: db_name'}), 400

        # Veritabanı yolunu oluştur
        db_path = os.path.join(QUOTE_DB_PATH, f"{db_name}.db")

        # Veritabanına bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # `list` tablosunu temizle
        cursor.execute('DELETE FROM list')
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': f'{db_name} veritabanındaki list tablosu temizlendi.'})
    except Exception as e:
        print("Hata (clear_list_table):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

def create_quote_list(clean_string):
    try:
        # Hedef dizin
        os.makedirs(QUOTE_DB_PATH, exist_ok=True)
        new_file_name = f"{clean_string}.db"
        new_db_path = os.path.join(QUOTE_DB_PATH, new_file_name)

        # wall.db veritabanına bağlan
        conn = sqlite3.connect('wall.db')
        cursor = conn.cursor()

        # Yeni veritabanı ve tablo oluştur
        conn_quote = sqlite3.connect(new_db_path)
        cursor_quote = conn_quote.cursor()
        cursor_quote.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID INTEGER,
                ITEM_NAME TEXT,
                ADET INTEGER,
                UNIT_TYPE TEXT,
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2), -- Yeni kolon eklendi
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT 
            )
        ''')

        # wall.db'den verileri al ve filtrele (ADET > 0)
        cursor.execute('''
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM wall_parca
            WHERE ADET > 0
            UNION ALL
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM veg_parca
            WHERE ADET > 0
            UNION ALL
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM inter_parca
            WHERE ADET > 0
            UNION ALL
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM exter_parca
            WHERE ADET > 0
        ''')
        rows = cursor.fetchall()

        # Kullanıcı ve müşteri bilgilerini oturumdan al
        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır

        # prc_tbl veritabanına bağlan
        conn_prc = sqlite3.connect('prc_tbl.db')
        cursor_prc = conn_prc.cursor()
        
        # USER_ID'yi ekleyerek verileri düzenle
        rows_with_user_id = []
        for row in rows:
            item_name, adet, unit_type, sira = row

            # prc_tbl'deki name1 ile eşleşen satırı al (büyük/küçük harf ve boşlukları göz ardı ederek)
            cursor_prc.execute('''
                SELECT id, local, import, kg
                FROM prc_tbl
                WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
            ''', (item_name,))
            prc_row = cursor_prc.fetchone()

            if prc_row:
                item_id, local_price, import_price, kg = prc_row
            else:
                item_id, local_price, import_price, kg = 0, 0.0, 0.0, 0.0  # Eşleşme yoksa varsayılan değerler

            kg_tot = float(kg) * float(adet)  # KG toplamı
            # local_price = round(local_price, 2)  # Ensure 2 decimal places
            local_price = float(f"{local_price:.2f}")
            print(f"Eklenmeye çalışılan veri: {item_name}, adet={adet}, sira={sira}, eşleşen_id={item_id}")
            rows_with_user_id.append((user_id, item_id, item_name, adet, unit_type, sira, local_price, 0.00, 0.00, 0.00, import_price, kg_tot))

        # list tablosuna ekle
        cursor_quote.executemany('''
            INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', rows_with_user_id)

        # Değişiklikleri kaydet ve bağlantıları kapat
        conn_quote.commit()
        conn_quote.close()
        conn.close()
        conn_prc.close()

        color_to_db(clean_string)

        print(f"Quote list database created successfully: {new_db_path}")

    except sqlite3.Error as e:
        print("Veritabanı hatası (create_quote_list):", str(e))
    except Exception as e:
        print("Beklenmeyen hata (create_quote_list):", str(e))

def color_to_db(clean_string):
    db_path = os.path.join(QUOTE_DB_PATH, f"{clean_string}.db")
    color_db_path = os.path.join(BASE_DIR, "color_selections.db")
    prc_db_path = os.path.join(BASE_DIR, "prc_tbl.db")
    if not os.path.exists(db_path) or not os.path.exists(color_db_path) or not os.path.exists(prc_db_path):
        return

    # Renkleri çek
    conn_color = sqlite3.connect(color_db_path)
    c_color = conn_color.cursor()
    c_color.execute('''
        SELECT Shelf_color, Ticket_color, Slatwall
        FROM color_selections
        WHERE Quote_number = ?
    ''', (clean_string,))
    row = c_color.fetchone()
    conn_color.close()
    if not row:
        return
    shelf_color, ticket_color, slatwall_color = row

    # Listeyi güncelle
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        UPDATE list
        SET COLOUR = ?
        WHERE SIRA < 4300
          AND LOWER(ITEM_NAME) NOT LIKE '%price holder%'
          AND LOWER(ITEM_NAME) NOT LIKE '%riser%'
          AND LOWER(ITEM_NAME) NOT LIKE '%bar%'
          AND LOWER(ITEM_NAME) NOT LIKE '%worktop%'
    ''', (shelf_color,))
    c.execute('''
        UPDATE list
        SET COLOUR = ?
        WHERE SIRA < 4300
          AND LOWER(ITEM_NAME) LIKE '%price holder%'
    ''', (ticket_color,))
    c.execute('''
        UPDATE list
        SET COLOUR = ?
        WHERE SIRA >= 3500 AND SIRA < 4000
    ''', (slatwall_color,))
    conn.commit()

    # Her satır için prc_tbl'den item_id çek ve list tablosuna yaz
    c.execute('SELECT rowid, ITEM_NAME, COLOUR FROM list')
    rows = c.fetchall()
    prc_conn = sqlite3.connect(prc_db_path)
    prc_c = prc_conn.cursor()
    for rowid, item_name, colour in rows:
        # Önce renk eşleşen satırı ara
        prc_c.execute('''
            SELECT id FROM prc_tbl
            WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
              AND LOWER(COALESCE(Colour, '')) = LOWER(?)
        ''', (item_name, colour))
        prc_row = prc_c.fetchone()
        if prc_row:
            item_id = prc_row[0]
        else:
            # Renk eşleşmedi, renk boş olanı al
            prc_c.execute('''
                SELECT id FROM prc_tbl
                WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                  AND (Colour IS NULL OR Colour = '')
            ''', (item_name,))
            prc_row2 = prc_c.fetchone()
            item_id = prc_row2[0] if prc_row2 else 0
        c.execute('UPDATE list SET ITEM_ID = ? WHERE rowid = ?', (item_id, rowid))
    conn.commit()
    conn.close()
    prc_conn.close()

@app.route('/run_fytlndr', methods=['POST'])
def run_fytlndr():
    return jsonify({'status': 'error', 'message': 'fytlndr fonksiyonu kaldırıldı.'}), 400

@app.route('/apply_discount', methods=['POST'])
def apply_discount():
    try:
        # JSON verisini al
        data = request.get_json()
        quote_number = data.get('quote_number')
        dsc = data.get('dsc', 0)  # İndirim oranı (varsayılan %0)

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # Veritabanı yolunu oluştur
        db_path = os.path.join(QUOTE_DB_PATH, f"{quote_number}.db")

        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{quote_number} veritabanı bulunamadı.'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # IMPORT sütunu da dahil çekiyoruz
        cursor.execute('SELECT PRICE, ADET, SIRA, DSPRICE, IMPORT, DEPO FROM list')
        rows = cursor.fetchall()

        updated_rows = []
        for row in rows:
            price, adet, sira, dsprice, import_value, depo_value = row
            price = price or 0
            adet = adet or 0
            import_value = import_value or 0
            depo_value = depo_value or 0

            # Sıra numarası 1 ile başlıyorsa indirim uygula
            if sira < 7000:
                new_dsprice = round(price * (1 - dsc / 100), 2)
            else:
                new_dsprice = dsprice  # İndirim uygulanmaz

            amounth = round(adet * new_dsprice, 2)
            
            # Sıra 7000 ve 7200 arasında ise depo hesabı yapma
            if 7000 <= sira < 7299:
                
                depo = depo_value  # Eski değeri koru
            else:
                depo = round(adet * (new_dsprice - import_value), 2)

            updated_rows.append((new_dsprice, amounth, depo, price, adet, sira))

        # Şimdi DSPRICE, AMOUNTH ve DEPO alanlarını güncelle
        cursor.executemany('''
            UPDATE list
            SET DSPRICE = ?, AMOUNTH = ?, DEPO = ?
            WHERE PRICE = ? AND ADET = ? AND SIRA = ?
        ''', updated_rows)

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': f'{quote_number} için indirim ve depo hesaplaması uygulandı.'})

    except sqlite3.Error as e:
        print("Veritabanı hatası (apply_discount):", str(e))
        return jsonify({'status': 'error', 'message': f'Veritabanı hatası: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata (apply_discount):", str(e))
        return jsonify({'status': 'error', 'message': f'Beklenmeyen hata: {str(e)}'}), 500


@app.route('/prep_up_qt', methods=['POST'])
def call_prep_up_qt():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        dsc = data.get('dsc', 0)
        del_pr = data.get('del_pr', 0)
        Dpst = data.get('Dpst', 0)
        customer_id = data.get('customer_id')      # <-- eklendi
        customer_name = data.get('customer_name')  # <-- eklendi
        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        prep_up_qt(quote_number, dsc, del_pr, Dpst, customer_id, customer_name)  # <-- müşteri bilgilerini ilet

        return jsonify({'status': 'success', 'message': f'{quote_number} için prep_up_qt çağrıldı.'})
    except Exception as e:
        print(f"prep_up_qt endpoint hatası: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def prep_up_qt(clean_string, dsc, del_pr, Dpst, customer_id, customer_name):
    try:
        user_id = session.get('user_id', 0)
        user_name = session.get('user', 'Unknown User')
        # Artık müşteri bilgisi parametreden geliyor!
        update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc, del_pr, Dpst)
        print(f"prep_up_qt: {clean_string} için update_quotes_db çağrıldı.")
    except Exception as e:
        print(f"prep_up_qt sırasında hata oluştu: {str(e)}")

def update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc, del_pr, Dpst):
    try:
        # quotes.db dosyasının yolunu belirleyin
        quotes_db_path = os.path.join(BASE_DIR, "quotes.db")

        # customers.db'den postcode ve address bilgisini al
        conn_cust = sqlite3.connect(os.path.join(BASE_DIR, "customers.db"))
        cursor_cust = conn_cust.cursor()
        cursor_cust.execute("SELECT postcode, address FROM customers WHERE id = ?", (customer_id,))
        cust_row = cursor_cust.fetchone()
        conn_cust.close()
        postcode = cust_row[0] if cust_row else ""
        address1 = cust_row[1] if cust_row else ""

        # quotes.db veritabanını oluştur veya aç
        conn_quotes = sqlite3.connect(quotes_db_path)
        cursor_quotes = conn_quotes.cursor()

        # quotes tablosunu oluştur (eğer yoksa)
        cursor_quotes.execute('''
            CREATE TABLE IF NOT EXISTS quotes (
                Quote_number TEXT NOT NULL,
                User_id INTEGER NOT NULL,
                User_name TEXT NOT NULL,
                Customer_id TEXT,
                Customer_name TEXT,
                Posct_code TEXT,      -- Yeni kolon 1
                Address1 TEXT,        -- Yeni kolon 2
                Discount DECIMAL(10, 2),
                Amount DECIMAL(10, 2) NOT NULL,
                Sold TEXT,
                Inv TEXT,
                created_at TEXT DEFAULT (strftime('%d-%m-%Y %H:%M:%S', 'now', 'localtime')),
                Delpr INTEGER DEFAULT 0,
                Deposit REAL DEFAULT 0.0
            )
        ''')

        # Oluşturulan veritabanının yolunu belirleyin
        new_db_path = os.path.join(QUOTE_DB_PATH, f"{clean_string}.db")

        # Oluşturulan veritabanına bağlan
        conn_new_db = sqlite3.connect(new_db_path)
        cursor_new_db = conn_new_db.cursor()

        # Amount sütunundaki değerlerin toplamını hesapla
        cursor_new_db.execute('SELECT SUM(AMOUNTH) FROM list')
        total_amount = cursor_new_db.fetchone()[0] or 0.0

        # Sunucunun tarih ve saatini al
        current_time1 = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

        # `Quote_number` zaten var mı kontrol et
        cursor_quotes.execute('SELECT COUNT(*) FROM quotes WHERE Quote_number = ?', (clean_string,))
        quote_exists = cursor_quotes.fetchone()[0] > 0

        if quote_exists:
            # Eğer `Quote_number` zaten varsa, satırı güncelle
            cursor_quotes.execute('''
                UPDATE quotes
                SET User_id = ?, User_name = ?, Customer_id = ?, Customer_name = ?, Posct_code = ?, Address1 = ?, Discount = ?, Amount = ?, Sold = ?, Inv = ?, created_at = ?, Delpr= ?, Deposit= ?
                WHERE Quote_number = ?
            ''', (user_id, user_name, customer_id, customer_name, postcode, address1, dsc, total_amount, '', '', current_time1, del_pr, Dpst, clean_string))
            print(f"Quotes database updated for existing Quote_number: {clean_string}")
        else:
            # Eğer `Quote_number` yoksa, yeni bir satır ekle
            cursor_quotes.execute('''
                INSERT INTO quotes (Quote_number, User_id, User_name, Customer_id, Customer_name, Posct_code, Address1, Discount, Amount, Sold, Inv, created_at, Delpr, Deposit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (clean_string, user_id, user_name, customer_id, customer_name, postcode, address1, dsc, total_amount, '', '', current_time1, del_pr, Dpst))
            print(f"Quotes database inserted new Quote_number: {clean_string}")

        # Değişiklikleri kaydet ve bağlantıları kapat
        conn_quotes.commit()
        conn_new_db.close()
        conn_quotes.close()

    except sqlite3.Error as e:
        print("Veritabanı hatası (update_quotes_db):", str(e))
    except Exception as e:
        print("Beklenmeyen hata (update_quotes_db):", str(e))

def get_data_from_db():
    # SQLite veritabanına bağlan
    conn = sqlite3.connect('wall.db')
    cursor = conn.cursor()
    
    # Tüm tablo isimlerini al
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    data = {}
    for table_name in tables:
        table_name = table_name[0]
        
        # Her tablodan verileri al
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        
        # Tablo sütun adlarını al
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Verileri ve sütunları 'data' sözlüğüne ekle
        data[table_name] = {"columns": columns, "rows": rows}
    
    conn.close()
    return data  # Verileri döndür


@app.route('/get_quotes', methods=['GET'])
def get_quotes():
    try:
        # quotes.db veritabanına bağlan
        quotes_db_path = os.path.join(BASE_DIR, "quotes.db")
        conn = sqlite3.connect(quotes_db_path)
        cursor = conn.cursor()

        # Kullanıcı yetkisini session'dan al
        user_id = session.get('user_id')
        authority = session.get('authority', 'user')

        # Yetkiye göre filtre uygula
        if authority in ['admin', 'poweruser']:
            cursor.execute('SELECT * FROM quotes')
        else:
            cursor.execute('SELECT * FROM quotes WHERE User_id = ?', (user_id,))

        rows = cursor.fetchall()

        # Sütun adlarını al
        cursor.execute('PRAGMA table_info(quotes)')
        columns = [col[1] for col in cursor.fetchall()]

        conn.close()

        # Verileri JSON formatında döndür
        return jsonify({'columns': columns, 'rows': rows})
    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({'error': f'Hata: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata:", str(e))
        return jsonify({'error': f'Beklenmeyen hata: {str(e)}'}), 500

@app.route('/get_quote_list', methods=['GET'])
def get_quote_list():
    global islmdvm
    islmdvm = 1
    try:
        db_name = request.args.get('db_name')
        if not db_name:
            return jsonify({'message': 'Veritabanı adı sağlanmadı.'}), 400

        if not db_name.endswith('.db'):
            db_file = db_name + '.db'
        else:
            db_file = db_name
        db_path = os.path.join(QUOTE_DB_PATH, db_file)

        if not os.path.exists(db_path):
            return jsonify({'message': f'{db_file} dosyası bulunamadı.'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # rowid dahil tüm verileri sıraya göre çek
        cursor.execute('''
            SELECT USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, rowid
            FROM list
            ORDER BY CAST(SIRA AS DECIMAL(10, 2)) ASC
        ''')
        rows = cursor.fetchall()
        conn.close()

        return jsonify({'db_name': db_name, 'data': rows})

    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({'message': f'Hata: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata:", str(e))
        return jsonify({'message': f'Beklenmeyen hata: {str(e)}'}), 500
    finally:
        islmdvm = 0


@app.route('/add_item_data', methods=['POST'])
def add_item_data():
    try:
        data = request.get_json()
        add_item_data = data.get('add_item_data', [])
        largest_file = str(data.get('largest_file', '') or '').replace("Quotation Number: ", "").strip()

        # Eğer veri gelmemişse hata döndür
        if not add_item_data:
            return jsonify({"status": "error", "message": "Hiçbir veri alınmadı."}), 400
        
        # Hedef veritabanı dosyası
        new_db_path = os.path.join(QUOTE_DB_PATH, f"{largest_file}.db")
        sr = 9000
        item_id=101
        # Yeni veritabanı bağlantısı
        conn_quote = sqlite3.connect(new_db_path)
        cursor_quote = conn_quote.cursor()

        # `list` tablosunu oluştur (zaten varsa hata vermez)
        cursor_quote.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID INTEGER PRIMARY KEY AUTOINCREMENT,
                ITEM_NAME TEXT NOT NULL,
                ADET INTEGER NOT NULL,
                UNIT_TYPE TEXT DEFAULT 'ADD_ITEM',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2), -- Yeni kolon eklendi
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT 
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır

        # USER_ID'yi ekleyerek verileri düzenle
        #rows_with_user_id = [(user_id, *row) for row in rows]

        # Gelen verileri işleyip tabloya ekle
        for item in add_item_data:
            item_name = item.get('itemName', '').strip()
            sr = round(sr + 1, 0)  # SR'yi 0.1 artır ve ondalık hassasiyetini koru
            qty = int(item.get('qty', 0))  # Sayısal değer olarak kaydet
            price = float(item.get('price', 0))  # Sayısal değer olarak kaydet
            dsprice = float(item.get('dsprice', 0))  # Sayısal değer olarak kaydet
            item_id = int(item_id + 1)

            # Kar değerini metin olarak al ve içinden sadece rakamsal kısmı ayıkla
            kar_text = str(item.get('kar', '0')).strip()
            kar_match = re.search(r'\d+(\.\d+)?', kar_text)  # Rakamsal kısmı bul

            if kar_match:
                kar_value = float(kar_match.group())  # Eşleşen değeri float olarak al
                print(f"Kar değeri (ayıklandı): {kar_value}")
            else:
                print(f"Kar değeri bulunamadı: {kar_text}")
                kar_value = 0.0  # Eğer rakam yoksa varsayılan 0.0 olarak al

            cursor_quote.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                VALUES (?, ?, ?, ?, 'ADD_ITEM', ?, ?, ?, ?, ?, ?)                 


            ''', (user_id, item_id, item_name, qty, sr, price, dsprice, qty*dsprice, qty*kar_value, dsprice-kar_value))      #, price, dsprice))

         

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn_quote.commit()
        conn_quote.close()

        return jsonify({"status": "success", "message": "Veri başarıyla kaydedildi!"})
    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({"status": "error", "message": f"Veritabanı hatası: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Beklenmeyen hata: {str(e)}"}), 500

@app.route("/fetch_customers", methods=["GET"])
def fetch_customers():
    connection = sqlite3.connect("customers.db")
    cursor = connection.cursor()
    # cursor.execute("SELECT id, customer_name, tel, address1, address2, postcode FROM customers")
    cursor.execute("SELECT id, customer_name, tel, address, address2, postcode FROM customers")
    customers = cursor.fetchall()
    connection.close()
    return jsonify(customers)

# @app.route("/fetch_customers_dlvr", methods=["GET"])
# def fetch_customers_dlvr():
#     connection = sqlite3.connect("prf_adr_dlvr.db")
#     cursor = connection.cursor()
#     cursor.execute("SELECT id, customer_name, tel, address, postcode FROM customers")
#     cursor.execute('SELECT name, tel, address, address1, postcode, Dname, Dtel, Daddress, Daddress1, Dpostcode WHERE Quote_number = ?', (quote_number,))
#     customers = cursor.fetchall()
#     connection.close()
#     return jsonify(customers)

@app.route('/get_quote_files', methods=['GET'])
def get_quote_files():
    quotes_dir = './quotes'  # Quotes klasörünün yolu
    try:
        # .db uzantılı dosyaları seç
        files = [f for f in os.listdir(quotes_dir) if f.endswith('.db')]

        # Eğer hiç dosya yoksa "00000000.db" döndür
        if not files:
            return jsonify(["00000000.db"])

        # Dosya listesini döndür
        return jsonify(files)
    except Exception as e:
        # Hata durumunda hata mesajını döndür
        return jsonify({'error': str(e)}), 500
    
@app.route('/get_server_time', methods=['GET'])
def get_server_time():
    try:
        # Sunucunun tarih ve saatini al
        # current_time = datetime.now().strftime('%d-%m-%Y')
        # current_dtime = datetime.now().strftime('%d-%m-%Y %H:%M:%S')
        current_time = datetime.now().strftime('%d-%m-%y %H:%M:%S')
        return jsonify({'status': 'success', 'server_time': current_time})
    except Exception as e:
        print("Hata:", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500  
      

@app.route('/save_unite_selection', methods=['POST'])
def save_unite_selection():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        selections = data.get('selections')  # Unite sayfasındaki seçimler

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "unite_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS unite_selections (
                Quote_number TEXT NOT NULL,
                Row_index INTEGER NOT NULL,
                Selection_data TEXT NOT NULL,
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM unite_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        for row_index, selection in enumerate(selections):
            cursor.execute('''
                INSERT INTO unite_selections (Quote_number, Row_index, Selection_data)
                VALUES (?, ?, ?)
            ''', (quote_number, row_index, json.dumps(selection)))  # Tüm seçimleri JSON olarak kaydedin

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Seçimler kaydedildi.'})
    except Exception as e:
        print("Hata (save_unite_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/load_unite_selection', methods=['GET'])
def load_unite_selection():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "unite_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Seçimleri al
        cursor.execute('SELECT Row_index, Selection_data FROM unite_selections WHERE Quote_number = ?', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        # Seçimleri JSON formatında döndür
        selections = {row[0]: json.loads(row[1]) for row in rows}
        return jsonify({'status': 'success', 'selections': selections})
    except Exception as e:
        print("Hata (load_unite_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500  


@app.route('/get_customer_by_quote', methods=['GET'])
def get_customer_by_quote():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # quotes.db veritabanına bağlan
        quotes_db_path = os.path.join(BASE_DIR, "quotes.db")
        conn_quotes = sqlite3.connect(quotes_db_path)
        cursor_quotes = conn_quotes.cursor()

        # Quote'a ait Customer ID'yi al
        cursor_quotes.execute('''
            SELECT Customer_id
            FROM quotes
            WHERE Quote_number = ?
        ''', (quote_number,))
        customer_id_row = cursor_quotes.fetchone()
        conn_quotes.close()

        if not customer_id_row:
            return jsonify({'status': 'error', 'message': f'Quote_number {quote_number} ile ilişkili müşteri bulunamadı.'}), 404

        # Customer ID'yi 7 karakter uzunluğunda sıfırlarla doldur
        # customer_id = str(customer_id_row[0]).zfill(7)
        # print(repr(customer_id_row[0]))
        customer_id = customer_id_row[0]

        # customers.db veritabanına bağlan
        customers_db_path = os.path.join(BASE_DIR, "customers.db")
        conn_customers = sqlite3.connect(customers_db_path)
        cursor_customers = conn_customers.cursor()

        # Customer ID'ye göre müşteri bilgilerini al
        cursor_customers.execute('''
            SELECT id, customer_name, tel, address, address2, postcode
            FROM customers
            WHERE id = ?
        ''', (customer_id,))
        customer = cursor_customers.fetchone()
        conn_customers.close()

        if not customer:
            return jsonify({'status': 'error', 'message': f'Customer_id {customer_id} ile ilişkili müşteri bulunamadı.'}), 404
        

        # Müşteri bilgilerini JSON formatında döndür
        return jsonify({
            'status': 'success',
            'customer_id': customer[0],
            'customer_name': customer[1],
            'tel': customer[2],
            'address1': customer[3],
            'address2': customer[4],
            'postcode': customer[5]
        })
    except Exception as e:
        print("Hata (get_customer_by_quote):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/save_aditm_selection', methods=['POST'])
def save_aditm_selection():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number') if isinstance(data, dict) else None
        selections = data.get('selections') if isinstance(data, dict) else data  # Eğer data bir listeyse doğrudan kullan

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "aditm_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu yeniden oluştur (eksik sütunları eklemek için)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS aditm_selections (
                Quote_number TEXT NOT NULL,
                Row_index INTEGER NOT NULL,
                Item_name TEXT DEFAULT '',  -- Eksik sütun eklendi
                Quantity INTEGER DEFAULT 0,
                Price REAL DEFAULT 0.0,
                Discounted_price REAL DEFAULT 0.0,
                Depo_code TEXT DEFAULT '',
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM aditm_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        for row_index, selection in enumerate(selections):
            cursor.execute('''
                INSERT INTO aditm_selections (Quote_number, Row_index, Item_name, Quantity, Price, Discounted_price, Depo_code)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (
                quote_number,
                row_index,
                selection[0] if len(selection) > 0 else '',  # Item_name
                int(selection[1]) if len(selection) > 1 and selection[1] else 0,  # Quantity
                float(selection[2]) if len(selection) > 2 and selection[2] else 0.0,  # Price
                float(selection[3]) if len(selection) > 3 and selection[3] else 0.0,  # Discounted_price
                selection[4] if len(selection) > 4 else ''  # Depo_code
            ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Add Item seçimleri kaydedildi.'})
    except Exception as e:
        print("Hata (save_aditm_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/load_aditm_selection', methods=['GET'])
def load_aditm_selection():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "aditm_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Seçimleri al
        cursor.execute('''
            SELECT Row_index, Item_name, Quantity, Price, Discounted_price, Depo_code
            FROM aditm_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        # Seçimleri JSON formatında döndür
        selections = [
            {
                'row_index': row[0],
                'item_name': row[1],
                'quantity': row[2],
                'price': row[3],
                'discounted_price': row[4],
                'depo_code': row[5]
            }
            for row in rows
        ]
        # print("Geri gönderilen veriler:", selections)  # Geri gönderilen veriyi yazdır
        return jsonify({'status': 'success', 'selections': selections})
    except Exception as e:
        print("Hata (load_aditm_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_refrigeration_groups', methods=['GET'])
def get_refrigeration_groups():
    try:
        conn = sqlite3.connect('refrigeration.db')
        cursor = conn.cursor()
        # "GroupName" sütun adı kullanıldı
        cursor.execute('SELECT DISTINCT "GroupName" FROM REFRIGERATION')
        groups = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'groups': groups})
    except Exception as e:
        print("Hata (get_refrigeration_groups):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_refrigeration_items', methods=['GET'])
def get_refrigeration_items():
    try:
        group = request.args.get('group')
        if not group:
            return jsonify({'status': 'error', 'message': 'Group parametresi eksik.'}), 400

        conn = sqlite3.connect('refrigeration.db')
        cursor = conn.cursor()
        # "GroupName" sütun adı kullanıldı
        cursor.execute('SELECT Model FROM REFRIGERATION WHERE "GroupName" = ?', (group,))
        items = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'items': items})
    except Exception as e:
        print("Hata (get_refrigeration_items):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_refrigeration_price', methods=['GET'])
def get_refrigeration_price():
    try:
        model_name = request.args.get('model')
        customer_type = request.args.get('customer_type')
        if not model_name or not customer_type:
            return jsonify({'status': 'error', 'message': 'Model veya müşteri tipi eksik.'}), 400

        conn = sqlite3.connect('refrigeration.db')
        cursor = conn.cursor()

        # Müşteri tipine göre fiyat sütununu seç
        if customer_type == "Retail":
            cursor.execute('SELECT RetailPrice FROM REFRIGERATION WHERE Model = ?', (model_name,))
        elif customer_type == "Trade":
            cursor.execute('SELECT TradePrice FROM REFRIGERATION WHERE Model = ?', (model_name,))
        else:
            return jsonify({'status': 'error', 'message': 'Geçersiz müşteri tipi.'}), 400

        result = cursor.fetchone()
        conn.close()

        if result:
            price = result[0]
            # print(f"Customer Type: {customer_type}, Model: {model_name}, Price: {price}")  # Yeni print ifadesi
            return jsonify({'status': 'success', 'price': price})
        else:
            return jsonify({'status': 'error', 'message': 'Model bulunamadı.'}), 404
    except Exception as e:
        print("Hata (get_refrigeration_price):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_refrigeration_item_details', methods=['GET'])
def get_refrigeration_item_details():
    try:
        model_name = request.args.get('model')
        if not model_name:
            return jsonify({'status': 'error', 'message': 'Model adı belirtilmedi.'}), 400

        conn = sqlite3.connect('refrigeration.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT Warranty, UnpackPosition, RemoveDispose, TradePrice, Kar
            FROM REFRIGERATION
            WHERE Model = ?
        ''', (model_name,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return jsonify({
                'status': 'success',
                'warranty': result[0],
                'unpack': result[1],
                'remove': result[2],
                'tradePrice': result[3],
                'kar': result[4]
            })
        else:
            return jsonify({'status': 'error', 'message': 'Model bulunamadı.'}), 404
    except Exception as e:
        print("Hata (get_refrigeration_item_details):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500
    


@app.route('/add_ref_data', methods=['POST'])
def add_ref_data():
    try:
        data = request.get_json()
        ref_data = data.get('ref_data', [])
        largest_file = str(data.get('largest_file', '')).strip()

        # Eğer veri gelmemişse hata döndür
        if not ref_data:
            return jsonify({"status": "error", "message": "Geçerli veri yok."}), 400

        # Hedef veritabanı dosyası
        new_db_path = os.path.join(QUOTE_DB_PATH, f"{largest_file}.db")

        # Yeni veritabanı bağlantısı
        conn_quote = sqlite3.connect(new_db_path)
        cursor_quote = conn_quote.cursor()

        # `list` tablosunu oluştur (zaten varsa hata vermez)
        cursor_quote.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID TEXT NOT NULL,
                ITEM_NAME TEXT NOT NULL,
                ADET INTEGER NOT NULL,
                UNIT_TYPE TEXT DEFAULT 'ADD_ITEM',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2), -- Yeni kolon eklendi
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT 
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        sira = 7000  # Sıra değeri başlangıç

        # Gelen verileri işleyip tabloya ekle
        for item in ref_data:
            sku = item.get('sku', '')
            quantity = item.get('quantity', 0)
            dprice = item.get('dprice', 0.0)

            xtra = item.get('xtra', 0.0)
            
            # print(f"xtra değeri: {xtra}")  # <-- xtra değerini ekrana yazdır

            # SKU'dan `-` karakterinden önceki rakamsal değeri al
            import_value = 0.0
            if '-' in sku:
                parts = sku.split('-')
                prefix = parts[0].strip()  # `-` karakterinden önceki kısmı al ve boşlukları temizle
                suffix = parts[1].strip()  # `-` karakterinden sonraki kısmı al ve boşlukları temizle

                # Önceki ve sonraki rakamları ayıkla
                match_prefix = re.search(r'\d+', prefix)  # Önceki rakamları ayıkla
                match_suffix = re.search(r'\d+', suffix)  # Sonraki rakamları ayıkla

                if match_prefix and match_suffix:
                    prefix_value = float(match_prefix.group())  # Önceki rakam
                    suffix_value = float(match_suffix.group())  # Sonraki rakam
                    import_value = prefix_value - suffix_value  # Farkı hesapla
            depo = quantity*((dprice-import_value)-xtra)

            # print(f"depo değeri: {depo}")  # <-- depo değerini ekrana yazdır


            cursor_quote.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                sku,
                item.get('itemName', ''),
                quantity,
                item.get('unitType', 'Add Refrigeration'),
                round(sira, 2),  # Sıra değeri
                item.get('price', 0.0),
                dprice,
                item.get('quantity', 0) * item.get('dprice', 0.0),  # AMOUNTH hesaplama
                depo,
                import_value  # SKU'dan alınan import değeri
            ))
            sira += 1  # Sıra değerini artır
            # print(f"SKU: {sku}, Import Value: {import_value}")  # Yeni print ifadesi
        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn_quote.commit()
        conn_quote.close()

        return jsonify({"status": "success", "message": "Refrigeration verileri başarıyla kaydedildi!"})
    except sqlite3.Error as e:
        print("Veritabanı hatası (add_ref_data):", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print("Beklenmeyen hata (add_ref_data):", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/save_ref_selection', methods=['POST'])
def save_ref_selection():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        customer_type = data.get('customer_type')  # Customer type değeri
        ref_dsc = data.get('ref_dsc')  # Ref_dsc değeri
        selections = data.get('selections')  # Refrigeration sayfasındaki seçimler

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "ref_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ref_selections (
                Quote_number TEXT NOT NULL,
                Customer_type TEXT DEFAULT '',
                Ref_dsc REAL DEFAULT 0.0,
                Row_index INTEGER NOT NULL,
                Group_name TEXT DEFAULT '',
                Item_name TEXT DEFAULT '',
                Warranty INTEGER DEFAULT '',
                Unpack INTEGER DEFAULT '',
                Remove INTEGER DEFAULT '',
                Quantity INTEGER DEFAULT 0,
                Price REAL DEFAULT 0.0,
                Discounted_price REAL DEFAULT 0.0,
                Discount REAL DEFAULT 0.0,           -- <--- EKLENDİ
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM ref_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        for row_index, selection in enumerate(selections):
            cursor.execute('''
                INSERT INTO ref_selections (Quote_number, Customer_type, Ref_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price, Discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                quote_number,
                customer_type,
                float(ref_dsc) if ref_dsc else 0.0,
                row_index,
                selection.get('group_name', ''),
                selection.get('item_name', ''),
                selection.get('warranty', ''),
                selection.get('unpack', ''),
                selection.get('remove', ''),
                int(selection.get('quantity', 0)),
                float(selection.get('price', 0.0)),
                float(selection.get('discounted_price', 0.0)),
                float(selection.get('discount', 0.0))   # <--- EKLENDİ
            ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Refrigeration seçimleri kaydedildi.'})
    except Exception as e:
        print("Hata (save_ref_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/load_ref_selection', methods=['GET'])
def load_ref_selection():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "ref_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Seçimleri al (Discount alanını da çek!)
        cursor.execute('''
            SELECT Customer_type, Ref_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price, Discount
            FROM ref_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        # İlk satırdan customer_type ve ref_dsc değerlerini al
        customer_type = rows[0][0] if rows else ''
        ref_dsc = rows[0][1] if rows else 0.0

        # Seçimleri JSON formatında döndür (Discount'u da ekle)
        selections = [
            {
                'row_index': row[2],
                'group_name': row[3],
                'item_name': row[4],
                'warranty': row[5],
                'unpack': row[6],
                'remove': row[7],
                'quantity': row[8],
                'price': row[9],
                'discounted_price': row[10],
                'discount': row[11] if len(row) > 11 else 0  # Discount alanı
            }
            for row in rows
        ]
        return jsonify({
            'status': 'success',
            'customer_type': customer_type,
            'ref_dsc': ref_dsc,
            'selections': selections
        })
    except Exception as e:
        print("Hata (load_ref_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/add_woods_data', methods=['POST'])
def add_woods_data():
    try:
        data = request.get_json()
        woods_data = data.get('woods_data', [])
        largest_file = str(data.get('largest_file', '')).strip()

        if not woods_data:
            return jsonify({"status": "error", "message": "No data provided"}), 400

        db_path = os.path.join(QUOTE_DB_PATH, f"{largest_file}.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID TEXT,
                ITEM_NAME TEXT,
                ADET INTEGER,
                UNIT_TYPE TEXT DEFAULT 'WOOD',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2),         
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT  
            )
        ''')

        user_id = session.get('user_id', 0)
        sira = 4500

        # Wood DB bağlantısı
        wood_conn = sqlite3.connect('wood.db')
        wood_cursor = wood_conn.cursor()

        for item in woods_data:
            item_name = item.get('item', '')
            qty = int(item.get('quantity', 0))
            # wood_tbl'den import ve kg değerini çek
            wood_cursor.execute('SELECT IMPORT, KG FROM wood_tbl WHERE ITEM_NAME = ?', (item_name,))
            wood_row = wood_cursor.fetchone()
            import_value = wood_row[0] if wood_row else 0
            kg_value = wood_row[1] if wood_row else 0
            kg_total = float(kg_value) * qty

            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                item.get('sku', ''),
                item_name,
                qty,
                'WOOD',
                sira,
                float(item.get('price', 0)),
                float(item.get('dprice', 0)),
                qty * float(item.get('dprice', 0)),
                0, import_value, kg_total
            ))
            sira += 1

        wood_conn.close()
        conn.commit()
        conn.close()
        return jsonify({"status": "success", "message": "Woods verileri başarıyla kaydedildi!"})
    except Exception as e:
        print("Woods API Hatası:", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/get_woods_groups', methods=['GET'])
def get_woods_groups():
    import sqlite3
    conn = sqlite3.connect('wood.db')
    cursor = conn.cursor()
    cursor.execute('SELECT DISTINCT G_NAME FROM wood_tbl WHERE G_NAME IS NOT NULL AND G_NAME != ""')
    groups = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'groups': groups})

@app.route('/get_woods_items', methods=['GET'])
def get_woods_items():
    import sqlite3
    group = request.args.get('group')
    conn = sqlite3.connect('wood.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ITEM_NAME FROM wood_tbl WHERE G_NAME = ?', (group,))
    items = [row[0] for row in cursor.fetchall()]
    conn.close()
    return jsonify({'items': items})

@app.route('/get_woods_item_details', methods=['GET'])
def get_woods_item_details():
    import sqlite3
    item = request.args.get('item')
    conn = sqlite3.connect('wood.db')
    cursor = conn.cursor()
    cursor.execute('SELECT LOCAL, TRADE_PRICE, KOD FROM wood_tbl WHERE ITEM_NAME = ?', (item,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return jsonify({'local_price': row[0], 'trade_price': row[1], 'sku': row[2]})
    else:
        return jsonify({'local_price': 0, 'trade_price': 0, 'sku': ''})

@app.route('/save_woods_selection', methods=['POST'])
def save_woods_selection():
    import sqlite3
    data = request.get_json()
    quote_number = data.get('quote_number')
    customer_type = data.get('customer_type', 'Retail')
    selections = data.get('selections', [])

    db_path = os.path.join(BASE_DIR, "woods_selections.db")
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS woods_selections (
                Quote_number TEXT NOT NULL,
                Row_index INTEGER NOT NULL,
                Group_name TEXT,
                Item_name TEXT,
                Quantity INTEGER,
                Price REAL,
                Dprice REAL,
                SKU TEXT,
                Customer_type TEXT,
                Woods_discount REAL,  -- Her satırın kendi discount'u
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')
        cursor.execute('DELETE FROM woods_selections WHERE Quote_number = ?', (quote_number,))
        for idx, sel in enumerate(selections):
            quantity = int(sel.get('quantity', 0) or 0)
            price = float(sel.get('price', 0) or 0)
            dprice = float(sel.get('dprice', 0) or 0)
            woods_discount = float(sel.get('discount', 0) or 0)  # Her satırın kendi discount'u
            cursor.execute('''
                INSERT INTO woods_selections (Quote_number, Row_index, Group_name, Item_name, Quantity, Price, Dprice, SKU, Customer_type, Woods_discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                quote_number, idx, sel.get('group', ''), sel.get('item', ''), quantity, price, dprice, sel.get('sku', ''), customer_type, woods_discount
            ))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Woods seçimleri kaydedildi.'})
    except Exception as e:
        print("save_woods_selection Hatası:", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/load_woods_selection', methods=['GET'])
def load_woods_selection():
    import sqlite3
    quote_number = request.args.get('quote_number')
    db_path = os.path.join(BASE_DIR, "woods_selections.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT Group_name, Item_name, Quantity, Price, Dprice, SKU, Customer_type, Woods_discount
        FROM woods_selections
        WHERE Quote_number = ?
        ORDER BY Row_index ASC
    ''', (quote_number,))
    rows = cursor.fetchall()
    conn.close()
    selections = [
        {
            'group': row[0],
            'item': row[1],
            'quantity': row[2],
            'price': row[3],
            'dprice': row[4],
            'sku': row[5],
            'discount': row[7]  # Her satırın discount'u
        }
        for row in rows
    ]
    customer_type = rows[0][6] if rows else 'Retail'
    return jsonify({'status': 'success', 'selections': selections, 'customer_type': customer_type})


@app.route('/calculate_ceiling_qty', methods=['POST'])
def calculate_ceiling_qty():
    try:
        data = request.get_json()
        ceiling_m2 = float(data.get('ceilingM2', 0))
        trim_lm = float(data.get('trimLM', 0))
        ceil_dsc = float(data.get('ceil_dsc', 0))  # ceil_dsc değerini al
        ceiling_colour = data.get('ceilingColour', '')  # Renk seçimi (White/Black/'')

        # ceiling.db veritabanına bağlan
        conn = sqlite3.connect('ceiling.db')
        cursor = conn.cursor()

        # ceiling tablosundaki tüm verileri al
        cursor.execute('SELECT Code, Materials, Notes, Local FROM ceiling_data')
        ceiling_data = cursor.fetchall()
        conn.close()

        # Hesaplamalar
        rows = []
        for row in ceiling_data:
            code, materials, notes, local = row
            qty = 0

            if ceiling_colour == "White":
                if code == "W_CL_T1":
                    qty = max(8, math.ceil((ceiling_m2 / 100 * 278) / 8) * 8)
                elif code == "W_CL_MR61":
                    qty = math.ceil(ceiling_m2 / 100 * 25)
                elif code == "W_CL_CT062":
                    qty = math.ceil(ceiling_m2 / 100 * 150)
                elif code == "W_CL_CT63":
                    qty = math.ceil(ceiling_m2 / 100 * 150)
                elif code == "W_CL_AT44":
                    qty = math.ceil(trim_lm / 3)
                elif code == "CL_W124":
                    qty = max(1, math.ceil(ceiling_m2 / 100 * 1))
                elif code == "CL_AB122":
                    qty = max(1, math.ceil(ceiling_m2 / 100 * 1))
            elif ceiling_colour == "Black":
                if code == "B_CL_T1":
                    qty = max(8, math.ceil((ceiling_m2 / 100 * 278) / 8) * 8)
                elif code == "B_CL_MR61":
                    qty = math.ceil(ceiling_m2 / 100 * 25)
                elif code == "B_CL_CT062":
                    qty = math.ceil(ceiling_m2 / 100 * 150)
                elif code == "B_CL_CT63":
                    qty = math.ceil(ceiling_m2 / 100 * 150)
                elif code == "B_CL_AT44":
                    qty = math.ceil(trim_lm / 3)
                elif code == "CL_W124":
                    qty = max(1, math.ceil(ceiling_m2 / 100 * 1))
                elif code == "CL_AB122":
                    qty = max(1, math.ceil(ceiling_m2 / 100 * 1))
            # Eğer renk seçimi boşsa qty = 0 olarak kalır

            # dPrice hesaplaması
            d_price = local - (local * ceil_dsc / 100)

            rows.append({
                "Code": code,
                "Materials": materials,
                "Notes": notes,
                "local": local,
                "qty": qty,
                "dPrice": round(d_price, 2)  # dPrice değerini yuvarla
                # "dPrice":local-(local*ceil_dsc/100)
            })

        return jsonify({'status': 'success', 'rows': rows})
    except Exception as e:
        print("Hata (calculate_ceiling_qty):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/add_ceiling_data', methods=['POST'])
def add_ceiling_data():
    try:
        data = request.get_json()
        largest_file = data.get('largest_file', '')  # Veritabanı adı
        ceiling_data = data.get('ceiling_data', [])  # Ceiling verileri

        if not largest_file or not ceiling_data:
            return jsonify({'status': 'error', 'message': 'Eksik veri gönderildi.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join('quotes', f"{largest_file}.db")
        print(f"DB Path: {db_path}")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # `list` tablosunu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID TEXT NOT NULL,
                ITEM_NAME TEXT NOT NULL,
                ADET INTEGER NOT NULL,
                UNIT_TYPE TEXT DEFAULT 'ADD_ITEM',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2), -- Yeni kolon eklendi
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT       
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır

        # Ceiling veritabanına bağlan
        ceiling_db_path = os.path.join(BASE_DIR, 'ceiling.db')
        conn_ceiling = sqlite3.connect(ceiling_db_path)
        cursor_ceiling = conn_ceiling.cursor()

        # Ceiling verilerini işleyip veritabanına ekle
        for index, row in enumerate(ceiling_data, start=1):
            item_id = row.get('Code', '')
            item_name = row.get('Materials', '')
            adet = row.get('qty', 0)
            unit_type = "Ceiling"
            # sira = f"3.{index}"
            sira = int(8000 + int(index)) 
            price = row.get('local', 0)
            dsprice = row.get('dPrice', 0)
            amounth = adet * dsprice

            # Import değerini ceiling.db'den çek
            cursor_ceiling.execute('SELECT Import FROM ceiling_data WHERE Code = ?', (item_id,))
            import_row = cursor_ceiling.fetchone()
            Import = import_row[0] if import_row else 0  # Eğer sonuç yoksa varsayılan olarak 0 kullan

            depo = adet * (dsprice - Import)

            # print(f"Import: {Import}")
            # print("Ceiling Data:", ceiling_data)

            # Veriyi `list` tablosuna ekle
            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, item_id, item_name, adet, unit_type, sira, price, dsprice, amounth, depo, Import))

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn.commit()
        conn.close()
        conn_ceiling.close()
        print("Ceiling verileri başarıyla eklendi.")

        return jsonify({'status': 'success', 'message': 'Ceiling verileri başarıyla eklendi.'})
    except sqlite3.Error as e:
        print("Veritabanı hatası (add_ceiling_data):", str(e))
        return jsonify({'status': 'error', 'message': f'Veritabanı hatası: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata (add_ceiling_data):", str(e))
        return jsonify({'status': 'error', 'message': f'Beklenmeyen hata: {str(e)}'}), 500

@app.route('/save_ceil_selection', methods=['POST'])
def save_ceil_selection():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        ceiling_m2 = data.get('ceiling_m2')
        trim_lm = data.get('trim_lm')
        ceiling_discount = data.get('ceiling_discount')
        ceiling_colour = data.get('ceiling_colour')  # <-- Renk seçimi de alındı

        if not quote_number or ceiling_m2 is None or trim_lm is None or ceiling_discount is None:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler: quote_number, ceiling_m2, trim_lm, veya ceiling_discount eksik.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "ceil_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ceil_selections (
                Quote_number TEXT NOT NULL,
                ceiling_m2 REAL,
                trim_lm REAL,
                ceiling_discount REAL,
                ceiling_colour TEXT      -- <-- Renk seçimi için yeni kolon
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM ceil_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        cursor.execute('''
            INSERT INTO ceil_selections (Quote_number, ceiling_m2, trim_lm, ceiling_discount, ceiling_colour)
            VALUES (?, ?, ?, ?, ?)
        ''', (quote_number, ceiling_m2, trim_lm, ceiling_discount, ceiling_colour))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Ceiling seçimleri başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (save_ceil_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/load_ceil_selection', methods=['GET'])
def load_ceil_selection():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "ceil_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # ceiling_colour kolonunu da çek
        cursor.execute('''
            SELECT ceiling_m2, trim_lm, ceiling_discount, ceiling_colour
            FROM ceil_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        if rows:
            ceiling_m2 = rows[0][0]
            trim_lm = rows[0][1]
            ceiling_discount = rows[0][2]
            ceiling_colour = rows[0][3] if len(rows[0]) > 3 else ""
            return jsonify({
                'status': 'success',
                'ceiling_m2': ceiling_m2,
                'trim_lm': trim_lm,
                'ceiling_discount': ceiling_discount,
                'ceiling_colour': ceiling_colour
            })
        else:
            return jsonify({'status': 'error', 'message': 'No ceiling selection found.'}), 404
    except Exception as e:
        print("Hata (load_ceil_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_customer_by_id', methods=['GET'])
def get_customer_by_id():
    customer_id = request.args.get('id')
    if not customer_id:
        return jsonify({"status": "error", "message": "Customer ID is required"}), 400

    try:
        conn = sqlite3.connect('customers.db')
        cursor = conn.cursor()
        cursor.execute("SELECT customer_name, tel, address, address2, postcode, email, discount FROM customers WHERE id = ?", (customer_id,))
        customer = cursor.fetchone()
        conn.close()

        if customer:
            return jsonify({
                "status": "success",
                "customer": {
                    "name": customer[0],
                    "tel": customer[1],
                    "address1": customer[2],
                    "address2": customer[3],
                    "postcode": customer[4],
                    "email": customer[5],
                    "discount": customer[6]
                }
            })
        else:
            return jsonify({"status": "error", "message": "Customer not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/add_or_update_customer', methods=['POST'])
def add_or_update_customer():
    try:
        data = request.get_json()
        customer_id = data.get('id')  # Güncelleme için varsa
        customer_name = data.get('name')
        tel = data.get('tel')
        address1 = data.get('address1')
        address2 = data.get('address2')
        postcode = data.get('postcode')
        email = data.get('email')
        discount = data.get('discount')

        conn = sqlite3.connect(os.path.join(BASE_DIR, 'customers.db'))
        cursor = conn.cursor()
        cursor.execute('''
                CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                customer_name TEXT NOT NULL,
                tel TEXT NOT NULL,
                address TEXT NOT NULL,
                address2 TEXT,
                postcode TEXT NOT NULL,
                email TEXT,
                discount REAL
            )
        ''')

        if customer_id:
            # Müşteri güncelleme
            cursor.execute('''
                UPDATE customers
                SET customer_name = ?, tel = ?, address = ?, address2 = ?, postcode = ?, email = ?, discount = ?
                WHERE id = ?
            ''', (customer_name, tel, address1, address2, postcode, email, discount, customer_id))
        else:
            # Eksik alan kontrolü
            if not customer_name or not tel or not address1 or not postcode:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Eksik veri: Yıldızlı alanların doldurulması zorunludur.'}), 400

            # Aynı müşteri zaten var mı?
            cursor.execute('''
                SELECT id FROM customers
                WHERE customer_name = ? AND tel = ? AND address = ? AND postcode = ?
            ''', (customer_name, tel, address1, postcode))
            existing_customer = cursor.fetchone()

            if existing_customer:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Müşteri zaten kayıtlı.'}), 400

            # Yeni müşteri ID'si oluştur
            cursor.execute('SELECT MAX(CAST(id AS INTEGER)) FROM customers')
            last_id = cursor.fetchone()[0] or 0
            new_id = str(last_id + 1).zfill(7)

            # Yeni müşteri ekle
            cursor.execute('''
                INSERT INTO customers (id, customer_name, tel, address, address2, postcode, email, discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_id, customer_name, tel, address1, address2, postcode, email, discount))

            # Yeni müşteri için veritabanı oluştur
            customerhes_path = os.path.join(BASE_DIR, 'customerhes')
            os.makedirs(customerhes_path, exist_ok=True)

            new_db_name = f"{new_id}{postcode}.db"
            new_db_path = os.path.join(customerhes_path, new_db_name)

            conn_new_db = sqlite3.connect(new_db_path)
            cursor_new_db = conn_new_db.cursor()
            cursor_new_db.execute('''
                CREATE TABLE IF NOT EXISTS customer_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    Date TEXT,
                    Customername TEXT,
                    Customerid TEXT,
                    Quotenumber TEXT,
                    Description TEXT,
                    S_I TEXT,
                    Amonth REAL
                )
            ''')
            conn_new_db.commit()
            conn_new_db.close()

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Müşteri başarıyla eklendi/güncellendi.'})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'status': 'error', 'message': f"Hata oluştu: {str(e)}"}), 500

@app.route('/sale_cust_det', methods=['POST'])
def sale_cust_det():
    try:
        data = request.get_json()
        date = data.get('date')
        quote_number = data.get('quote_number')
        customer_id = data.get('customer_id')
        customer_name = data.get('customer_name')
        postcode = data.get('postcode')
        description = data.get('description')
        s_i = data.get('s_i')
        total = data.get('total')
        vat = data.get('vat')
        delivery = data.get('delivery')
        deposit = data.get('deposit')
        s_total = total + delivery
        g_total = total + delivery + vat

        if not all([date, quote_number, customer_id, customer_name, postcode, description, s_i]):
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # customer_id'yi 7 karakter olacak şekilde sıfırlarla doldur
        customer_id = str(customer_id).zfill(7)

        # Veritabanı adı oluştur
        db_name = f"{customer_id}{postcode}.db"
        db_path = os.path.join(BASE_DIR, 'customerhes', db_name)

        # Tabloda hangi amountu kullanacağımızı seç
        if s_i == "S":
            amount_to_save = s_total
        elif s_i == "I":
            amount_to_save = g_total
        else:
            amount_to_save = g_total  # Varsayılan olarak g_total

        # Veritabanına bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Veriyi customer_data tablosuna ekle
        cursor.execute('''
            INSERT INTO customer_data (Date, Customername, Customerid, Quotenumber, Description, S_I, Amonth)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, customer_name, customer_id, quote_number, description, s_i, amount_to_save))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Veriler başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (sale_cust_det):", str(e))

@app.route('/get_customer_by_quote_number', methods=['GET'])
def get_customer_by_quote_number():
    quote_number = request.args.get('quote_number')
    if not quote_number:
        return jsonify({'status': 'error', 'message': 'Quote number is required'}), 400

    try:
        conn = sqlite3.connect('quotes.db')
        cursor = conn.cursor()

        # Veritabanından customer_id ve customer_name bilgilerini al
        cursor.execute("""
            SELECT customer_id, customer_name
            FROM quotes
            WHERE quote_number = ?
        """, (quote_number,))
        result = cursor.fetchone()

        conn.close()

        if result:
            customer_id, customer_name = result
            return jsonify({'status': 'success', 'customer_id': customer_id, 'customer_name': customer_name})
        else:
            return jsonify({'status': 'error', 'message': 'Quote not found'}), 404

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_customer_db', methods=['GET'])
def get_customer_db():
    try:
        db_name = request.args.get('db_name')
        if not db_name:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: db_name'}), 400

        # Veritabanı yolunu oluştur
        db_path = os.path.join(BASE_DIR, 'customerhes', db_name)

        # Veritabanının varlığını kontrol et
        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{db_name} veritabanı bulunamadı.'}), 404

        # Veritabanına bağlan ve verileri al
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT Date, Customername, Customerid, Quotenumber, Description, S_I, Amonth FROM customer_data')
        rows = cursor.fetchall()
        conn.close()

        return jsonify({'status': 'success', 'rows': rows})
    except Exception as e:
        print("Hata (get_customer_db):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/update_prc_tbl_quantity', methods=['POST'])
def update_prc_tbl_quantity():
    try:
        data = request.json
        itemId = data.get('item_id')
        qty = data.get('qty')

        if not itemId or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400

        conn = sqlite3.connect('prc_tbl.db')  # prc_tbl veritabanına bağlan
        cursor = conn.cursor()

        cursor.execute("UPDATE prc_tbl SET quantity = quantity - ? WHERE id = ?", (qty, itemId))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Quantity updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/update_refrigeration_quantity', methods=['POST'])
def update_refrigeration_quantity():
    try:
        data = request.json
        Model= data.get('model_')
        qty = data.get('qty')

        # Gelen değerleri konsola yazdır
        # print(f"Received item_id: {Model}, qty: {qty}")

        if not Model or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400
        
        # Model'den ilk '\' işaretine kadar olan kısmı al
        if '\\' in Model:
            Model = Model.split('\\')[0].strip()

        conn = sqlite3.connect('refrigeration.db')  # refrigeration veritabanına bağlan
        cursor = conn.cursor()

        cursor.execute("UPDATE refrigeration SET Qty = Qty - ? WHERE LOWER(REPLACE(Model, ' ', '')) = LOWER(REPLACE(?, ' ', ''))",(qty, Model))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Quantity updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/update_wood_quantity', methods=['POST'])
def update_wood_quantity():
    try:
        data = request.json
        item_name = data.get('item_name')
        qty = data.get('qty')

        # Gelen değerleri konsola yazdır
        # print(f"Received item_id: {item_name}, qty: {qty}")

        if not item_name or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400

        conn = sqlite3.connect('wood.db')  # refrigeration veritabanına bağlan
        cursor = conn.cursor()

        cursor.execute("UPDATE wood_tbl SET Qty = Qty - ? WHERE LOWER(REPLACE(ITEM_NAME, ' ', '')) = LOWER(REPLACE(?, ' ', ''))",(qty, item_name))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Quantity updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/update_ceiling_quantity', methods=['POST'])
def update_ceiling_quantity():
    try:
        data = request.json
        code = data.get('item_id')  # item_id = Code
        qty = data.get('qty')

        if not code or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400

        conn = sqlite3.connect('ceiling.db')
        cursor = conn.cursor()
        cursor.execute("UPDATE ceiling_data SET Qty = Qty - ? WHERE Code = ?", (qty, code))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Ceiling quantity updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/update_catering_quantity', methods=['POST'])
def update_catering_quantity():
    try:
        data = request.json
        # model_name = data.get('model')
        itemId = data.get('item_id')
        item_name = data.get('item_name')
        qty = data.get('qty')

        if not itemId or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400

        if '\\' in item_name:
            item_name = item_name.split('\\')[0].strip()

        conn = sqlite3.connect('catering.db')
        cursor = conn.cursor()

        cursor.execute("UPDATE catering_tbl SET Qty = Qty - ? WHERE LOWER(REPLACE(Model, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (qty, item_name))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Catering quantity updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/get_prc_tbl_data', methods=['GET'])
def get_prc_tbl_data():
    try:
        # Veritabanına bağlan
        conn = sqlite3.connect('prc_tbl.db')
        cursor = conn.cursor()

        # Verileri çek
        cursor.execute("SELECT id, name1, name2, quantity, code, import, local, kg FROM prc_tbl")
        rows = cursor.fetchall()

        # Bağlantıyı kapat
        conn.close()

        # Verileri JSON formatında döndür
        return jsonify({"status": "success", "rows": rows})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/get_refrigeration_data', methods=['GET'])
def get_refrigeration_data():
    try:
        # Veritabanına bağlan
        conn = sqlite3.connect('refrigeration.db')
        cursor = conn.cursor()

        # Verileri çek
        cursor.execute('''
            SELECT ID, GroupName, Model, RetailPrice, TradePrice, Kar, Maliyet, Kg, Qty, Warranty, UnpackPosition, RemoveDispose
            FROM REFRIGERATION
        ''')
        rows = cursor.fetchall()

        # Bağlantıyı kapat
        conn.close()

        # Verileri JSON formatında döndür
        return jsonify({"status": "success", "rows": rows})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/update_quote_si', methods=['POST'])
def update_quote_si():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        s_i = data.get('s_i')  # 'S' veya 'I' değeri

        if not quote_number or not s_i:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # quotes.db veritabanına bağlan
        quotes_db_path = os.path.join(BASE_DIR, "quotes.db")
        conn = sqlite3.connect(quotes_db_path)
        cursor = conn.cursor()

        # `Sold` veya `Inv` kolonunu güncelle
        if s_i == 'S':
            cursor.execute('UPDATE quotes SET Sold = ? WHERE Quote_number = ?', ('S', quote_number))
        elif s_i == 'I':
            cursor.execute('UPDATE quotes SET Inv = ? WHERE Quote_number = ?', ('I', quote_number))
        else:
            return jsonify({'status': 'error', 'message': 'Geçersiz S/I değeri.'}), 400

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': f'{quote_number} için {s_i} değeri güncellendi.'})
    except Exception as e:
        print("Hata (update_quote_si):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_quote_date', methods=['GET'])
def get_quote_date():
    quote_number = request.args.get('quote_number')
    if not quote_number:
        return jsonify({'status': 'error', 'message': 'Quote number is required'}), 400

    try:
        # Veritabanına bağlan
        conn = sqlite3.connect('quotes.db')  # quotes.db yerine doğru veritabanı adını yazın
        cursor = conn.cursor()

        # Tarihi sorgula
        cursor.execute("SELECT created_at FROM quotes WHERE quote_number = ?", (quote_number,))
        result = cursor.fetchone()

        if result:
            return jsonify({'status': 'success', 'quote_date': result[0]})  # Anahtar 'quote_date' olarak değiştirildi
        else:
            return jsonify({'status': 'error', 'message': 'Quote not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    finally:
        conn.close()

@app.route('/check_sign', methods=['GET'])
def check_sign():
    quote_number = request.args.get('quote_number')
    if not quote_number:
        return jsonify({"status": "error", "message": "Quote number is required"}), 400

    try:
        conn = sqlite3.connect('quotes.db')
        cursor = conn.cursor()

        # S veya I kolonlarının dolu olup olmadığını kontrol et
        cursor.execute("SELECT Sold, Inv FROM quotes WHERE quote_number = ?", (quote_number,))
        result = cursor.fetchone()

        if result and (result[0] or result[1]):  # S veya I doluysa
            return jsonify({"status": "exists"})
        else:
            return jsonify({"status": "not_exists"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        conn.close()



# Özelleştirilmiş PDF sınıfı
from fpdf import FPDF
from fpdf.enums import XPos, YPos
# XPos ve YPos için sabitler
class XPos:
    LMARGIN = 'LMARGIN'
    RMARGIN = 'RMARGIN'
    RIGHT = 'RIGHT'

class YPos:
    NEXT = 'NEXT'
    TOP = 'TOP'
    BOTTOM = 'BOTTOM'

class InvoicePDF(FPDF):
    def header(self):
        self.set_font('Helvetica', '', 9)
        self.cell(90, 4, 'Easyshelf Direct Ltd.', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(100, 4, '205-207 Leabridge Road', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(100, 4, 'E10 7PN', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(100, 4, 'Telefon: +44 7834519643', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        try:
            self.image('static/images/logoI.png', x=150, y=9, w=50)
        except RuntimeError as e:
            print(f"Logo yüklenemedi: {e}")

        self.set_xy(140, 22)
        self.set_font('Helvetica', '', 9)
        self.cell(60, 5, f'Tarih: {self.invoice_date}', align='R')
        self.ln(5)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(1)

    def footer(self):
        self.set_y(-20)
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_font('Helvetica', 'I', 7.5)
        self.set_text_color(100, 100, 100)
        self.cell(0, 3, "Note: Engineers will follow customer/shop keeper/representative's instructions as to how and where to perform installation work. In no event will we be liable for any loss", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.cell(0, 3, "or damage including without limitation, indirect or consequential loss or damage, or any loss or damage whatsoever arising from any installation or delivery. All goods", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.cell(0, 3, "remains the property of Easyshelf Direct Ltd all dues paid in full 50% re-stocking fee will be charged for goods returned", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.cell(0, 3, "rall goods supplied example (refrigeration and catering equipments ) are one year parts  warranty only unless clearly specified", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.cell(0, 3, "VAT Reg .No : 130 7430 50 Company No: 07951727", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.cell(0, 5, f'Page {self.page_no()}', align='C')

@app.route('/update_delivery_address', methods=['POST'])
def update_delivery_address():
    try:
        data = request.json
        quote_number = data.get('quote_number')
        name = data.get('name')
        tel = data.get('tel')
        address1 = data.get('address1')
        address2 = data.get('address2')
        postcode = data.get('postcode')

        # Validate required fields
        if not all([quote_number, name, tel, address1, postcode]):
            return jsonify({'status': 'error', 'message': 'Missing required fields'}), 400

        # Update the delivery address in the database
        db_path = os.path.join(BASE_DIR, "prf_adr_dlvr.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if the quote_number exists
        cursor.execute('SELECT COUNT(*) FROM delivery_info WHERE quotenum = ?', (quote_number,))
        if cursor.fetchone()[0] == 0:
            conn.close()
            return jsonify({'status': 'error', 'message': 'Quote number not found'}), 404

        # Update the delivery fields
        cursor.execute('''
            UPDATE delivery_info
            SET Dname = ?, Dtel = ?, Daddress1 = ?, Daddress2 = ?, Dpostcode = ?
            WHERE quotenum = ?
        ''', (name, tel, address1, address2, postcode, quote_number))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Delivery address updated successfully'})

    except Exception as e:
        print(f"Error updating delivery address: {e}")
        return jsonify({'status': 'error', 'message': 'An error occurred while updating the delivery address'}), 500

@app.route('/generate_invoice', methods=['POST'])
def generate_invoice():
    data = request.json
    quote_number = data.get('quote_number')
    date = data.get('date', datetime.now().strftime('%d-%m-%Y'))
    recipient_email = 'volkanballi@gmail.com'

    if not quote_number or not recipient_email:
        return jsonify({'status': 'error', 'message': 'Quote number and recipient email are required.'}), 400

    try:
        # --- INVOICE LIST DB OLUŞTUR/KONTROL ---
        base_dir = os.path.dirname(os.path.abspath(__file__))
        invoice_db_path = os.path.join(base_dir, "invoice_list.db")
        conn_inv = sqlite3.connect(invoice_db_path)
        c_inv = conn_inv.cursor()
        c_inv.execute('''
            CREATE TABLE IF NOT EXISTS invoice_list (
                inv_num TEXT PRIMARY KEY,
                quote_num TEXT,
                ruser_id TEXT,
                user_name TEXT,
                customer_id TEXT,
                customer_name TEXT,
                g_tot REAL
            )
        ''')

        # Kullanıcı ve müşteri bilgilerini al
        user_id = str(session.get('user_id', '00')).zfill(2)
        user_name = session.get('user', 'Unknown User')
        # quotes tablosundan müşteri bilgilerini çek
        quotes_db_path = os.path.join(base_dir, "quotes.db")
        conn_quotes = sqlite3.connect(quotes_db_path)
        c_quotes = conn_quotes.cursor()
        c_quotes.execute("SELECT Customer_id, Customer_name, Amount FROM quotes WHERE Quote_number = ?", (quote_number,))
        qrow = c_quotes.fetchone()
        conn_quotes.close()
        if not qrow:
            return jsonify({'status': 'error', 'message': 'Quote not found.'}), 404
        customer_id, customer_name, g_tot = qrow

        # --- NUMARA KONTROLÜ ---
        dd_mm_yy = datetime.now().strftime('%d%m%y')
        prefix = f"{user_id}{dd_mm_yy}"
        c_inv.execute("SELECT inv_num FROM invoice_list WHERE inv_num LIKE ?", (f"{prefix}%",))
        existing = [row[0] for row in c_inv.fetchall()]
        if existing:
            max_suffix = max([int(e[len(prefix):]) for e in existing if e[len(prefix):].isdigit()] or [0])
            new_suffix = str(max_suffix + 1).zfill(5)
        else:
            new_suffix = "00001"
        invoice_num = f"{prefix}{new_suffix}"

        # --- KAYIT EKLE ---
        c_inv.execute('''
            INSERT INTO invoice_list (inv_num, quote_num, ruser_id, user_name, customer_id, customer_name, g_tot)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (invoice_num, quote_number, user_id, user_name, customer_id, customer_name, g_tot))
        conn_inv.commit()
        conn_inv.close()

        # --- PDF ve e-posta işlemleri (mevcut kodunuz) ---
        # Veritabanı yolları
        db_path = os.path.join(base_dir, 'quotes', f"{quote_number}.db")
        delivery_db_path = os.path.join(base_dir, "prf_adr_dlvr.db")

        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{quote_number}.db not found.'}), 404
        if not os.path.exists(delivery_db_path):
            return jsonify({'status': 'error', 'message': 'Delivery info database not found.'}), 404

        # Veritabanından liste verilerini al
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT ITEM_NAME, ADET, DSPRICE, AMOUNTH FROM list')
        rows = cursor.fetchall()
        conn.close()

        # --- TOPLAM, KDV, GENEL TOPLAM HESAPLAMA ---

        # Delivery Price'ı quotes tablosundan veya quote db'den çekin:
        conn = sqlite3.connect(os.path.join(BASE_DIR, "quotes.db"))
        cursor = conn.cursor()
        cursor.execute("SELECT Delpr FROM quotes WHERE Quote_number = ?", (quote_number,))
        delpr_row = cursor.fetchone()
        delivery_price = float(delpr_row[0]) if delpr_row and delpr_row[0] else 0.0
        conn.close()

        # KG bilgisini quote db'den çekin:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(KG) FROM list')
        kg_total = cursor.fetchone()[0] or 0
        conn.close()



        total_amount = sum(row[3] for row in rows)
        vat = round((total_amount + delivery_price) * 0.20, 2)
        grand_total = round(total_amount + delivery_price + vat, 2)

        # Veritabanından teslimat bilgilerini al
        conn = sqlite3.connect(delivery_db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, tel, address1, address2, postcode, Dname, Dtel, Daddress1, Daddress2, Dpostcode
            FROM delivery_info
            WHERE quotenum = ?
        ''', (quote_number,))
        delivery_info = cursor.fetchone()
        conn.close()

        if not delivery_info:
            return jsonify({'status': 'error', 'message': 'Delivery info not found for the given quote number.'}), 404



        # PDF oluşturma
        pdf = InvoicePDF()
        pdf.invoice_date = date  # header'da kullanacağız
        pdf.add_page()
        pdf.set_font('Helvetica', '', 8)
        pdf.cell(0, 3, f"Quotation Num: {quote_number}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.cell(0, 3, f"Invoice Num: {invoice_num}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)  # Yeni invoice numarası
        pdf.cell(0, 3, f"Sale person: {user_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT) 

        # color_selections.db'den renk seçimlerini al
        color_conn = sqlite3.connect('color_selections.db')
        color_cursor = color_conn.cursor()
        color_cursor.execute('''
            SELECT Shelf_color, Ticket_color, Ttype, Slatwall, Insert_color, Endcap
            FROM color_selections
            WHERE quote_number = ?
        ''', (quote_number,))
        color_row = color_cursor.fetchone()
        color_conn.close()

        # renk seçimlerini yaz
        # if (color_row):
        #     color_labels = ['Shelf', 'Ticket', 'Type', 'Slatwall', 'Insert', 'Endcap']
        #     for label, value in zip(color_labels, color_row):
        #         pdf.set_font('Helvetica', '', 7)
        #         pdf.cell(0, 3, f"{label}: {value or 'N/A'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        # else:
        #     pdf.cell(0, 4, "Color selections: Not found", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

        if color_row:
            color_labels = ['Shelf', 'Ticket', 'T.Type', 'Slatwall', 'Insert', 'Endcap']
            pdf.set_font('Helvetica', '', 7)
            x = 180
            y = 28
            for label, value in zip(color_labels, color_row):
                pdf.set_xy(x, y)
                pdf.cell(0, 3, f"{label}: {value or 'N/A'}", new_x=XPos.RIGHT, new_y=YPos.TOP)
                y += 3
            # Renklerin hemen altına Total KG yaz
            pdf.set_xy(x, y + 1)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.cell(0, 4, f"Total KG: {kg_total:.2f}", new_x=XPos.RIGHT, new_y=YPos.TOP)
        else:
            pdf.set_xy(180, 28)
            pdf.set_font('Helvetica', '', 7)
            pdf.cell(0, 4, "Color selections: Not found", new_x=XPos.RIGHT, new_y=YPos.TOP)
            pdf.set_xy(180, 32)
            pdf.set_font('Helvetica', 'B', 7)
            pdf.cell(0, 4, f"Total KG: {kg_total:.2f}", new_x=XPos.RIGHT, new_y=YPos.TOP)





        # Proforma To ve Deliver To bölümleri
        pdf.set_font('Helvetica', 'B', 9)

        # "Proforma To" başlığı
        pdf.set_xy(60, 28)  # Sol üst köşe (x=10, y=50)
        pdf.cell(0, 4, "Proforma To:", new_x=XPos.RIGHT, new_y=YPos.TOP)

        # "Deliver To" başlığı
        pdf.set_xy(125, 28)  # Sağ üst köşe (x=110, y=50)
        pdf.cell(0, 4, "Deliver To:", new_x=XPos.RIGHT, new_y=YPos.TOP)

        pdf.set_font('Helvetica', '', 8)

        # Proforma To bilgileri
        pdf.set_xy(60, 32)
        pdf.cell(0, 3, delivery_info[0], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Name
        pdf.set_xy(60, 36)
        pdf.cell(0, 3, delivery_info[1], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Tel
        pdf.set_xy(60, 39.5)
        pdf.cell(0, 3, delivery_info[2], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Address1
        pdf.set_xy(60, 43)
        pdf.cell(0, 3, delivery_info[3], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Address2
        pdf.set_xy(60, 46.5)
        pdf.cell(0, 3, delivery_info[4], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Postcode

        # Deliver To bilgileri
        pdf.set_xy(125, 32)
        pdf.cell(0, 3, delivery_info[5], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Name
        pdf.set_xy(125, 36)
        pdf.cell(0, 3, delivery_info[6], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Tel
        pdf.set_xy(125, 39.5)
        pdf.cell(0, 3, delivery_info[7], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Address1
        pdf.set_xy(125, 43)
        pdf.cell(0, 3, delivery_info[8], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Address2
        pdf.set_xy(125, 46.5)
        pdf.cell(0, 3, delivery_info[9], new_x=XPos.RIGHT, new_y=YPos.TOP)  # Postcode

        

        # Tablo başlıkları
        pdf.ln(5)
        pdf.set_font('Helvetica', 'B', 10)
        fillH = True
        pdf.set_fill_color(235, 235, 235)
        pdf.cell(120, 5, "ITEM_NAME", align='L', fill=fillH)
        pdf.cell(10, 5, "QTY", align='R', fill=fillH)
        pdf.cell(30, 5, "D.PRICE", align='R', fill=fillH)
        pdf.cell(30, 5, "AMOUNTH", align='R', fill=fillH)
        pdf.ln()

        # Veriler
        pdf.set_font('Helvetica', '', 8)
        fill = False
        for row in rows:
            pdf.set_fill_color(235, 235, 235)  # Çok açık gri
            pdf.cell(120, 4, row[0], align='L', fill=fill)
            pdf.cell(10, 4, str(row[1]), align='R', fill=fill)
            pdf.cell(30, 4, f"{row[2]:.2f}", align='R', fill=fill)
            pdf.cell(30, 4, f"{row[3]:.2f}", align='R', fill=fill)
            pdf.ln()
            fill = not fill

        # --- TOPLAM, KDV, GENEL TOPLAM SATIRLARI ---
        pdf.set_font('Helvetica', 'B', 9)
        pdf.cell(160, 5, "Total:", align='R')
        pdf.cell(30, 5, f"{total_amount:.2f}", align='R')
        pdf.ln()


        # Delivery Price satırı
        pdf.cell(160, 5, "Delivery:", align='R')
        pdf.cell(30, 5, f"{delivery_price:.2f}", align='R')
        pdf.ln()



        pdf.cell(160, 5, "VAT (20%):", align='R')
        pdf.cell(30, 5, f"{vat:.2f}", align='R')
        pdf.ln()
        pdf.cell(160, 5, "G.Total:", align='R')
        pdf.cell(30, 5, f"{grand_total:.2f}", align='R')
        pdf.ln()


        # PDF'yi bellekte oluştur
        pdf_buffer = BytesIO()
        pdf.output(pdf_buffer)
        pdf_buffer.seek(0)

        # PDF'yi dosya olarak ftpye kaydet
        pdf_buffer.seek(0)
        upload_pdf_to_ftp(
            pdf_buffer,
            f"Invoice_{invoice_num}.pdf",
            'ftp.easyshelf.co.uk',  # FTP sunucu adresiniz
            'volkan@easyshelf.co.uk',    # FTP kullanıcı adınız
            'Volkan@2025!',           # FTP şifreniz
            '/invoice'            # FTP klasörü (isteğe bağlı)
        )
        pdf_buffer.seek(0)  # E-posta için tekrar başa sar

        # E-posta gönderme
        sender_email = "easyfatgon@gmail.com"  # Gönderen e-posta adresi
        sender_password = "bchm xdew ywhc vqzj"  # Gönderen e-posta şifresi

        # E-posta mesajını oluştur
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = recipient_email
        msg['Subject'] = f"Invoice {invoice_num}"

        # E-posta gövdesi
        body = f"Dear Customer,\n\nPlease find attached the invoice for quotation number {invoice_num}.\n\nBest regards,\nYour Company"
        msg.attach(MIMEText(body, 'plain'))

        # PDF'yi ek olarak ekle
        attachment = MIMEBase('application', 'octet-stream')
        attachment.set_payload(pdf_buffer.read())
        encoders.encode_base64(attachment)
        attachment.add_header('Content-Disposition', f'attachment; filename=Invoice_{invoice_num}.pdf')
        msg.attach(attachment)

        # SMTP sunucusuna bağlan ve e-posta gönder
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()

        return jsonify({'status': 'success', 'message': f'Invoice sent to {recipient_email}.'})

    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
def upload_pdf_to_ftp(pdf_bytes, filename, ftp_host, ftp_user, ftp_pass, ftp_dir='/'):
    try:
        ftp = FTP(ftp_host)
        ftp.login(ftp_user, ftp_pass)
        if ftp_dir:
            ftp.cwd(ftp_dir)
        ftp.storbinary(f'STOR {filename}', pdf_bytes)
        ftp.quit()
        print("PDF FTP'ye başarıyla yüklendi.")
        return True
    except Exception as e:
        print(f"FTP yükleme hatası: {e}")
        return False

    # try:
    #     print("PDF ISTENIRSE FTP'ye KAYIT EDILECEK.")
    #     return True
    # except Exception as e:
    #     print(f"FTP yükleme hatası: {e}")
    #     return False

@app.route('/createTableprofdelv', methods=['POST'])
def create_table_profdelv():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        customer_id = data.get('customer_id')

        if not quote_number or not customer_id:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler: quote_number veya customer_id eksik.'}), 400

        # prf_adr_dlvr.db dosyasını oluştur veya aç
        db_path = os.path.join(BASE_DIR, "prf_adr_dlvr.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS delivery_info (
                quotenum TEXT NOT NULL,
                name TEXT,
                tel TEXT,
                address1 TEXT,
                address2 TEXT,
                postcode TEXT,
                Dname TEXT,
                Dtel TEXT,
                Daddress1 TEXT,
                Daddress2 TEXT,
                Dpostcode TEXT
            )
        ''')

        # customers.db'den müşteri bilgilerini al
        customers_db_path = os.path.join(BASE_DIR, "customers.db")
        conn_customers = sqlite3.connect(customers_db_path)
        cursor_customers = conn_customers.cursor()

        cursor_customers.execute('''
            SELECT customer_name, tel, address, address2, postcode
            FROM customers
            WHERE id = ?
        ''', (customer_id,))
        customer_data = cursor_customers.fetchone()
        conn_customers.close()

        if not customer_data:
            return jsonify({'status': 'error', 'message': f'Customer ID {customer_id} ile eşleşen müşteri bulunamadı.'}), 404

        # Mevcut bir kayıt olup olmadığını kontrol et
        cursor.execute('SELECT COUNT(*) FROM delivery_info WHERE quotenum = ?', (quote_number,))
        record_exists = cursor.fetchone()[0] > 0

        if record_exists:
            # Mevcut kaydı güncelle
            cursor.execute('''
                UPDATE delivery_info
                SET name = ?, tel = ?, address1 = ?, address2 = ?, postcode = ?, 
                    Dname = ?, Dtel = ?, Daddress1 = ?, Daddress2 = ?, Dpostcode = ?
                WHERE quotenum = ?
            ''', (*customer_data, *customer_data, quote_number))
        else:
            # Yeni bir kayıt ekle
            cursor.execute('''
                INSERT INTO delivery_info (quotenum, name, tel, address1, address2, postcode, Dname, Dtel, Daddress1, Daddress2, Dpostcode)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (quote_number, *customer_data, *customer_data))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Veriler başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (create_table_profdelv):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_delivery_info', methods=['GET'])
def get_delivery_info():
    try:
        quote_number = request.args.get('quote_number')
        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # prf_adr_dlvr.db'den verileri al
        db_path = os.path.join(BASE_DIR, "prf_adr_dlvr.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT name, tel, address1, address2, postcode, Dname, Dtel, Daddress1, Daddress2, Dpostcode
            FROM delivery_info
            WHERE quotenum = ?
        ''', (quote_number,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'status': 'error', 'message': 'Quote number ile eşleşen kayıt bulunamadı.'}), 404

        delivery_info = {
            "name": row[0],
            "tel": row[1],
            "address1": row[2],
            "address2": row[3],
            "postcode": row[4],
            "Dname": row[5],
            "Dtel": row[6],
            "Daddress1": row[7],
            "Daddress2": row[8],
            "Dpostcode": row[9]
        }

        return jsonify({'status': 'success', 'delivery_info': delivery_info})
    except Exception as e:
        print("Hata (get_delivery_info):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/depo_topla', methods=['POST'])
def depo_topla():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Quote number eksik.'}), 400

        db_path = os.path.join('quotes', f"{quote_number}.db")
        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{quote_number}.db bulunamadı.'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Normal gruplama
        cursor.execute('''
        SELECT 
            CAST(SIRA AS INTEGER) / 100 * 100 AS vercode, 
            SUM(DEPO)
        FROM list
        GROUP BY vercode
        ORDER BY vercode
        ''')
        rows = cursor.fetchall()

        # 1000-2299 ve 4000-4299 arası DEPO toplamı
        cursor.execute('''
            SELECT SUM(DEPO) FROM list
            WHERE (SIRA >= 1000 AND SIRA < 2300) OR (SIRA >= 4000 AND SIRA < 4300)
        ''')
        merged_1000_sum = cursor.fetchone()[0] or 0

        # 2300-3999 arası DEPO toplamı
        cursor.execute('''
            SELECT SUM(DEPO) FROM list
            WHERE (SIRA >= 2300 AND SIRA < 4000)
        ''')
        merged_2300_sum = cursor.fetchone()[0] or 0

        # Kod eşleme fonksiyonu
        def code_to_letter(code):
            code = int(code)
            if code == 1000:
                return "R"
            elif code == 2300:
                return "C"
            elif code == 4500:
                return "T"
            elif code == 7000:
                return "D"
            elif code == 7200:
                return "RST"
            elif code == 8000:
                return "TV"
            elif code == 9000:
                return "X"
            else:
                return str(code)

        # Sonuçları oluştur
        result_list = []
        merged_1000_written = False
        merged_2300_written = False
        for vercode, depo_sum in rows:
            if vercode == 1000 and not merged_1000_written:
                result_list.append(f"{code_to_letter(1000)}/{int(merged_1000_sum)}")
                merged_1000_written = True
            elif vercode == 2300 and not merged_2300_written:
                result_list.append(f"{code_to_letter(2300)}/{int(merged_2300_sum)}")
                merged_2300_written = True
            elif (1000 < vercode < 2300) or (2300 < vercode < 4000) or (4000 <= vercode < 4300):
                continue
            else:
                result_list.append(f"{code_to_letter(vercode)}/{int(depo_sum)}")

        result = '-'.join(result_list)
        conn.close()
        return jsonify({'status': 'success', 'result': result})
    except Exception as e:
        print("Hata (depo_topla):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/kg_topla', methods=['POST'])
def kg_topla():
    data = request.get_json()
    quote_number = data.get('quote_number')
    db_path = os.path.join(QUOTE_DB_PATH, f"{quote_number}.db")
    if not os.path.exists(db_path):
        return jsonify({'status': 'error', 'message': 'DB bulunamadı.'}), 404
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT SUM(KG) FROM list')
        kg_total = cursor.fetchone()[0] or 0
        conn.close()
        return jsonify({'status': 'success', 'kg_total': float(kg_total)})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_color_options', methods=['GET'])
def get_color_options():
    try:
        conn = sqlite3.connect('color_tbl.db')
        cursor = conn.cursor()

        # Fetch options for each dropdown, filtering out NULL or empty values
        cursor.execute('SELECT DISTINCT SHELF FROM color_tbl WHERE SHELF IS NOT NULL AND SHELF != ""')
        shelf = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT TICKET FROM color_tbl WHERE TICKET IS NOT NULL AND TICKET != ""')
        ticket = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT TYPE FROM color_tbl WHERE TYPE IS NOT NULL AND TYPE != ""')
        ttype = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT SLATWALL FROM color_tbl WHERE SLATWALL IS NOT NULL AND SLATWALL != ""')
        slatwall = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT "INSERT" FROM color_tbl WHERE "INSERT" IS NOT NULL AND "INSERT" != ""')
        insert = [row[0] for row in cursor.fetchall()]

        cursor.execute('SELECT DISTINCT ENDCAP FROM color_tbl WHERE ENDCAP IS NOT NULL AND ENDCAP != ""')
        endcap = [row[0] for row in cursor.fetchall()]

        conn.close()

        return jsonify({
            'status': 'success',
            'shelf': shelf,
            'ticket': ticket,
            'type': ttype,
            'slatwall': slatwall,
            'insert': insert,
            'endcap': endcap
        })
    except Exception as e:
        print("Error (get_color_options):", str(e))
        return jsonify({'status': 'error', 'message': str(e)})

@app.route('/save_color_selections', methods=['POST'])
def save_color_selections():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        selections = data.get('selections')

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "color_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Tabloyu oluştur (eğer yoksa)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS color_selections (
                Quote_number TEXT PRIMARY KEY,
                Shelf_color TEXT,
                Ticket_color TEXT,
                Ttype TEXT,
                Slatwall TEXT,
                Insert_color TEXT,
                Endcap TEXT
            )
        ''')

        # Eski kaydı sil
        cursor.execute('DELETE FROM color_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni kaydı ekle
        cursor.execute('''
            INSERT INTO color_selections (Quote_number, Shelf_color, Ticket_color, Ttype, Slatwall, Insert_color, Endcap)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            quote_number,
            selections.get('shelfColor', ''),
            selections.get('ticketColor', ''),
            selections.get('ttype', ''),
            selections.get('slatwall', ''),
            selections.get('insert', ''),
            selections.get('endcap', '')
        ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Renk seçimleri başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (save_color_selections):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/load_color_selections', methods=['GET'])
def load_color_selections():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "color_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Seçimleri al
        cursor.execute('''
            SELECT Shelf_color, Ticket_color, Ttype, Slatwall, Insert_color, Endcap
            FROM color_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return jsonify({'status': 'error', 'message': f'Quote_number {quote_number} için renk seçimleri bulunamadı.'}), 404

        # Seçimleri JSON formatında döndür
        return jsonify({
            'status': 'success',
            'selections': {
                'shelfColor': row[0],
                'ticketColor': row[1],
                'ttype': row[2],
                'slatwall': row[3],
                'insert': row[4],
                'endcap': row[5]
            }
        })
    except Exception as e:
        print(f"Hata (load_color_selections): {str(e)}")  # Hata detaylarını konsola yazdır
        return jsonify({'status': 'error', 'message': f'Sunucu hatası: {str(e)}'}), 500

@app.route('/add_unite_secnd_part', methods=['POST'])
def add_unite_secnd_part():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        selections = data.get('selections', [])

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        db_path = os.path.join(QUOTE_DB_PATH, f"{quote_number}.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID INTEGER,
                ITEM_NAME TEXT NOT NULL,
                ADET INTEGER NOT NULL,
                UNIT_TYPE TEXT DEFAULT 'UNITE_SECOND_PART',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2),
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT 
            )
        ''')

        user_id = session.get('user_id', 0)
        prc_conn = sqlite3.connect('prc_tbl.db')
        prc_cursor = prc_conn.cursor()
        counter_conn = sqlite3.connect('counter.db')
        counter_cursor = counter_conn.cursor()

        processed_items = []

        for selection in selections:
            item_name = selection['item_name']
            quantity = selection['quantity']
            column_number = selection['column_number']
            row_index = selection['row_index']

            if "Counter S." in item_name or "Counter H." in item_name or "Counter High" in item_name or "Counter Standard" in item_name or "Counter HIGH" in item_name or "Counter STANDARD" in item_name:
                counter_cursor.execute('''
                    SELECT item_name, qty 
                    FROM counter_parca
                    WHERE LOWER(REPLACE(group_name, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                counter_rows = counter_cursor.fetchall()

                for counter_item_name, counter_qty in counter_rows:
                    sira = int(2300 + int(row_index))
                    prc_cursor.execute('''
                        SELECT id, local, import, kg FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price, import_value, kg_value = prc_row if prc_row else (None, 0.0, 0.0, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price, import_value, ((counter_qty * quantity)*kg_value)))

            elif "Fruit" in item_name:
                counter_cursor.execute('''
                    SELECT item_name, qty 
                    FROM counter_parca
                    WHERE LOWER(REPLACE(group_name, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                counter_rows = counter_cursor.fetchall()

                for counter_item_name, counter_qty in counter_rows:
                    sira = int(1500 + int(row_index))
                    prc_cursor.execute('''
                        SELECT id, local, import, kg FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price, import_value, kg_value = prc_row if prc_row else (None, 0.0, 0.0, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price, import_value, ((counter_qty * quantity)*kg_value)))

            elif "Freezer" in item_name or "freezer" in item_name:
                counter_cursor.execute('''
                    SELECT item_name, qty 
                    FROM counter_parca
                    WHERE LOWER(REPLACE(group_name, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                counter_rows = counter_cursor.fetchall()

                for counter_item_name, counter_qty in counter_rows:
                    sira = int(2000 + int(row_index))
                    prc_cursor.execute('''
                        SELECT id, local, import, kg FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price, import_value, kg_value = prc_row if prc_row else (None, 0.0, 0.0, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price, import_value, ((counter_qty * quantity)*kg_value)))
            else:
                prc_cursor.execute('''
                    SELECT id, local, import, kg FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                prc_row = prc_cursor.fetchone()
                item_id, price, import_value, kg_value = prc_row if prc_row else (None, 0.0, 0.0, 0.0)

                if item_id is None:
                    item_id = 0

                if any(x in item_name for x in ["Side", "side", "Drop", "drop", "Slat", "slat"]):
                    sira = int(3500 + int(row_index))
                    grpname = item_name
                else:
                    sira = int(4000 + int(row_index))  #siranumarasi 4000 den 2150 ye dgisti
                    grpname = 'UNITE_SECOND_PART'

                cursor.execute('''
                    INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?)
                ''', (user_id, item_id, item_name, quantity, grpname, sira, price, import_value, (quantity*kg_value)))

            processed_items.append({
                'item_name': item_name,
                'row_index': row_index,
                'column_number': column_number
            })

        # ------------------ Worktop Hesaplama ------------------ #

        def extract_numeric_value(text):
            numbers = re.findall(r'\d+', text)
            return int(numbers[-1]) if numbers else 0

        def extract_prefix(text):
            valid_prefixes = ["Counter STANDARD", "Counter S. LOW", "Counter HIGH", "Counter High", "Counter Standard", "Counter H. LOW"]
            for prefix in valid_prefixes:
                if text.startswith(prefix):
                    return prefix
            return None

        def calculate_worktops(items):
            worktops = []
            i = 0

            def get_column_number(item):
                return item.get('column_number') if isinstance(item, dict) else item['column_number']

            while i < len(items):
                item = items[i]
                name = item['item_name']
                column_number = get_column_number(item)
                prefix = extract_prefix(name)

                # Worktop Standard grubu
                if prefix in ["Counter STANDARD", "Counter HIGH", "Counter High", "Counter Standard"]:
                    ws = 0
                    group_prefix = prefix

                    while i < len(items):
                        current_prefix = extract_prefix(items[i]['item_name'])
                        if current_prefix not in ["Counter STANDARD", "Counter HIGH", "Counter High", "Counter Standard"]:
                            break
                        val = extract_numeric_value(items[i]['item_name'])
                        ws += val * 10
                        i += 1

                    ws += 30

                    if group_prefix == "Counter High":
                        worktops.append(("Worktop High", ws))
                    else:
                        worktops.append(("Worktop Standard", ws))
                    continue

                # Worktop Low grubu
                elif prefix in ["Counter S. LOW", "Counter H. LOW"]:
                    wl = 0
                    start_index = i
                    group_prefix = prefix
                    current_column = column_number

                    while i < len(items):
                        current_prefix = extract_prefix(items[i]['item_name'])
                        if current_prefix not in ["Counter S. LOW", "Counter H. LOW"]:
                            break
                        # Sadece aynı kolonda olanları topla
                        if get_column_number(items[i]) == current_column:
                            val = extract_numeric_value(items[i]['item_name'])
                            if val == 66:
                                wl += val * 10 + 5
                            else:
                                wl += val * 10
                        i += 1

                    # before: aynı kolonda ve bir önceki satır
                    before = None
                    for j in range(start_index - 1, -1, -1):
                        if get_column_number(items[j]) == current_column:
                            before = extract_prefix(items[j]['item_name'])
                            break

                    # after: aynı kolonda ve bir sonraki satır
                    after = None
                    for j in range(i, len(items)):
                        if get_column_number(items[j]) == current_column:
                            after = extract_prefix(items[j]['item_name'])
                            break

                    if before in ["Counter STANDARD", "Counter HIGH", "Counter High", "Counter Standard"]:
                        wl -= 35
                    else:
                        wl += 15

                    if after in ["Counter STANDARD", "Counter HIGH", "Counter High", "Counter Standard"]:
                        wl -= 35
                    else:
                        wl += 15

                    if group_prefix == "Counter H. LOW":
                        worktops.append(("Worktop H.Low", wl))
                    else:
                        worktops.append(("Worktop S.Low", wl))
                    continue
                else:
                    i += 1

            return worktops

        
        worktops = calculate_worktops(processed_items)
        for name, value in worktops:
            # Worktop için import ve kg değerini prc_tbl'ye bakarak çek
            prc_cursor.execute('''
                SELECT import, kg FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
            ''', (name,))
            import_row = prc_cursor.fetchone()
            import_value = import_row[0] if import_row else 0.0
            kg_value = import_row[1] if import_row else 0.0

            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                VALUES (?, 99999, ?, 1, 'WORKTOP', 2500, ?, 0, 0, 0, ?, ?)
            ''', (user_id, f'{name} {value}', value*0.17, import_value, kg_value))

        conn.commit()
        conn.close()
        prc_conn.close()
        counter_conn.close()

        color_to_db(quote_number)

        return jsonify({'status': 'success', 'message': 'Veriler başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (add_unite_secnd_part):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/apply_adet', methods=['POST'])
def apply_adet():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        adet_updates = data.get('adet_updates', [])

        if not quote_number or not adet_updates:
            return jsonify({'status': 'error', 'message': 'Eksik veri'}), 400

        db_path = os.path.join(QUOTE_DB_PATH, f"{quote_number}.db")
        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': 'Veritabanı bulunamadı'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        for item in adet_updates:
            adet = item.get('adet')
            db_indexes = item.get('db_indexes', [])

            if adet is None or not db_indexes:
                continue

            for row_index in db_indexes:
                cursor.execute("UPDATE List SET ADET = ? WHERE rowid = ?", (adet, row_index))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Adetler güncellendi'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/list_main_dbs', methods=['GET'])
def list_main_dbs():
    try:
        db_files = [f for f in os.listdir(BASE_DIR) if f.endswith('.db')]
        return jsonify({'status': 'success', 'dbs': db_files})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/get_main_db_table', methods=['GET'])
def get_main_db_table():
    db_name = request.args.get('db_name')
    if not db_name:
        return jsonify({'status': 'error', 'message': 'DB adı gerekli'})
    db_path = os.path.join(BASE_DIR, db_name)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_name = cursor.fetchone()
        if not table_name:
            return jsonify({'status': 'error', 'message': 'Tablo bulunamadı'})
        table_name = table_name[0]
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = [col[1] for col in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'table_name': table_name, 'columns': columns, 'rows': rows})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/save_main_db_table', methods=['POST'])
def save_main_db_table():
    data = request.get_json()
    db_name = data.get('db_name')
    table_name = data.get('table_name')
    columns = data.get('columns')
    rows = data.get('rows')
    if not db_name or not table_name or not columns or not rows:
        return jsonify({'status': 'error', 'message': 'Eksik veri'})
    db_path = os.path.join(BASE_DIR, db_name)
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table_name}")
        placeholders = ','.join(['?'] * len(columns))
        for row in rows:
            cursor.execute(f"INSERT INTO {table_name} ({','.join(columns)}) VALUES ({placeholders})", row)
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Tablo kaydedildi'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    

@app.route('/get_customer_quotes_content', methods=['GET'])
def get_customer_quotes_content():
    import sqlite3
    import pprint
    customer_id = request.args.get('customer_id')
    postcode = request.args.get('postcode')
    if not customer_id or not postcode:
        return jsonify({'status': 'error', 'message': 'Eksik parametre'}), 400

    db_name = f"{str(customer_id).zfill(7)}{postcode}.db"
    db_path = os.path.join(BASE_DIR, "customerhes", db_name)
    if not os.path.exists(db_path):
        return jsonify({'status': 'error', 'message': 'Müşteri veritabanı bulunamadı'}), 404

    qty_list_path = os.path.join(BASE_DIR, "returns_qty_list.db")
    qty_db_exists = os.path.exists(qty_list_path)

    # returns_qty_list.db'den tüm return kayıtlarını önceden çek
    qty_map = {}
    if qty_db_exists:
        qty_conn = sqlite3.connect(qty_list_path)
        qty_c = qty_conn.cursor()
        # Tablo yoksa oluştur!
        qty_c.execute('''
            CREATE TABLE IF NOT EXISTS returns_qty_list (
                RetNumber TEXT,
                QuoteNumber TEXT,
                Orig_Rowid INTEGER,
                Ret_Qty REAL,
                Ded_fee REAL,
                Date TEXT
            )
        ''')
        qty_c.execute("SELECT QuoteNumber, Orig_Rowid, SUM(Ret_Qty) FROM returns_qty_list GROUP BY QuoteNumber, Orig_Rowid")
        for qn, rowid, total_qty in qty_c.fetchall():
            qty_map[(qn, rowid)] = float(total_qty or 0)
        qty_conn.close()
    
    

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT Quotenumber FROM customer_data")
        quote_numbers = [row[0] for row in cursor.fetchall()]

        # S_I değerlerini bir sözlükte tut
        si_map = {}
        cursor.execute("SELECT Quotenumber, S_I FROM customer_data")
        for row in cursor.fetchall():
            si_map[row[0]] = row[1] if row[1] else ""

        conn.close()

        all_rows = []
        quote_row_map = {}

        for qn in quote_numbers:
            quote_db_path = os.path.join(BASE_DIR, "quotes", f"{qn}.db")
            si_value = si_map.get(qn, "")
            if os.path.exists(quote_db_path):
                try:
                    qconn = sqlite3.connect(quote_db_path)
                    qcursor = qconn.cursor()
                    qcursor.execute("SELECT rowid, * FROM list")
                    rows = qcursor.fetchall()

                    quote_rows = []
                    for row in rows:
                        rowid = row[0]
                        row_data = list(row[1:])
                        qtty_idx = 3 if len(row_data) > 3 else 2
                        # Return miktarını returns_qty_list.db'den bul, yoksa 0 al
                        old_ret_qty = 0
                        if qty_db_exists:
                            old_ret_qty = qty_map.get((qn, rowid), 0)
                        try:
                            orig_qtty = float(row_data[qtty_idx])
                        except Exception:
                            orig_qtty = 0
                        new_qtty = max(orig_qtty - old_ret_qty, 0)
                        row_data[qtty_idx] = new_qtty
                        # İsterseniz retqty bilgisini de ekleyebilirsiniz:
                        # full_row = [rowid] + row_data + [qn, si_value, old_ret_qty]
                        full_row = [rowid] + row_data + [qn, si_value]
                        all_rows.append(full_row)
                        quote_rows.append(full_row)
                    quote_row_map[qn] = quote_rows
                    qconn.close()
                except Exception as e:
                    print(f"Quote {qn} için hata: {e}")
                    continue

        # --- DÜZENLİ PRINT ---
        # print("\n--- get_customer_quotes_content Yollanan Bilgiler ---")
        # pprint.pprint({
        #     "customer_id": customer_id,
        #     "postcode": postcode,
        #     "quote_numbers": quote_numbers,
        #     "rows_count": len(all_rows),
        #     "sample_row": all_rows[0] if all_rows else None
        # })
        # print("--- Tüm Satırlar ---")
        # for i, row in enumerate(all_rows):
        #     print(f"{i+1}: {row}")
        # print("--- SONU ---\n")

        # print("\n--- get_customer_quotes_content Toplanan Bilgiler (Gruplanmış) ---")
        # for qn, rows in quote_row_map.items():
        #     print(f"Quote Number: {qn} ({len(rows)} satır)")
        #     for i, row in enumerate(rows):
        #         print(f"  {i+1}: {row}")
        # print("--- TOPLAM SONU ---\n")
        # --- /DÜZENLİ PRINT ---

        return jsonify({'status': 'success', 'rows': all_rows})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500


@app.route('/save_returns', methods=['POST'])
def save_returns():
    import sqlite3
    data = request.get_json()
    returns = data.get('returns', [])
    customer_id = data.get('customer_id', '')
    customer_name = data.get('customer_name', '')
    g_total = data.get('g_total', 0)
    deduct_fee = data.get('deduct_fee', 0)
    if not returns:
        return jsonify({'status': 'error', 'message': 'No return data.'}), 400

    base_dir = os.path.dirname(os.path.abspath(__file__))
    retquotes_dir = os.path.join(base_dir, 'retquotes')
    os.makedirs(retquotes_dir, exist_ok=True)

    # returns_qty_list.db oluştur (yoksa)
    qty_list_path = os.path.join(base_dir, "returns_qty_list.db")
    qty_conn = sqlite3.connect(qty_list_path)
    qty_c = qty_conn.cursor()
    qty_c.execute('''
        CREATE TABLE IF NOT EXISTS returns_qty_list (
            RetNumber TEXT,
            QuoteNumber TEXT,
            Orig_Rowid INTEGER,
            Ret_Qty REAL,
            Ded_fee REAL,
            Date TEXT
        )
    ''')

    # Grupla: {quote_number: [satırlar]}
    grouped = {}
    for row in returns:
        qn = row['quote_number']
        grouped.setdefault(qn, []).append(row)

    # Benzersiz return db ve RetNumber üret
    ret_db_names = {}
    for quote_number, rows in grouped.items():
        existing = [f for f in os.listdir(retquotes_dir) if f.startswith(f"R{quote_number}")]
        suffixes = []
        for f in existing:
            parts = f.replace('.db', '').split('-')
            if len(parts) == 2 and parts[0] == f"R{quote_number}" and parts[1].isdigit():
                suffixes.append(int(parts[1]))
            elif f == f"R{quote_number}.db":
                suffixes.append(1)
        next_suffix = max(suffixes, default=0) + 1
        ret_db_name = f"R{quote_number}-{next_suffix}.db"
        ret_db_names[quote_number] = ret_db_name

        orig_db_path = os.path.join(base_dir, 'quotes', f"{quote_number}.db")
        if not os.path.exists(orig_db_path):
            continue

        # Orijinal kolonları al
        conn_orig = sqlite3.connect(orig_db_path)
        c_orig = conn_orig.cursor()
        c_orig.execute("PRAGMA table_info(list)")
        orig_columns = [col[1] for col in c_orig.fetchall()]
        conn_orig.close()

        # Ekstra kolonlar
        extra_columns = ['Orig_Rowid', 'S_I', 'Ret_Qty', 'Old_Ret_Qty', 'Ded_fee', 'Ret_Amnt']
        all_columns = orig_columns + extra_columns

        # Yeni return db oluştur
        db_path = os.path.join(retquotes_dir, ret_db_name)
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        create_cols = ', '.join([f"{col} TEXT" for col in orig_columns] +
            ["Orig_Rowid INTEGER", "S_I TEXT", "Ret_Qty REAL", "Old_Ret_Qty REAL", "Ded_fee REAL", "Ret_Amnt REAL"])
        c.execute(f"CREATE TABLE IF NOT EXISTS returns ({create_cols})")

        # Satır ekle/güncelle
        for row in rows:
            rowid = int(row['rowid'])
            conn_orig = sqlite3.connect(orig_db_path)
            c_orig = conn_orig.cursor()
            c_orig.execute(f"SELECT * FROM list WHERE rowid = ?", (rowid,))
            orig_row = c_orig.fetchone()
            conn_orig.close()
            if not orig_row:
                continue

            try:
                dsprice_idx = orig_columns.index('DSPRICE')
                dsprice = float(orig_row[dsprice_idx])
            except Exception:
                dsprice = 0.0

            try:
                unit_type_idx = orig_columns.index('UNIT_TYPE')
                item_name_idx = orig_columns.index('ITEM_NAME')
                item_id_idx = orig_columns.index('ITEM_ID')
            except Exception:
                unit_type_idx = None
                item_name_idx = None
                item_id_idx = None

            try:
                fee = float(str(deduct_fee).replace(',', '.'))
            except Exception:
                fee = 0.0

            # Old_Ret_Qty returns_qty_list.db'den toplanacak
            qty_c.execute("SELECT SUM(Ret_Qty) FROM returns_qty_list WHERE QuoteNumber=? AND Orig_Rowid=? AND Ded_fee=?", (quote_number, rowid, fee))
            old_ret_qty = float(qty_c.fetchone()[0] or 0)
            new_ret_qty = float(row['ret_qty'])
            new_old_ret_qty = old_ret_qty + new_ret_qty

            # --- RET_AMNT HESAPLAMA BLOKU ---
            # item_name ve unit_type kontrolü
            unit_type = str(orig_row[unit_type_idx]).strip().upper() if unit_type_idx is not None else ""
            item_name = str(orig_row[item_name_idx]).strip() if item_name_idx is not None else ""
            dsprice = float(orig_row[dsprice_idx]) if dsprice_idx is not None else 0.0

            # Varsayılan ret_amnt
            ret_amnt = (dsprice * new_ret_qty) - ((dsprice * new_ret_qty) * fee / 100)

            if unit_type.lower() == "add refrigeration":
                # item_name'de unpack veya remove geçiyor mu?
                if any(x in item_name.lower() for x in ["unpack", "remove"]):
                    # İlk '\' işaretine kadar olan kısmı al
                    base_name = item_name.split('\\')[0].strip() if '\\' in item_name else item_name.strip()
                    # refrigeration.db'den unpack ve remove değerlerini çek
                    try:
                        conn_ref = sqlite3.connect('refrigeration.db')
                        c_ref = conn_ref.cursor()
                        c_ref.execute("SELECT UnpackPosition, RemoveDispose FROM REFRIGERATION WHERE LOWER(REPLACE(Model, ' ', '')) = LOWER(REPLACE(?, ' ', ''))",(base_name.replace(' ', '').lower(),))
                        ref_row = c_ref.fetchone()
                        conn_ref.close()
                        unpack_val = float(ref_row[0]) if ref_row and ref_row[0] else 0.0
                        remove_val = float(ref_row[1]) if ref_row and ref_row[1] else 0.0
                        # Eğer item_name'de unpack varsa çıkar
                        if "unpack" in item_name.lower():
                            ret_amnt -= unpack_val * new_ret_qty
                        # Eğer item_name'de remove varsa çıkar
                        if "remove" in item_name.lower():
                            ret_amnt -= remove_val * new_ret_qty
                    except Exception as e:
                        print(f"Unpack/Remove kontrolünde hata: {e}")
            # --- /RET_AMNT HESAPLAMA BLOKU ---

            extra_values = [
                rowid,  # Orig_Rowid
                row.get('s_i', ''),
                new_ret_qty,  # Ret_Qty (bu işlemdeki)
                new_old_ret_qty,  # Old_Ret_Qty (tüm return toplamı)
                fee,
                ret_amnt
            ]
            insert_values = list(orig_row) + extra_values

            placeholders = ','.join(['?'] * len(insert_values))
            c.execute(f"INSERT INTO returns ({','.join(all_columns)}) VALUES ({placeholders})", insert_values)

            # --- returns_qty_list.db'ye ekle ---
            qty_c.execute('''
                INSERT INTO returns_qty_list (RetNumber, QuoteNumber, Orig_Rowid, Ret_Qty, Ded_fee, Date)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (ret_db_name.replace('.db', ''), quote_number, rowid, new_ret_qty, fee, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))

            # --- RETURN STOCK UPDATE BLOKU (id ile) ---
            if unit_type_idx is not None and item_name_idx is not None:
                unit_type = str(orig_row[unit_type_idx]).strip().upper()
                item_name = str(orig_row[item_name_idx]).strip()
                if '\\' in item_name:
                    item_name = item_name.split('\\')[0].strip()
                ret_qty = new_ret_qty

                if unit_type.lower() in [ "add_item", "worktop"]:
                    pass
                elif unit_type.lower() == "add refrigeration":
                    try:
                        conn_ref = sqlite3.connect('refrigeration.db')
                        c_ref = conn_ref.cursor()
                        c_ref.execute("UPDATE REFRIGERATION SET Qty = Qty + ? WHERE LOWER(REPLACE(Model, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (ret_qty, item_name))
                        conn_ref.commit()
                        conn_ref.close()
                    except Exception as e:
                        print(f"Refrigeration güncelleme hatası: {e}")
                elif unit_type.lower() == "wood":
                    try:
                        conn_wood = sqlite3.connect('wood.db')
                        c_wood = conn_wood.cursor()
                        c_wood.execute("UPDATE wood_tbl SET QTY = QTY + ? WHERE LOWER(REPLACE(ITEM_NAME, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (ret_qty, item_name))
                        conn_wood.commit()
                        conn_wood.close()
                    except Exception as e:
                        print(f"Wood güncelleme hatası: {e}")
                elif unit_type.lower() == "ceiling":
                    try:
                        conn_ceiling = sqlite3.connect('ceiling.db')
                        c_ceiling = conn_ceiling.cursor()
                        c_ceiling.execute("UPDATE ceiling_data SET Qty = Qty + ? WHERE Code = ?", (ret_qty, orig_row[item_id_idx]))
                        conn_ceiling.commit()
                        conn_ceiling.close()
                    except Exception as e:
                        print(f"Ceiling güncelleme hatası: {e}")

                elif unit_type.lower() == "add catering":
                    try:
                        conn_catering = sqlite3.connect('catering.db')
                        c_catering = conn_catering.cursor()
                        c_catering.execute("UPDATE catering_tbl SET Qty = Qty + ? WHERE LOWER(REPLACE(Model, ' ', '')) = LOWER(REPLACE(?, ' ', ''))", (ret_qty, item_name))

                        
                        conn_catering.commit()
                        conn_catering.close()
                    except Exception as e:
                        print(f"Catering güncelleme hatası: {e}")

                else:
                    try:
                        # ID ile stok güncelle
                        if item_id_idx is not None:
                            item_id = orig_row[item_id_idx]
                            conn_prc = sqlite3.connect('prc_tbl.db')
                            c_prc = conn_prc.cursor()
                            c_prc.execute("UPDATE prc_tbl SET quantity = quantity + ? WHERE id = ?", (ret_qty, item_id))
                            conn_prc.commit()
                            conn_prc.close()
                        else:
                            # Eğer ITEM_ID yoksa eski yöntemle name1 ile güncelle
                            conn_prc = sqlite3.connect('prc_tbl.db')
                            c_prc = conn_prc.cursor()
                            c_prc.execute("UPDATE prc_tbl SET quantity = quantity + ? WHERE LOWER(name1) = LOWER(?)", (ret_qty, item_name.lower()))
                            conn_prc.commit()
                            conn_prc.close()
                    except Exception as e:
                        print(f"prc_tbl güncelleme hatası: {e}")
            # --- /RETURN STOCK UPDATE BLOKU ---

        conn.commit()
        conn.close()

    qty_conn.commit()
    qty_conn.close()

    # Yeni fonksiyonu çağır
    create_CR_list(returns, customer_id, customer_name, g_total, deduct_fee, ret_db_names)
    return jsonify({'status': 'success', 'message': 'Returns saved.'})

# Yeni fonksiyon: create_CR_list
def create_CR_list(returns, customer_id, customer_name, g_total, deduct_fee, ret_db_names=None):
    """
    Returns listesini cr_note_list.db'ye kaydeder.
    Kolonlar: User_id, Customer_id, Customer_Name, RetNumber, Description, Amounth, s_i, State, Used_quote, Date
    """
    from datetime import datetime

    base_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(base_dir, "cr_note_list.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cr_note_list (
            User_id TEXT,
            Customer_id TEXT,
            Customer_Name TEXT,
            RetNumber TEXT,
            Description TEXT,
            Amounth REAL,
            s_i TEXT,
            State TEXT,
            Used_quote TEXT,
            Date TEXT,
            U_P_Date TEXT
        )
    ''')

    user_id = str(session.get('user_id', ''))
    now = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

    for row in returns:
        quote_number = str(row.get('quote_number', ''))
        # Yeni RetNumber: Rxxxxxxx-N
        if ret_db_names and quote_number in ret_db_names:
            ret_number = ret_db_names[quote_number].replace('.db', '')
        else:
            # fallback: eski sistem
            ret_number = "R" + quote_number

        s_i = row.get('s_i', '')
        state = ''
        # --- Amounth hesaplama ---
        ret_db_path = os.path.join(base_dir, "retquotes", f"{ret_number}.db")
        Ret_Amnt_sum = 0
        if os.path.exists(ret_db_path):
            rconn = sqlite3.connect(ret_db_path)
            rc = rconn.cursor()
            try:
                rc.execute("SELECT Ret_Amnt FROM returns")
                Ret_Amnt = rc.fetchall()
                Ret_Amnt_sum = sum(float(x[0]) for x in Ret_Amnt if x[0] is not None)
            except Exception as e:
                print(f"Ret DB okuma hatası: {e}")
            rconn.close()
        amounth = Ret_Amnt_sum
        # ------------------------

        used_quote = ""  # Şimdilik boş
        description = f"Credit Note for '{quote_number}'"

        # Aynı RetNumber varsa güncelle, yoksa yeni satır ekle
        c.execute("SELECT 1 FROM cr_note_list WHERE RetNumber = ?", (ret_number,))
        exists = c.fetchone()
        if exists:
            c.execute('''
                UPDATE cr_note_list
                SET User_id=?, Customer_id=?, Customer_Name=?, Description=?, Amounth=?, s_i=?, State=?, Used_quote=?, Date=?
                WHERE RetNumber=?
            ''', (user_id, customer_id, customer_name, description, amounth, s_i, state, used_quote, now, ret_number))
        else:
            c.execute('''
                INSERT INTO cr_note_list (User_id, Customer_id, Customer_Name, RetNumber, Description, Amounth, s_i, State, Used_quote, Date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, customer_id, customer_name, ret_number, description, amounth, s_i, state, used_quote, now))

        # --- CREDIT NOTE PDF ve MAIL ---
        if s_i == "I":
            # Müşteri e-posta adresini customers.db'den çek
            customer_email = 'volkanballi@gmail.com'
            try:
                customers_db_path = os.path.join(base_dir, 'customers.db')
                conn_cust = sqlite3.connect(customers_db_path)
                c_cust = conn_cust.cursor()
                c_cust.execute("SELECT email FROM customers WHERE id = ?", (customer_id,))
                row_email = c_cust.fetchone()
                if row_email and row_email[0]:
                    customer_email = row_email[0]
                conn_cust.close()
            except Exception as e:
                print(f"Credit Note PDF için e-posta çekme hatası: {e}")

            if customer_email:
                credit_not_pdf(ret_number, description, amounth, customer_name, customer_email)
            else:
                print(f"Credit Note PDF için e-posta adresi bulunamadı (customer_id={customer_id})")

    conn.commit()
    conn.close()


def credit_not_pdf(ret_number, description, amounth, customer_name, customer_email, date=None):
    """
    Credit Note PDF oluşturur ve e-posta ile gönderir.
    Invoice ile aynı header ve logo kullanılır.
    """
    from datetime import datetime
    if not date:
        date = datetime.now().strftime('%d-%m-%Y')

    class CreditNotePDF(InvoicePDF):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.invoice_date = date  # Header'da tarih için

        # InvoicePDF'in header ve footer'ı otomatik uygulanacak

    pdf = CreditNotePDF()
    pdf.add_page()
    pdf.set_font("Helvetica", '', 11)
    pdf.cell(0, 8, f"Customer: {customer_name}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(5)
    # Tablo başlıkları
    pdf.set_font("Helvetica", 'B', 11)
    pdf.cell(50, 8, "RetNumber", border=1, align='C')
    pdf.cell(90, 8, "Description", border=1, align='C')
    pdf.cell(40, 8, "Amounth", border=1, align='C')
    pdf.ln()
    # Tablo verisi
    pdf.set_font("Helvetica", '', 11)
    pdf.cell(50, 8, ret_number, border=1)
    pdf.cell(90, 8, description, border=1)
    pdf.cell(40, 8, f"{amounth:.2f}", border=1, align='R')
    pdf.ln()

    # PDF'yi bellekte oluştur
    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    # E-posta gönderimi
    sender_email = "easyfatgon@gmail.com"  # Gönderen e-posta adresi
    sender_password = "bchm xdew ywhc vqzj"  # Gönderen e-posta şifresi (uygun şekilde değiştir)
    recipient_email = customer_email

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"Credit Note {ret_number}"

    body = f"Dear Customer,\n\nPlease find attached the credit note for {ret_number}.\n\nBest regards,\nYour Company"
    msg.attach(MIMEText(body, 'plain'))

    attachment = MIMEBase('application', 'octet-stream')
    attachment.set_payload(pdf_buffer.read())
    encoders.encode_base64(attachment)
    attachment.add_header('Content-Disposition', f'attachment; filename=CreditNote_{ret_number}.pdf')
    msg.attach(attachment)

    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        # print(f"Credit Note PDF sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"Credit Note email send error: {e}")
        return False


@app.route('/get_credit_note_list', methods=['GET'])
def get_credit_note_list():
    customer_id = request.args.get('customer_id')
    if not customer_id:
        return jsonify({'status': 'success', 'rows': []})
    try:
        db_path = os.path.join(BASE_DIR, "cr_note_list.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute('''
            SELECT User_id, Customer_id, Customer_Name, RetNumber, Description, Amounth, s_i, State, Used_quote, Date, U_P_Date
            FROM cr_note_list
            WHERE Customer_id = ?
            ORDER BY Date DESC
        ''', (customer_id,))
        rows = c.fetchall()
        conn.close()
        return jsonify({'status': 'success', 'rows': rows})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/save_cr_note_selection', methods=['POST'])
def save_cr_note_selection():
    try:
        data = request.get_json()
        used_quote = data.get('used_quote')
        selected_notes = data.get('selected_notes', [])
        unselected_notes = data.get('unselected_notes', [])

        if not used_quote:
            return jsonify({'status': 'error', 'message': 'Eksik veri'}), 400

        base_dir = os.path.dirname(os.path.abspath(__file__))

        # 1. cr_note_selection.db'ye kaydet (sadece seçili olanlar)
        sel_db_path = os.path.join(base_dir, "cr_note_selection.db")
        conn_sel = sqlite3.connect(sel_db_path)
        c_sel = conn_sel.cursor()
        c_sel.execute('''
            CREATE TABLE IF NOT EXISTS cr_note_selection (
                RetNumber TEXT PRIMARY KEY,
                Used_quote TEXT
            )
        ''')
        for note in selected_notes:
            ret_number = note.get('retNumber')
            if ret_number:
                c_sel.execute('REPLACE INTO cr_note_selection (RetNumber, Used_quote) VALUES (?, ?)', (ret_number, used_quote))
        # Unselected olanları sil
        for note in unselected_notes:
            ret_number = note.get('retNumber')
            if ret_number:
                c_sel.execute('DELETE FROM cr_note_selection WHERE RetNumber = ?', (ret_number,))
        conn_sel.commit()
        conn_sel.close()

        # 2. cr_note_list.db'de güncelle
        cr_db_path = os.path.join(base_dir, "cr_note_list.db")
        conn_cr = sqlite3.connect(cr_db_path)
        c_cr = conn_cr.cursor()
        # Seçili olanlar: Used ve Used_quote ata
        for note in selected_notes:
            ret_number = note.get('retNumber')
            if ret_number:
                c_cr.execute('''
                    UPDATE cr_note_list
                    SET Used_quote = ?, State = 'Used'
                    WHERE RetNumber = ?
                ''', (used_quote, ret_number))
        # Seçili olmayanlar: Used_quote ve State'i temizle
        for note in unselected_notes:
            ret_number = note.get('retNumber')
            if ret_number:
                c_cr.execute('''
                    UPDATE cr_note_list
                    SET Used_quote = '', State = ''
                    WHERE RetNumber = ?
                ''', (ret_number,))
        conn_cr.commit()
        conn_cr.close()

        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    
@app.route('/get_cr_note_amounth_total')
def get_cr_note_amounth_total():
    used_quote = request.args.get('used_quote')
    # print(f"[get_cr_note_amounth_total] Gelen used_quote: {used_quote}")  # Gelen değeri yazdır
    if not used_quote:
        return jsonify({'status': 'error', 'message': 'Eksik parametre'})
    try:
        db_path = os.path.join(BASE_DIR, "cr_note_list.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("SELECT SUM(Amounth) FROM cr_note_list WHERE Used_quote = ?", (used_quote,))
        total = c.fetchone()[0] or 0.0
        conn.close()
        # print(f"[get_cr_note_amounth_total] Gönderilen toplam: {total}")  # Gönderilen değeri yazdır
        return jsonify({'status': 'success', 'total': total})
    except Exception as e:
        print(f"[get_cr_note_amounth_total] Hata: {e}")
        return jsonify({'status': 'error', 'message': str(e)})


@app.route('/pay_credit_note', methods=['POST'])
def pay_credit_note():
    try:
        data = request.get_json()
        ret_numbers = data.get('ret_numbers', [])
        if not ret_numbers:
            return jsonify({'status': 'error', 'message': 'No RetNumber selected.'})
        db_path = os.path.join(BASE_DIR, "cr_note_list.db")
        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        for ret_number in ret_numbers:
            c.execute("UPDATE cr_note_list SET State = 'Paid' WHERE RetNumber = ?", (ret_number,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)})
    


@app.route('/export_db_excel')
def export_db_excel():
    db_name = request.args.get('db_name')
    if not db_name:
        return "Eksik parametre: db_name", 400
    db_path = os.path.join(BASE_DIR, db_name)
    if not os.path.exists(db_path):
        return f"{db_name} bulunamadı.", 404
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_name = cursor.fetchone()
        if not table_name:
            return "Tablo bulunamadı.", 404
        table_name = table_name[0]
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", conn)
        df = df.where(pd.notnull(df), None)
        conn.close()
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name=table_name)  # sheet_name tablo adı
        output.seek(0)
        return send_file(
            output,
            download_name=f"{db_name.replace('.db','')}.xlsx",
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        return f"Hata: {str(e)}", 500


@app.route('/import_excel_to_db', methods=['POST'])
def import_excel_to_db():
    from werkzeug.utils import secure_filename
    excel_file = request.files.get('excel_file')
    db_name = request.form.get('db_name')
    if not excel_file or not db_name:
        return jsonify({'status': 'error', 'message': 'Eksik parametre'}), 400
    db_path = os.path.join(BASE_DIR, db_name)
    if not os.path.exists(db_path):
        return jsonify({'status': 'error', 'message': f'{db_name} bulunamadı.'}), 404
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        table_name = cursor.fetchone()
        if not table_name:
            return jsonify({'status': 'error', 'message': 'Tablo bulunamadı.'}), 404
        table_name = table_name[0]
        # Excel'den sheet adı ile oku
        df = pd.read_excel(excel_file, sheet_name=table_name)
        # ...devamı aynı...
        cursor.execute(f"PRAGMA table_info({table_name})")
        db_info = cursor.fetchall()
        db_columns = [col[1] for col in db_info]
        db_types = [col[2].upper() for col in db_info]
        excel_columns = list(df.columns)
        if db_columns != excel_columns:
            return jsonify({'status': 'error', 'message': f'Excel ve tablo sütunları aynı değil!\nDB: {db_columns}\nExcel: {excel_columns}'}), 400
        # ...devamı aynı...
        cursor.execute(f"DELETE FROM {table_name}")
        for _, row in df.iterrows():
            cursor.execute(
                f"INSERT INTO {table_name} ({','.join(db_columns)}) VALUES ({','.join(['?']*len(db_columns))})",
                tuple(row)
            )
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500
    


@app.route('/get_catering_groups', methods=['GET'])
def get_catering_groups():
    try:
        conn = sqlite3.connect('catering.db')
        cursor = conn.cursor()
        cursor.execute('SELECT DISTINCT "GroupName" FROM catering_tbl')
        groups = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'groups': groups})
    except Exception as e:
        print("Hata (get_catering_groups):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_catering_items', methods=['GET'])
def get_catering_items():
    try:
        group = request.args.get('group')
        if not group:
            return jsonify({'status': 'error', 'message': 'Group parametresi eksik.'}), 400

        conn = sqlite3.connect('catering.db')
        cursor = conn.cursor()
        cursor.execute('SELECT Model FROM catering_tbl WHERE LOWER("GroupName") = LOWER(?)', (group,))
        items = [row[0] for row in cursor.fetchall()]
        conn.close()
        return jsonify({'status': 'success', 'items': items})
    except Exception as e:
        print("Hata (get_catering_items):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_catering_price', methods=['GET'])
def get_catering_price():
    try:
        model_name = request.args.get('model')
        customer_type = request.args.get('customer_type')
        if not model_name or not customer_type:
            return jsonify({'status': 'error', 'message': 'Model veya müşteri tipi eksik.'}), 400

        conn = sqlite3.connect('catering.db')
        cursor = conn.cursor()

        if customer_type == "Retail":
            cursor.execute('SELECT RetailPrice FROM catering_tbl WHERE LOWER(Model) = LOWER(?)', (model_name,))
        elif customer_type == "Trade":
            cursor.execute('SELECT TradePrice FROM catering_tbl WHERE LOWER(Model) = LOWER(?)', (model_name,))
        else:
            return jsonify({'status': 'error', 'message': 'Geçersiz müşteri tipi.'}), 400

        result = cursor.fetchone()
        conn.close()

        if result:
            price = result[0]
            return jsonify({'status': 'success', 'price': price})
        else:
            return jsonify({'status': 'error', 'message': 'Model bulunamadı.'}), 404
    except Exception as e:
        print("Hata (get_catering_price):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_catering_item_details', methods=['GET'])
def get_catering_item_details():
    try:
        model_name = request.args.get('model')
        if not model_name:
            return jsonify({'status': 'error', 'message': 'Model adı belirtilmedi.'}), 400

        conn = sqlite3.connect('catering.db')
        cursor = conn.cursor()
        cursor.execute('''
            SELECT Warranty, UnpackPosition, RemoveDispose, TradePrice, Kar
            FROM catering_tbl
            WHERE LOWER(Model) = LOWER(?)
        ''', (model_name,))
        result = cursor.fetchone()
        conn.close()

        if result:
            return jsonify({
                'status': 'success',
                'warranty': result[0],
                'unpack': result[1],
                'remove': result[2],
                'tradePrice': result[3],
                'kar': result[4]
            })
        else:
            return jsonify({'status': 'error', 'message': 'Model bulunamadı.'}), 404
    except Exception as e:
        print("Hata (get_catering_item_details):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/add_catering_data', methods=['POST'])
def add_catering_data():
    try:
        data = request.get_json()
        catering_data = data.get('catering_data', [])
        largest_file = str(data.get('largest_file', '')).strip()

        if not catering_data:
            return jsonify({"status": "error", "message": "Geçerli veri yok."}), 400

        new_db_path = os.path.join(QUOTE_DB_PATH, f"{largest_file}.db")
        conn_quote = sqlite3.connect(new_db_path)
        cursor_quote = conn_quote.cursor()

        cursor_quote.execute('''
            CREATE TABLE IF NOT EXISTS list (
                USER_ID INTEGER,
                ITEM_ID TEXT NOT NULL,
                ITEM_NAME TEXT NOT NULL,
                ADET INTEGER NOT NULL,
                UNIT_TYPE TEXT DEFAULT 'ADD_ITEM',
                SIRA DECIMAL(10, 2),
                PRICE DECIMAL(10, 2),
                DSPRICE DECIMAL(10, 2),
                AMOUNTH DECIMAL(10, 2),
                DEPO DECIMAL(10, 2),
                IMPORT DECIMAL(10, 2),
                KG DECIMAL(10, 2) DEFAULT 0.0,
                COLOUR TEXT 
            )
        ''')

        user_id = session.get('user_id', 0)
        sira = 7200  # Sıra değeri başlangıç

        for item in catering_data:
            sku = item.get('sku', '')
            quantity = item.get('quantity', 0)
            dprice = item.get('dprice', 0.0)
            xtra = item.get('xtra', 0.0)

            import_value = 0.0
            if '-' in sku:
                parts = sku.split('-')
                prefix = parts[0].strip()
                suffix = parts[1].strip()
                match_prefix = re.search(r'\d+', prefix)
                match_suffix = re.search(r'\d+', suffix)
                if match_prefix and match_suffix:
                    prefix_value = float(match_prefix.group())
                    suffix_value = float(match_suffix.group())
                    import_value = prefix_value - suffix_value
            depo = quantity * ((dprice - import_value)-xtra)
            cursor_quote.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                sku,
                item.get('itemName', ''),
                quantity,
                item.get('unitType', 'Add Catering'),
                round(sira, 2),
                item.get('price', 0.0),
                dprice,
                quantity * dprice,
                depo,
                import_value
            ))
            sira += 1
        conn_quote.commit()
        conn_quote.close()
        return jsonify({"status": "success", "message": "Catering verileri başarıyla kaydedildi!"})
    except sqlite3.Error as e:
        print("Veritabanı hatası (add_catering_data):", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500
    except Exception as e:
        print("Beklenmeyen hata (add_catering_data):", str(e))
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/save_catering_selection', methods=['POST'])
def save_catering_selection():
    try:
        data = request.get_json()
        quote_number = data.get('quote_number')
        customer_type = data.get('customer_type')
        catering_dsc = data.get('catering_dsc')
        selections = data.get('selections')

        if not quote_number or not selections:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        db_path = os.path.join(BASE_DIR, "catering_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS catering_selections (
                Quote_number TEXT NOT NULL,
                Customer_type TEXT DEFAULT '',
                Catering_dsc REAL DEFAULT 0.0,
                Row_index INTEGER NOT NULL,
                Group_name TEXT DEFAULT '',
                Item_name TEXT DEFAULT '',
                Warranty INTEGER DEFAULT '',
                Unpack INTEGER DEFAULT '',
                Remove INTEGER DEFAULT '',
                Quantity INTEGER DEFAULT 0,
                Price REAL DEFAULT 0.0,
                Discounted_price REAL DEFAULT 0.0,
                Discount REAL DEFAULT 0.0,
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')

        cursor.execute('DELETE FROM catering_selections WHERE Quote_number = ?', (quote_number,))

        for row_index, selection in enumerate(selections):
            cursor.execute('''
                INSERT INTO catering_selections (Quote_number, Customer_type, Catering_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price, Discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                quote_number,
                customer_type,
                float(catering_dsc) if catering_dsc else 0.0,
                row_index,
                selection.get('group_name', ''),
                selection.get('item_name', ''),
                selection.get('warranty', ''),
                selection.get('unpack', ''),
                selection.get('remove', ''),
                int(selection.get('quantity', 0)),
                float(selection.get('price', 0.0)),
                float(selection.get('discounted_price', 0.0)),
                float(selection.get('discount', 0.0))
            ))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Catering seçimleri kaydedildi.'})
    except Exception as e:
        print("Hata (save_catering_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/load_catering_selection', methods=['GET'])
def load_catering_selection():
    try:
        quote_number = request.args.get('quote_number')

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        db_path = os.path.join(BASE_DIR, "catering_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT Customer_type, Catering_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price, Discount
            FROM catering_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        customer_type = rows[0][0] if rows else ''
        catering_dsc = rows[0][1] if rows else 0.0

        selections = [
            {
                'row_index': row[2],
                'group_name': row[3],
                'item_name': row[4],
                'warranty': row[5],
                'unpack': row[6],
                'remove': row[7],
                'quantity': row[8],
                'price': row[9],
                'discounted_price': row[10],
                'discount': row[11] if len(row) > 11 else 0
            }
            for row in rows
        ]
        return jsonify({
            'status': 'success',
            'customer_type': customer_type,
            'catering_dsc': catering_dsc,
            'selections': selections
        })
    except Exception as e:
        print("Hata (load_catering_selection):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500
    




@app.route('/save_customer_note', methods=['POST'])
def save_customer_note():
    try:
        data = request.get_json()
        customer_id = str(data.get('customer_id', '')).zfill(7)
        note = data.get('note', '')
        if not customer_id:
            return jsonify({'status': 'error', 'message': 'Eksik müşteri ID'}), 400

        db_path = os.path.join(BASE_DIR, "customer_notes.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS customer_notes (
                customer_id TEXT PRIMARY KEY,
                note TEXT
            )
        ''')
        cursor.execute('REPLACE INTO customer_notes (customer_id, note) VALUES (?, ?)', (customer_id, note))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/get_customer_note', methods=['GET'])
def get_customer_note():
    customer_id = str(request.args.get('customer_id', '')).zfill(7)
    if not customer_id:
        return jsonify({'status': 'error', 'message': 'Eksik müşteri ID'}), 400
    db_path = os.path.join(BASE_DIR, "customer_notes.db")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS customer_notes (
            customer_id TEXT PRIMARY KEY,
            note TEXT
        )
    ''')
    cursor.execute('SELECT note FROM customer_notes WHERE customer_id = ?', (customer_id,))
    row = cursor.fetchone()
    conn.close()
    note = row[0] if row else ''
    return jsonify({'status': 'success', 'note': note})


if __name__ == '__main__':
    app.run(debug=True)