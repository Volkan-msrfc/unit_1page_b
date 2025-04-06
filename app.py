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
            rows_with_user_id.append((user_id, item_id, item_name, adet, unit_type, sira, local_price, 1.00, 1.00, 1.00, 1.00))

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
        cursor.execute('SELECT ITEM_NAME, PRICE, ADET FROM list')
        rows = cursor.fetchall()

        # Her satır için `DSPRICE` ve `AMOUNTH` hesapla
        updated_rows = []
        for row in rows:
            item_name, price, adet = row
            price = price or 0  # Eğer `PRICE` None ise 0 olarak ele al
            adet = adet or 0    # Eğer `ADET` None ise 0 olarak ele al

            # DSPRICE ve AMOUNTH hesaplaması
            dsprice = round(price * (1 - dsc / 100), 2)
            amounth = round(adet * dsprice, 2)

            updated_rows.append((dsprice, amounth, item_name))

        # Güncellenmiş değerleri veritabanına yaz
        cursor.executemany('''
            UPDATE list
            SET DSPRICE = ?, AMOUNTH = ?
            WHERE ITEM_NAME = ?
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

        if not quote_number:
            return jsonify({'status': 'error', 'message': 'Eksik parametre: quote_number'}), 400

        # prep_up_qt fonksiyonunu çağır
        prep_up_qt(quote_number)

        return jsonify({'status': 'success', 'message': f'{quote_number} için prep_up_qt çağrıldı.'})
    except Exception as e:
        print(f"prep_up_qt endpoint hatası: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

def prep_up_qt(clean_string):
    try:
        # Kullanıcı ve müşteri bilgilerini oturumdan al
        user_id = session.get('user_id', 0)  # Eğer oturumda user_id yoksa varsayılan olarak 0 kullanılır
        user_name = session.get('user', 'Unknown User')  # Kullanıcı adını oturumdan al
        customer_id = session.get('customer_id', 0)  # Eğer oturumda customer_id yoksa varsayılan olarak 0 kullanılır
        customer_name = session.get('customer_name', 'Unknown Customer')  # Müşteri adını oturumdan al

        # `update_quotes_db` fonksiyonunu çağır
        update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name)

        print(f"prep_up_qt: {clean_string} için update_quotes_db çağrıldı.")
    except Exception as e:
        print(f"prep_up_qt sırasında hata oluştu: {str(e)}")

def update_quotes_db(clean_string, user_id, user_name, customer_id, customer_name):
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
                Amount DECIMAL(10, 2) NOT NULL, -- Toplam tutar
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
                SET User_id = ?, User_name = ?, Customer_id = ?, Customer_name = ?, Amount = ?, created_at = ?
                WHERE Quote_number = ?
            ''', (user_id, user_name, customer_id, customer_name, total_amount, current_time1, clean_string))
            print(f"Quotes database updated for existing Quote_number: {clean_string}")
        else:
            # Eğer `Quote_number` yoksa, yeni bir satır ekle
            cursor_quotes.execute('''
                INSERT INTO quotes (Quote_number, User_id, User_name, Customer_id, Customer_name, Amount, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (clean_string, user_id, user_name, customer_id, customer_name, total_amount, current_time1))
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

        print(f"db_name: {db_name}")  # db_name'i konsola yazdır

        print(f"data: {rows}")  # data'yı (rows) konsola yazdır

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
        print("GET_quote bitti:")
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


if __name__ == '__main__':
    app.run(debug=True)
