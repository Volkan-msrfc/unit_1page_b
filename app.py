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



app = Flask(__name__)

app.permanent_session_lifetime = timedelta(minutes=60)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# quotes dizinine giden yolu ayarlayın
QUOTE_DB_PATH = os.path.join(BASE_DIR, 'quotes')

app.secret_key = 'colacola998346'  # Güvenli bir anahtar belirleyin

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

        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, password, authority, status FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()

        if user:
            if user[3] != "active":
                conn.close()
                error = "Your login permission has been revoked. Please contact the administrator."
                return render_template('login.html', error=error)
            if check_password_hash(user[1], password):
                session.permanent = True
                session['user'] = username
                session['user_id'] = user[0]
                session['authority'] = user[2] if len(user) > 2 else 'user'

                # Aynı kullanıcıdan eski oturumları sil
                cursor.execute("DELETE FROM active_users WHERE user_id = ?", (user[0],))
                cursor.execute("""
                    INSERT INTO active_users (user_id, username, login_time)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                """, (user[0], username))
                conn.commit()
                conn.close()

                return redirect(url_for('menu'))
            else:
                conn.close()
                error = "Wrong user name or password."
                return render_template('login.html', error=error)
        else:
            conn.close()
            error = "Wrong user name or password."
            return render_template('login.html', error=error)

    return render_template('login.html')


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
                ikishelf = qty * unit_piece
            else:
                ikishelf = 0

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece

            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = qty_option8 * shelf_size_option9
            else:
                ucshelf = 0

            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, ucshelf, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            if shelf_size_option11 == 0 or qty_option10 == 0:
                dortshelf = 0
            else:
                dortshelf = qty_option10 * shelf_size_option11
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
                ucshelf = qty_option8 * unit_piece
            else:
                ucshelf = 0

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
                ucshelf = qty_option8 * unit_piece
            else:
                ucshelf = 0

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

            if shelf_size == 0:
                ikishelf = 0  # birshelf değerini sıfırla
            else:
                ikishelf = qty * unit_piece
            cursor.execute('''
            UPDATE veg_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, ikishelf, unit_type, row_index))

             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            if shelf_size_option9 == 0 or qty_option8 == 0:
                ucshelf = qty_option8 * unit_piece
            else:
                ucshelf = 0

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
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + birprc)), unit_type, row_index))

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
                ucshelf = qty_option8 * unit_piece
            else:
                ucshelf = 0

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
                ucshelf = qty_option8 * unit_piece
            else:
                ucshelf = 0

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
                KG DECIMAL(10, 2) DEFAULT 0.00
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

            # local_price = round(local_price, 2)  # Ensure 2 decimal places
            local_price = float(f"{local_price:.2f}")
            print(f"Eklenmeye çalışılan veri: {item_name}, adet={adet}, sira={sira}, eşleşen_id={item_id}")
            rows_with_user_id.append((user_id, item_id, item_name, adet, unit_type, sira, local_price, 0.00, 0.00, 0.00, import_price, kg))

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

        print(f"Quote list database created successfully: {new_db_path}")

    except sqlite3.Error as e:
        print("Veritabanı hatası (create_quote_list):", str(e))
    except Exception as e:
        print("Beklenmeyen hata (create_quote_list):", str(e))

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
        cursor.execute('SELECT PRICE, ADET, SIRA, DSPRICE, IMPORT FROM list')
        rows = cursor.fetchall()

        updated_rows = []
        for row in rows:
            price, adet, sira, dsprice, import_value = row
            price = price or 0
            adet = adet or 0
            import_value = import_value or 0

            # Sıra numarası 1 ile başlıyorsa indirim uygula
            if sira < 7000:
                new_dsprice = round(price * (1 - dsc / 100), 2)
            else:
                new_dsprice = dsprice  # İndirim uygulanmaz

            amounth = round(adet * new_dsprice, 2)
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
        customer_id = data.get('customer_id')      # <-- eklendi
        customer_name = data.get('customer_name')  # <-- eklendi
        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        prep_up_qt(quote_number, dsc, del_pr, customer_id, customer_name)  # <-- müşteri bilgilerini ilet

        return jsonify({'status': 'success', 'message': f'{quote_number} için prep_up_qt çağrıldı.'})
    except Exception as e:
        print(f"prep_up_qt endpoint hatası: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def prep_up_qt(clean_string, dsc, del_pr, customer_id, customer_name):
    try:
        user_id = session.get('user_id', 0)
        user_name = session.get('user', 'Unknown User')
        # Artık müşteri bilgisi parametreden geliyor!
        update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc, del_pr)
        print(f"prep_up_qt: {clean_string} için update_quotes_db çağrıldı.")
    except Exception as e:
        print(f"prep_up_qt sırasında hata oluştu: {str(e)}")

def update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc, del_pr):
    try:
        # quotes.db dosyasının yolunu belirleyin
        quotes_db_path = os.path.join(BASE_DIR, "quotes.db")

        # quotes.db veritabanını oluştur veya aç
        conn_quotes = sqlite3.connect(quotes_db_path)
        cursor_quotes = conn_quotes.cursor()

        # quotes tablosunu oluştur (eğer yoksa)
        cursor_quotes.execute('''
            CREATE TABLE IF NOT EXISTS quotes (
                Quote_number TEXT NOT NULL,  -- 00000001 gibi numaraları tutar
                User_id INTEGER NOT NULL,    -- Kullanıcı ID'si
                User_name TEXT NOT NULL,     -- Kullanıcı adı
                Customer_id TEXT,         -- Müşteri ID'si
                Customer_name TEXT,          -- Müşteri adı
                Discount DECIMAL(10, 2),     -- İndirim oranı
                Amount DECIMAL(10, 2) NOT NULL, -- Toplam tutar
                Sold TEXT,                    -- Satış durumu (1 harf)
                Inv TEXT,                    -- Fatura durumu (1 harf)
                created_at TEXT DEFAULT (strftime('%d-%m-%Y %H:%M:%S', 'now', 'localtime')), -- Kayıt tarihi ve saati
                Delpr INTEGER DEFAULT 0 -- Fiyatlandırma durumu (0 veya 1)
            )
        ''')

        # Oluşturulan veritabanının yolunu belirleyin
        new_db_path = os.path.join(QUOTE_DB_PATH, f"{clean_string}.db")

        # Oluşturulan veritabanına bağlan
        conn_new_db = sqlite3.connect(new_db_path)
        cursor_new_db = conn_new_db.cursor()

        # Amount sütunundaki değerlerin toplamını hesapla
        cursor_new_db.execute('SELECT SUM(AMOUNTH) FROM list')
        total_amount = cursor_new_db.fetchone()[0] or 0.0  # Eğer sonuç None ise 0.0 olarak ayarla

        # Sunucunun tarih ve saatini al
        current_time1 = datetime.now().strftime('%d-%m-%Y %H:%M:%S')

        # `Quote_number` zaten var mı kontrol et
        cursor_quotes.execute('SELECT COUNT(*) FROM quotes WHERE Quote_number = ?', (clean_string,))
        quote_exists = cursor_quotes.fetchone()[0] > 0

        if quote_exists:
            # Eğer `Quote_number` zaten varsa, satırı güncelle
            cursor_quotes.execute('''
                UPDATE quotes
                SET User_id = ?, User_name = ?, Customer_id = ?, Customer_name = ?, Discount = ?, Amount = ?, Sold = ?, Inv = ?, created_at = ?, Delpr= ?
                WHERE Quote_number = ?
            ''', (user_id, user_name, customer_id, customer_name, dsc, total_amount, '', '', current_time1, del_pr, clean_string))
            print(f"Quotes database updated for existing Quote_number: {clean_string}")
        else:
            # Eğer `Quote_number` yoksa, yeni bir satır ekle
            cursor_quotes.execute('''
                INSERT INTO quotes (Quote_number, User_id, User_name, Customer_id, Customer_name, Discount, Amount, Sold, Inv, created_at, Delpr)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (clean_string, user_id, user_name, customer_id, customer_name, dsc, total_amount, '', '', current_time1, del_pr))
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
                KG DECIMAL(10, 2) DEFAULT 0.0 -- Yeni kolon eklendi
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
                KG DECIMAL(10, 2) DEFAULT 0.0 -- Yeni kolon eklendi
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        sira = 7000  # Sıra değeri başlangıç

        # Gelen verileri işleyip tabloya ekle
        for item in ref_data:
            sku = item.get('sku', '')
            quantity = item.get('quantity', 0)
            dprice = item.get('dprice', 0.0)
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
            depo = quantity*(dprice-import_value)
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
            print(f"SKU: {sku}, Import Value: {import_value}")  # Yeni print ifadesi
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
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM ref_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        for row_index, selection in enumerate(selections):
            cursor.execute('''
                INSERT INTO ref_selections (Quote_number, Customer_type, Ref_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                float(selection.get('discounted_price', 0.0))
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
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # Veritabanına bağlan
        db_path = os.path.join(BASE_DIR, "ref_selections.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Seçimleri al
        cursor.execute('''
            SELECT Customer_type, Ref_dsc, Row_index, Group_name, Item_name, Warranty, Unpack, Remove, Quantity, Price, Discounted_price
            FROM ref_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        # İlk satırdan customer_type ve ref_dsc değerlerini al
        customer_type = rows[0][0] if rows else ''
        ref_dsc = rows[0][1] if rows else 0.0

        # Seçimleri JSON formatında döndür
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
                'discounted_price': row[10]
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
                KG DECIMAL(10, 2) DEFAULT 0.0
            )
        ''')

        user_id = session.get('user_id', 0)
        sira = 3700

        for item in woods_data:
            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT, KG)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                item.get('sku', ''),
                item.get('item', ''),
                int(item.get('quantity', 0)),
                'WOOD',
                sira,
                float(item.get('price', 0)),
                float(item.get('dprice', 0)),
                int(item.get('quantity', 0)) * float(item.get('dprice', 0)),
                0, 0, 0
            ))
            sira += 1

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
    woods_discount = data.get('woods_discount', 0)
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
                Woods_discount REAL,
                PRIMARY KEY (Quote_number, Row_index)
            )
        ''')
        cursor.execute('DELETE FROM woods_selections WHERE Quote_number = ?', (quote_number,))
        for idx, sel in enumerate(selections):
            quantity = int(sel.get('quantity', 0) or 0)
            price = float(sel.get('price', 0) or 0)
            dprice = float(sel.get('dprice', 0) or 0)
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
        {'group': row[0], 'item': row[1], 'quantity': row[2], 'price': row[3], 'dprice': row[4], 'sku': row[5]}
        for row in rows
    ]
    customer_type = rows[0][6] if rows else 'Retail'
    woods_discount = rows[0][7] if rows else 0
    return jsonify({'status': 'success', 'selections': selections, 'customer_type': customer_type, 'woods_discount': woods_discount})


@app.route('/calculate_ceiling_qty', methods=['POST'])
def calculate_ceiling_qty():
    try:
        data = request.get_json()
        ceiling_m2 = float(data.get('ceilingM2', 0))
        trim_lm = float(data.get('trimLM', 0))
        ceil_dsc = float(data.get('ceil_dsc', 0))  # ceil_dsc değerini al

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

            if code == "CL_T1":
                qty = max(8, math.ceil((ceiling_m2 / 100 * 278) / 8) * 8)
            elif code == "CL_MR61":
                qty = math.ceil(ceiling_m2 / 100 * 25)
            elif code == "CL_CT062":
                qty = math.ceil(ceiling_m2 / 100 * 150)
            elif code == "CL_CT63":
                qty = math.ceil(ceiling_m2 / 100 * 150)
            elif code == "CL_AT44":
                qty = math.ceil(trim_lm / 3)
            elif code == "CL_W124":
                qty = max(1, math.ceil(ceiling_m2 / 100 * 1))
            elif code == "CL_AB122":
                qty = max(1, math.ceil(ceiling_m2 / 100 * 1))

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
                KG DECIMAL(10, 2) DEFAULT 0.0 -- Yeni kolon eklendi       
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
        # selections = data.get('selections', [])  # Selections is optional, default to an empty list

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
                ceiling_discount REAL
            )
        ''')

        # Eski kayıtları sil
        cursor.execute('DELETE FROM ceil_selections WHERE Quote_number = ?', (quote_number,))

        # Yeni seçimleri ekle
        cursor.execute('''
            INSERT INTO ceil_selections (Quote_number, ceiling_m2, trim_lm, ceiling_discount)
            VALUES (?, ?, ?, ?)
        ''', (quote_number, ceiling_m2, trim_lm, ceiling_discount))

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

        # Seçimleri al
        cursor.execute('''
            SELECT ceiling_m2, trim_lm, ceiling_discount
            FROM ceil_selections
            WHERE Quote_number = ?
        ''', (quote_number,))
        rows = cursor.fetchall()

        conn.close()

        if rows:
            ceiling_m2 = rows[0][0]
            trim_lm = rows[0][1]
            ceiling_discount = rows[0][2]
            return jsonify({
                'status': 'success',
                'ceiling_m2': ceiling_m2,
                'trim_lm': trim_lm,
                'ceiling_discount': ceiling_discount
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
        g_total = data.get('g_total')

        if not all([date, quote_number, customer_id, customer_name, postcode, description, s_i, g_total]):
            return jsonify({'status': 'error', 'message': 'Eksik parametreler.'}), 400

        # customer_id'yi 7 karakter olacak şekilde sıfırlarla doldur
        customer_id = str(customer_id).zfill(7)

        # Veritabanı adı oluştur
        db_name = f"{customer_id}{postcode}.db"
        db_path = os.path.join(BASE_DIR, 'customerhes', db_name)

        # Veritabanına bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Veriyi customer_data tablosuna ekle
        cursor.execute('''
            INSERT INTO customer_data (Date, Customername, Customerid, Quotenumber, Description, S_I, Amonth)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (date, customer_name, customer_id, quote_number, description, s_i, g_total))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': 'Veriler başarıyla kaydedildi.'})
    except Exception as e:
        print("Hata (sale_cust_det):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

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
        # print(f"Received item_id: {item_id}, qty: {qty}")

        if not Model or qty is None:
            return jsonify({'status': 'error', 'message': 'Invalid input data'}), 400

        conn = sqlite3.connect('refrigeration.db')  # refrigeration veritabanına bağlan
        cursor = conn.cursor()

        cursor.execute("UPDATE refrigeration SET Qty = Qty - ? WHERE Model = ?", (qty, Model))
        conn.commit()

        if cursor.rowcount == 0:
            return jsonify({'status': 'error', 'message': 'Item not found or quantity not updated'}), 404

        return jsonify({'status': 'success', 'message': 'Quantity updated successfully'})
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
    # recipient_email = data.get('easyfatal12@gmail.com')  # Alıcı e-posta adresi
    # recipient_email = 'volkanballi@gmail.com'
    recipient_email = 'volkanballi@gmail.com' # , 'mehmet@easyshelf.co.uk'

    if not quote_number or not recipient_email:
        return jsonify({'status': 'error', 'message': 'Quote number and recipient email are required.'}), 400

    try:
        # Veritabanı yolları
        db_path = os.path.join(QUOTE_DB_PATH, f"{quote_number}.db")
        delivery_db_path = os.path.join(BASE_DIR, "prf_adr_dlvr.db")

        # Veritabanı dosyalarının varlığını kontrol et
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
        total_amount = sum(row[3] for row in rows)
        vat = round(total_amount * 0.20, 2)
        grand_total = round(total_amount + vat, 2)

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

           # Invoice numarasını oluştur
        user_id = str(session.get('user_id', '00')).zfill(2)  # User ID'yi 2 haneli yap
        user_name = session.get('user', 'Unknown User')  # Kullanıcı adını oturumdan al
        dd_mm_yy = datetime.now().strftime('%d%m%y')  # Tarihten mmYY formatını al
        prefix = f"{user_id}{dd_mm_yy}"  # Başlangıç 6 hane/8 hane

        # Invoice klasöründeki mevcut dosyaları kontrol et
        folder = 'invoice'
        os.makedirs(folder, exist_ok=True)
        existing_files = [f for f in os.listdir(folder) if f.startswith(prefix)]
        if existing_files:
            # Son 5 hanesi en büyük olanı bul
            max_suffix = max(int(f[len(prefix):-4]) for f in existing_files if f[len(prefix):-4].isdigit())
            new_suffix = str(max_suffix + 1).zfill(5)  # 1 artır ve 5 haneli yap
        else:
            new_suffix = "00001"  # İlk dosya için başlangıç

        invoice_num = f"{prefix}{new_suffix}"  # Tam invoice numarası

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
        if (color_row):
            color_labels = ['Shelf', 'Ticket', 'Type', 'Slatwall', 'Insert', 'Endcap']
            for label, value in zip(color_labels, color_row):
                pdf.set_font('Helvetica', '', 7)
                pdf.cell(0, 3, f"{label}: {value or 'N/A'}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.cell(0, 4, "Color selections: Not found", new_x=XPos.LMARGIN, new_y=YPos.NEXT)

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

        # E-posta gönderme
        sender_email = "easyfatgon@gmail.com"  # Gönderen e-posta adresi
        sender_password = "jqsq mkvn zdvm jqzr"  # Gönderen e-posta şifresi

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

        # Veritabanı yolunu oluştur
        db_path = os.path.join('quotes', f"{quote_number}.db")

        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{quote_number}.db bulunamadı.'}), 404

        # Veritabanına bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # SIRA kolonundaki başlangıç numaralarına göre DEPO sütununu topla
        cursor.execute('''
        SELECT 
            CAST(SIRA AS INTEGER) / 100 * 100 AS vercode, 
            SUM(DEPO)
        FROM list
        GROUP BY vercode
        ORDER BY vercode
        ''')
        rows = cursor.fetchall()
        conn.close()

        # Sonucu formatla ve toplamları aşağı yuvarla
        result = '-'.join([f"{row[0]}/{int(row[1])}" for row in rows])

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
        return jsonify({'status': 'success', 'kg_total': int(kg_total)})
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
        conn = sqlite3.connect(db_path)  # Dosya yoksa oluşturur
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
                KG DECIMAL(10, 2) DEFAULT 0.0 -- Yeni kolon eklendi           
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
                        SELECT id, local FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price = prc_row if prc_row else (None, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price))

            elif "Fruit" in item_name:
                counter_cursor.execute('''
                    SELECT item_name, qty 
                    FROM counter_parca
                    WHERE LOWER(REPLACE(group_name, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                counter_rows = counter_cursor.fetchall()

                for counter_item_name, counter_qty in counter_rows:
                    print(f"Counter Item Name: {counter_item_name} | Item Name: {item_name}")  # <<< BURAYA EKLENDİ

                    sira = int(1500 + int(row_index))
                    prc_cursor.execute('''
                        SELECT id, local FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price = prc_row if prc_row else (None, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price))

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
                        SELECT id, local FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                    ''', (counter_item_name,))
                    prc_row = prc_cursor.fetchone()
                    item_id, price = prc_row if prc_row else (None, 0.0)

                    if item_id is None:
                        item_id = 0

                    cursor.execute('''
                        INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
                    ''', (user_id, item_id, counter_item_name, counter_qty * quantity, item_name, sira, price))
            else:
                prc_cursor.execute('''
                    SELECT id, local FROM prc_tbl WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
                ''', (item_name,))
                prc_row = prc_cursor.fetchone()
                item_id, price = prc_row if prc_row else (None, 0.0)

                if item_id is None:
                    item_id = 0

                if any(x in item_name for x in ["Side", "side", "Drop", "drop", "Slat", "slat"]):
                    sira = int(3500 + int(row_index))
                    grpname = item_name
                else:
                    sira = int(4000 + int(row_index))
                    grpname = 'UNITE_SECOND_PART'

                cursor.execute('''
                    INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
                ''', (user_id, item_id, item_name, quantity, grpname, sira, price))

            processed_items.append({'item_name': item_name})




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

            while i < len(items):
                item = items[i]
                name = item['item_name']
                prefix = extract_prefix(name)

                # Worktop Standard grubu

                if prefix in ["Counter STANDARD", "Counter HIGH", "Counter High","Counter Standard"]:
                    ws = 0
                    group_prefix = prefix  # İlk prefix'i sakla

                    while i < len(items):
                        current_prefix = extract_prefix(items[i]['item_name'])
                        if current_prefix not in ["Counter STANDARD", "Counter HIGH", "Counter High","Counter Standard"]:
                            break
                        val = extract_numeric_value(items[i]['item_name'])
                        ws += val * 10
                        i += 1

                    ws += 30

                    # "Counter High" için özel adlandırma
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
                    
                    while i < len(items):
                        current_prefix = extract_prefix(items[i]['item_name'])
                        if current_prefix not in ["Counter S. LOW", "Counter H. LOW"]:
                            break
                        val = extract_numeric_value(items[i]['item_name'])
                        if val == 66:
                            wl += val * 10 + 5
                        else:
                            wl += val * 10
                        i += 1

                    # Önceki kontrol
                    before = extract_prefix(items[start_index - 1]['item_name']) if start_index > 0 else None
                    if before in ["Counter STANDARD", "Counter HIGH", "Counter High", "Counter Standard"]:
                        wl -= 35
                    else:
                        wl += 15

                    # Sonraki kontrol
                    after = extract_prefix(items[i]['item_name']) if i < len(items) else None
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
            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
                VALUES (?, 99999, ?, 1, 'WORKTOP', 2500, ?, 0, 0, 0, ?)
            ''', (user_id, f'{name} {value}', value*0.17, value*0.04))

        conn.commit()
        conn.close()
        prc_conn.close()
        counter_conn.close()

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

if __name__ == '__main__':
    app.run(debug=True)