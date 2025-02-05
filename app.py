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
import queue
import threading
import time


app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# quotes dizinine giden yolu ayarlayın
QUOTE_DB_PATH = os.path.join(BASE_DIR, 'quotes')

app.secret_key = 'colacola998346'  # Güvenli bir anahtar belirleyin

# Kullanıcı sırası için bir FIFO kuyruğu
user_queue = queue.Queue()
processing_user = None  # Şu an işlem yapan kullanıcıyı tutar
lock = threading.Lock()  # İşlem sırasında veri bütünlüğünü korumak için

def process_next_user():
    global processing_user
    
    while True:
        user_id = user_queue.get()  # Sıradaki kullanıcıyı al (bloklamalı)

        with lock:
            processing_user = user_id  # İşlenen kullanıcıyı güncelle

        print(f"Processing user: {processing_user}")
        time.sleep(5)  # Gerçek işlem burada olacak (simülasyon)
        print(f"User {processing_user} finished processing.")

        with lock:
            processing_user = None  # İşlem tamamlandı

        user_queue.task_done()  # Kuyrukta işin tamamlandığını bildir

@app.route('/enqueue', methods=['POST'])
def enqueue_user():
    global processing_user

    if 'user_id' not in session:
        return jsonify({'error': 'Oturum açılmamış'}), 401

    user_id = session['user_id']

    with lock:
        if user_id in list(user_queue.queue):  # Kullanıcı zaten sıradaysa tekrar ekleme
            return jsonify({'message': 'Zaten sıradasınız.'})

        user_queue.put(user_id)  # Kullanıcıyı sıraya ekle

        # Eğer şu anda işlem yapan biri yoksa, işlem başlat
        if processing_user is None:
            threading.Thread(target=process_next_user, daemon=True).start()

    return jsonify({'message': 'Sıraya eklendiniz.', 'queue_position': user_queue.qsize()})


@app.route('/queue_status', methods=['GET'])
def queue_status():
    return jsonify({
        'current_processing': processing_user,
        'queue': list(user_queue.queue)
    })



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
    session.pop('user', None)  # Kullanıcıyı oturumdan çıkar
    return redirect(url_for('login'))  # Login sayfasına yönlendir

@app.route('/proforma', methods=['GET', 'POST'])
def proforma():
    return render_template('proforma.html')  # proforma.html şablonunu döner

@app.route('/update_width', methods=['POST'])
def update_width():
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

            cursor.execute('''
            UPDATE wall_parca
            SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 22
            ''', (unit_piece, unit_type, row_index))

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

            cursor.execute('''
            UPDATE wall_parca
            SET ADET = ?, UNIT_TYPE = ?, SIRA = ?
            WHERE rowid = 22
            ''', (unit_piece, unit_type, row_index))

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
            ''', (base_shelf, unit_piece * 2, unit_type, row_index))   

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
    
def create_quote_list(clean_string):
    try:
        # Hedef dizin
        os.makedirs(QUOTE_DB_PATH, exist_ok=True)
        new_file_name = f"{clean_string}.db"
        new_db_path = os.path.join(QUOTE_DB_PATH, new_file_name)
        # Yeni veritabanının tam yolu
        #new_db_path = os.path.join(target_dir, new_file_name)

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
                AMOUNTH DECIMAL(10, 2)
            )
        ''')

        # wall.db'den verileri al ve filtrele (ADET > 0)
        cursor.execute('''
            SELECT ITEM_NAME, ADET, UNIT_TYPE, SIRA
            FROM wall_parca
            WHERE ADET > 0
        ''')
        rows = cursor.fetchall()

        # quote_list tablosuna ekle
        cursor_quote.executemany('''
            INSERT INTO list (USER_ID, ITEM_ID, ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE, AMOUNTH)
            VALUES (0, 0, ?, ?, ?, ?, 0.00, 0.00, 0.00)
        ''', rows)

        # Değişiklikleri kaydet ve bağlantıyı kapat
        conn_quote.commit()
        conn_quote.close()
        conn.close()

        print(f"Quote list database created successfully aloo: {new_db_path}")

    except sqlite3.Error as e:
        print("Veritabanı hatası (create_quote_list):", str(e))


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




@app.route('/get_quote_list', methods=['GET'])
def get_quote_list():
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

        # Veriyi JSON formatında döndür
        return jsonify({'db_name': db_name, 'data': rows})

    except sqlite3.Error as e:
        print("Veritabanı hatası:", str(e))
        return jsonify({'message': f'Hata: {str(e)}'}), 500
    except Exception as e:
        print("Beklenmeyen hata:", str(e))
        return jsonify({'message': f'Beklenmeyen hata: {str(e)}'}), 500


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
                INSERT INTO list (ITEM_NAME, ADET, UNIT_TYPE, SIRA, PRICE, DSPRICE)
                VALUES (?, ?, 'ADD_ITEM', ?, ?, ?)
            ''', (item_name, qty, sr, price, dsprice))

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
        files = [f for f in os.listdir(quotes_dir) if f.endswith('.db')]  # .db dosyalarını seç
        return jsonify(files)  # Dosya listesini döndür
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
