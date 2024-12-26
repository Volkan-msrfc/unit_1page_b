import sqlite3
from werkzeug.security import generate_password_hash

def add_user(username, name, surname, password):
    conn = sqlite3.connect('users.db')  # Veritabanını bağla
    cursor = conn.cursor()

    # Kullanıcıyı ekleme (şifre hash'leniyor)
    cursor.execute('INSERT INTO users (username, name, surname, password) VALUES (?, ?, ?, ?)', 
                   (username, name, surname, generate_password_hash(password)))

    conn.commit()  # Değişiklikleri kaydet
    conn.close()   # Bağlantıyı kapat

# 'volkan' kullanıcısını ekle
add_user('volkan', 'Volkan', 'Balli', 'Volkan12345')