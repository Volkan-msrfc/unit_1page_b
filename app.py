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

app = Flask(__name__)

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

        # Kullanıcı doğrulama
        conn = sqlite3.connect('users.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, password FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[1], password):  # Şifre doğrulaması
            session['user'] = username  # Kullanıcıyı oturuma kaydet
            session['user_id'] = user[0]  # **Gerçek ID'yi kaydet (1 veya 2 gibi)**
            return redirect(url_for('menu'))  # Giriş başarılıysa menuye yönlendir
        else:
            error = "Kullanıcı adı veya şifre yanlış."  # Hata mesajı
            return render_template('login.html', error=error)

    return render_template('login.html')  # GET isteğinde login sayfasını göster

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
    session.pop('user', None)  # Kullanıcıyı oturumdan çıkar
    return redirect(url_for('login'))  # Login sayfasına yönlendir

@app.route('/proforma', methods=['GET', 'POST'])
def proforma():
    return render_template('proforma.html')  # proforma.html şablonunu döner

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

        # Değişiklikleri geçici olarak kaydet
        conn.commit()

        # Gelen verileri al
        data = request.get_json()

        # Her bir alanı al, boş stringse varsayılan değeri kullan, ondalıklı değerleri tamsayıya dönüştür
        
        row_index = int(float(data.get('row_index', 0) or 0)) 
        row_index = f"1.{row_index}"  # İstenilen formata dönüştür
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
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 1
            ''', (width, base_shelf, unit_piece, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, qty * unit_piece, unit_type, row_index))
             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, qty_option8 * unit_piece, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, qty_option10 * unit_piece, unit_type, row_index))

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
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + 1)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece, unit_type, row_index))        


            # 12. satırdaki Pilinth için width güncellemesi
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, unit_piece, unit_type, row_index))

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
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece, unit_type, row_index))

            cursor.execute('''
            UPDATE wall_parca
            SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 22
            ''', (unit_piece, unit_type, row_index))

        elif unit_type == "Double Gondola":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 1
            ''', (width, base_shelf , unit_piece * 2, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, qty * unit_piece, unit_type, row_index))
             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, qty_option8 * unit_piece, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, qty_option10 * unit_piece, unit_type, row_index))

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
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + 1)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece *2 , unit_type, row_index))        


            # 12. satırdaki Pilinth için width güncellemesi
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, unit_piece, unit_type, row_index))

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
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece * 2, unit_type, row_index))    


        elif unit_type == "Single Gondola":

            # 2. İlk "Metallic Shelf" için Width, Depth ve Adet güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 1
            ''', (width, base_shelf, unit_piece, unit_type, row_index))

            # 4. İkinci "Metallic Shelf" için Width, Depth (Shelf Size) ve Adet güncellemeleri
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 2
            ''', (width, shelf_size, qty * unit_piece, unit_type, row_index))
             # 4. satırdaki Metallic Shelf için width, shelf_size_option9 ve qty_option8 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 3
            ''', (width, shelf_size_option9, qty_option8 * unit_piece, unit_type, row_index))

            # 5. satırdaki Metallic Shelf için width, shelf_size_option11 ve qty_option10 * unit_piece
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, DEPTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 4
            ''', (width, shelf_size_option11, qty_option10 * unit_piece, unit_type, row_index))

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
            cursor.execute('''
            UPDATE wall_parca
            SET width = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Price Holder '
            ''', (width, (unit_piece * (qty + qty_option8 + qty_option10 + 1)), unit_type, row_index))

            # 1. "Upright Post 30*60*" için height ve adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET height = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Upright Post 30*60*'
            ''', (height, unit_piece, unit_type, row_index))

            # 3. "Baseleg" için Depth ve Adet güncelleme
            cursor.execute('''
            UPDATE wall_parca
            SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece, unit_type, row_index))        


            # 12. satırdaki Pilinth için width güncellemesi
            cursor.execute('''
            UPDATE wall_parca
            SET WIDTH = ?, ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 11
            ''', (width, unit_piece, unit_type, row_index))

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
            cursor.execute('''
                UPDATE wall_parca
                SET depth = ?, adet = ?, UNIT_TYPE = ?, SIRA = ?
                WHERE UNIT_ITEMS = 'Baseleg '
            ''', (base_shelf, unit_piece , unit_type, row_index))   

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
                IMPORT DECIMAL(10, 2) -- Yeni kolon eklendi
            )
        ''')

        # wall.db'den verileri al ve filtrele (ADET > 0)
        cursor.execute('''
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM wall_parca
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
                SELECT id, local, import
                FROM prc_tbl
                WHERE LOWER(REPLACE(name1, ' ', '')) = LOWER(REPLACE(?, ' ', ''))
            ''', (item_name,))
            prc_row = cursor_prc.fetchone()

            if prc_row:
                item_id, local_price, import_price = prc_row
            else:
                item_id, local_price, import_price = 0, 0.0, 0.0  # Eşleşme yoksa varsayılan değerler

            # local_price = round(local_price, 2)  # Ensure 2 decimal places
            local_price = float(f"{local_price:.2f}")
            rows_with_user_id.append((user_id, item_id, item_name, adet, unit_type, sira, local_price, 0.00, 0.00, 0.00, import_price))

        # list tablosuna ekle
        cursor_quote.executemany('''
            INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH, DEPO, IMPORT)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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

        # Veritabanına bağlan
        if not os.path.exists(db_path):
            return jsonify({'status': 'error', 'message': f'{quote_number} veritabanı bulunamadı.'}), 404

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # `list` tablosundaki verileri al
        cursor.execute('SELECT PRICE, ADET, SIRA, DSPRICE FROM list')
        rows = cursor.fetchall()

        updated_rows = []
        for row in rows:
            price, adet, sira, dsprice = row
            price = price or 0
            adet = adet or 0

            # Sıra numarası 1 ile başlıyorsa indirim uygula
            if str(sira).startswith('1'):
                new_dsprice = round(price * (1 - dsc / 100), 2)
            else:
                new_dsprice = dsprice  # İndirim uygulanmaz

            amounth = round(adet * new_dsprice, 2)

            # Değiştirilen değerleri yazdır
            # print(f"SIRA: {sira}, PRICE: {price}, ADET: {adet}, DSPRICE: {new_dsprice}, AMOUNTH: {amounth}")

            updated_rows.append((new_dsprice, amounth, price, adet, sira))

        cursor.executemany('''
            UPDATE list
            SET DSPRICE = ?, AMOUNTH = ?
            WHERE PRICE = ? AND ADET = ? AND SIRA = ?
        ''', updated_rows)

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'message': f'{quote_number} için indirim uygulandı.'})
    except sqlite3.Error as e:
        print("Veritabanı hatası (apply_discount):", str(e))
        return jsonify({'status': 'error', 'message': f'Veritabanı hatası: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata (apply_discount):", str(e))
        return jsonify({'status': 'error', 'message': f'Beklenmeyen hata: {str(e)}'}), 500


@app.route('/prep_up_qt', methods=['POST'])
def call_prep_up_qt():
    try:
        # Frontend'den gelen JSON verisini al
        data = request.get_json()
        quote_number = data.get('quote_number')
        dsc = data.get('dsc', 0)
        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # prep_up_qt fonksiyonunu çağır
        # print(f"dsc değeri1: {dsc}")  # dsc değerini konsola yazdır
        prep_up_qt(quote_number,dsc)

        return jsonify({'status': 'success', 'message': f'{quote_number} için prep_up_qt çağrıldı.'})
    except Exception as e:
        print(f"prep_up_qt endpoint hatası: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def prep_up_qt(clean_string,dsc):
    try:
        # Kullanıcı ve müşteri bilgilerini oturumdan al
        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        user_name = session.get('user', 'Unknown User')  # Kullanıcı adını oturumdan al
        customer_id = session.get('customer_id', 0)  # Eğer oturumda customer_id yoksa varsayılan olarak 0 kullanılır
        customer_name = session.get('customer_name', 'Unknown Customer')  # Müşteri adını oturumdan al
        # Proforma sayfasındaki dsc değerini al

        # `update_quotes_db` fonksiyonunu çağır
        update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc)

        print(f"prep_up_qt: {clean_string} için update_quotes_db çağrıldı.")
    except Exception as e:
        print(f"prep_up_qt sırasında hata oluştu: {str(e)}")

def update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name, dsc):
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
                Customer_id INTEGER,         -- Müşteri ID'si
                Customer_name TEXT,          -- Müşteri adı
                Discount DECIMAL(10, 2),     -- İndirim oranı
                Amount DECIMAL(10, 2) NOT NULL, -- Toplam tutar
                Sold TEXT,                    -- Satış durumu (1 harf)
                Inv TEXT,                    -- Fatura durumu (1 harf)
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- Kayıt tarihi ve saati
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
        current_time1 = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # `Quote_number` zaten var mı kontrol et
        cursor_quotes.execute('SELECT COUNT(*) FROM quotes WHERE Quote_number = ?', (clean_string,))
        quote_exists = cursor_quotes.fetchone()[0] > 0

        if quote_exists:
            # Eğer `Quote_number` zaten varsa, satırı güncelle
            cursor_quotes.execute('''
                UPDATE quotes
                SET User_id = ?, User_name = ?, Customer_id = ?, Customer_name = ?, Discount = ?, Amount = ?, Sold = ?, Inv = ?, created_at = ?
                WHERE Quote_number = ?
            ''', (user_id, user_name, customer_id, customer_name, dsc, total_amount, '', '', current_time1, clean_string))
            print(f"Quotes database updated for existing Quote_number: {clean_string}")
        else:
            # Eğer `Quote_number` yoksa, yeni bir satır ekle
            cursor_quotes.execute('''
                INSERT INTO quotes (Quote_number, User_id, User_name, Customer_id, Customer_name, Discount, Amount, Sold, Inv, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (clean_string, user_id, user_name, customer_id, customer_name, dsc, total_amount, '', '', current_time1))
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

        # quotes tablosundaki tüm verileri al
        cursor.execute('SELECT * FROM quotes')
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
    islmdvm = 1  # update_width fonksiyonu başladığında değeri 1 yap
    try:
        # Frontend'den gelen db_name parametresini al
        db_name = request.args.get('db_name')  # db_name parametresi URL'den alınacak
        if not db_name:
            return jsonify({'message': 'Veritabanı adı sağlanmadı.'}), 400

        # .dp uzantısını kaldır ve .db dosyasını bul
        if not db_name.endswith('.db'):
            db_file = db_name + '.db'
        else:
            db_file = db_name
        db_path = os.path.join(QUOTE_DB_PATH, db_file)

        # Dosyanın var olup olmadığını kontrol et
        if not os.path.exists(db_path):
            return jsonify({'message': f'{db_file} dosyası bulunamadı.'}), 404

        # Dosyaya bağlan
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # list tablosundaki verileri çek
        cursor.execute('SELECT USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH FROM list ORDER BY CAST(SIRA AS DECIMAL(10, 2)) ASC')
        rows = cursor.fetchall()

        # Bağlantıyı kapat
        conn.close()

        # Kullanıcı ve müşteri bilgilerini oturumdan al
        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        user_name = session.get('user', 'Unknown User')  # Kullanıcı adını oturumdan al
        customer_id = session.get('customer_id', 0)  # Eğer oturumda customer_id yoksa varsayılan olarak 0 kullanılır
        customer_name = session.get('customer_name', 'Unknown Customer')  # Müşteri adını oturumdan al

        # `update_quotes_db` fonksiyonunu çağır
        # update_quotes_db(db_name.replace('.db', ''), user_id, user_name, customer_id, customer_name)

        # Veriyi JSON formatında döndür
        return jsonify({'db_name': db_name, 'data': rows})

    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({'message': f'Hata: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata:", str(e))
        return jsonify({'message': f'Beklenmeyen hata: {str(e)}'}), 500
    finally:
        islmdvm = 0  # get_quote_list işlemi bittiğinde değeri tekrar 0 yap


@app.route('/add_item_data', methods=['POST'])
def add_item_data():
    try:
        data = request.get_json()
        add_item_data = data.get('add_item_data', [])
        largest_file = str(data.get('largest_file', '') or '').replace("Quotation Number: ", "").strip()

        # Eğer veri gelmemişse hata döndür
        if not add_item_data:
            return jsonify({"status": "error", "message": "Hiçbir veri alınmadı."}), 400

        # Hedef dizin ve veritabanı adı
        #target_dir = r"/home/render/quotes"
        #os.makedirs(target_dir, exist_ok=True)
        #new_db_path = os.path.join(target_dir, f"{largest_file}.db")
        
        # Hedef veritabanı dosyası
        new_db_path = os.path.join(QUOTE_DB_PATH, f"{largest_file}.db")
        sr = 4.0

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
                AMOUNTH DECIMAL(10, 2)
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır

        # USER_ID'yi ekleyerek verileri düzenle
        #rows_with_user_id = [(user_id, *row) for row in rows]

        # Gelen verileri işleyip tabloya ekle
        for item in add_item_data:
            item_name = item.get('itemName', '').strip()
            sr = round(sr + 0.1, 1)  # SR'yi 0.1 artır ve ondalık hassasiyetini koru
            qty = int(item.get('qty', 0))  # Sayısal değer olarak kaydet
            price = float(item.get('price', 0))  # Sayısal değer olarak kaydet
            dsprice = float(item.get('dsprice', 0))  # Sayısal değer olarak kaydet

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
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH)
                VALUES (?, 0, ?, ?, 'ADD_ITEM', ?, ?, ?, ?)                 


            ''', (user_id, item_name, qty, sr, price, dsprice, qty*dsprice))      #, price, dsprice))

         

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn_quote.commit()
        conn_quote.close()

        return jsonify({"status": "success", "message": "Veri başarıyla kaydedildi!"})
    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({"status": "error", "message": f"Veritabanı hatası: {str(e)}"}), 500
    except Exception as e:
        print("Beklenmeyen hata:", str(e))
        return jsonify({"status": "error", "message": f"Beklenmeyen hata: {str(e)}"}), 500

@app.route("/fetch_customers", methods=["GET"])
def fetch_customers():
    connection = sqlite3.connect("customers.db")
    cursor = connection.cursor()
    cursor.execute("SELECT id, customer_name, tel, address, postcode FROM customers")
    customers = cursor.fetchall()
    connection.close()
    return jsonify(customers)

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
            ''', (quote_number, row_index, json.dumps(selection)))

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
        customer_id = str(customer_id_row[0]).zfill(7)

        # customers.db veritabanına bağlan
        customers_db_path = os.path.join(BASE_DIR, "customers.db")
        conn_customers = sqlite3.connect(customers_db_path)
        cursor_customers = conn_customers.cursor()

        # Customer ID'ye göre müşteri bilgilerini al
        cursor_customers.execute('''
            SELECT id, customer_name, tel, address, postcode
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
            'address': customer[3],
            'postcode': customer[4]
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
                AMOUNTH DECIMAL(10, 2)
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        sira = 2.1  # Sıra değeri başlangıç

        # Gelen verileri işleyip tabloya ekle
        for item in ref_data:
            cursor_quote.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                item.get('sku', ''),
                item.get('itemName', ''),
                item.get('quantity', 0),
                item.get('unitType', 'Add Refrigeration'),
                round(sira, 2),  # Sıra değeri
                item.get('price', 0.0),
                item.get('dprice', 0.0),
                item.get('quantity', 0) * item.get('dprice', 0.0)  # AMOUNTH hesaplama
            ))
            sira += 0.1  # Sıra değerini artır

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
                AMOUNTH DECIMAL(10, 2)
            )
        ''')

        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        # print("Tablo oluşturuldu veya zaten mevcut.")

        # Ceiling verilerini işleyip veritabanına ekle
        for index, row in enumerate(ceiling_data, start=1):
            item_id = row.get('Code', '')
            item_name = row.get('Materials', '')
            adet = row.get('qty', 0)
            unit_type = "Ceiling"
            sira = f"3.{index}"
            price = row.get('local', 0)
            dsprice = row.get('dPrice', 0)
            amounth = adet * dsprice

            # print(f"Veri ekleniyor: {user_id}, {item_id}, {item_name}, {adet}, {unit_type}, {sira}, {price}, {dsprice}, {amounth}")
            cursor.execute('''
                INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (user_id, item_id, item_name, adet, unit_type, sira, price, dsprice, amounth))

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn.commit()
        conn.close()
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



        # Seçimleri JSON formatında döndür
        # selections = [
        #     {
		#         'ceiling_m2': row[0],
        #         'trim_lm': row[1],
        #         'ceiling_discount': row[2]

        #     }
        #     for row in rows
        # ]
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
        customer_id = data.get('id')  # Eğer müşteri ID'si varsa güncelleme yapılacak
        # print(f"Gelen müşteri ID'si: {customer_id}")  # Gelen müşteri ID'sini yazdır
        customer_name = data.get('name')
        tel = data.get('tel')
        address1 = data.get('address1')
        address2 = data.get('address2')
        postcode = data.get('postcode')
        email = data.get('email')
        discount = data.get('discount')

        if not customer_name or not tel:
            return jsonify({'status': 'error', 'message': 'Müşteri adı ve telefon numarası zorunludur.'}), 400

        conn = sqlite3.connect('customers.db')
        cursor = conn.cursor()

        if customer_id:
            # Güncelleme işlemi
            cursor.execute('''
                UPDATE customers
                SET customer_name = ?, tel = ?, address = ?, address2 = ?, postcode = ?, email = ?, discount = ?
                WHERE id = ?
            ''', (customer_name, tel, address1, address2, postcode, email, discount, customer_id))
        else:
            # Yeni müşteri ekleme işlemi
            cursor.execute('SELECT MAX(CAST(id AS INTEGER)) FROM customers')  # Listedeki son kaydın ID'sini al
            last_id = cursor.fetchone()[0] or 0  # Eğer tablo boşsa 0 kullan
            new_id = str(last_id + 1).zfill(7)  # Yeni ID'yi oluştur ve 7 karaktere sıfırlarla doldur
            cursor.execute('''
                INSERT INTO customers (id, customer_name, tel, address, address2, postcode, email, discount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (new_id, customer_name, tel, address1, address2, postcode, email, discount))

            # Yeni müşteri için veritabanı oluştur
            customerhes_path = os.path.join(BASE_DIR, 'customerhes')  # customerhes klasörünün yolu
            os.makedirs(customerhes_path, exist_ok=True)  # Klasörü oluştur (eğer yoksa)
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
        print("Hata (add_or_update_customer):", str(e))
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
