import sqlite3
from werkzeug.security import generate_password_hash

def create_user_table():
    conn = sqlite3.connect('users.db')  # Veritabanı dosyasını aç veya oluştur
    cursor = conn.cursor()

    # Kullanıcılar için bir tablo oluşturma
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    # Örnek bir kullanıcı ekleme (şifre hash'lenmeli)
    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', 
                   ('admin', generate_password_hash('password')))

    conn.commit()  # Değişiklikleri kaydet
    conn.close()   # Bağlantıyı kapat

create_user_table()  # Bu fonksiyonu çalıştır
