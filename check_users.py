import sqlite3

def check_users():
    conn = sqlite3.connect('users.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM users')
    users = cursor.fetchall()

    for user in users:
        print(user)

    conn.close()

check_users()