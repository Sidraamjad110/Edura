import pyodbc

server = '192.168.18.14'
database = 'medipro'
username = 'rasant_dev'
password = 'Xy!0pMn#nO'
driver = 'ODBC Driver 17 for SQL Server'

print(f"Testing with driver: {driver}")
print(f"Server: {server}")
print(f"Database: {database}")

try:
    conn = pyodbc.connect(
        f'DRIVER={{{driver}}};'
        f'SERVER={server};'
        f'DATABASE={database};'
        f'UID={username};'
        f'PWD={password};'
        f'TrustServerCertificate=yes;'
    )
    print("✓ Connection successful!")
    
    cursor = conn.cursor()
    cursor.execute("SELECT @@VERSION")
    row = cursor.fetchone()
    print(f"SQL Server Version: {row[0]}")
    
    cursor.execute("SELECT DB_NAME()")
    row = cursor.fetchone()
    print(f"Connected to database: {row[0]}")
    
    conn.close()
except Exception as e:
    print(f"✗ Connection failed: {e}")
    
    # Try without TrustServerCertificate
    try:
        print("\nTrying without TrustServerCertificate...")
        conn = pyodbc.connect(
            f'DRIVER={{{driver}}};'
            f'SERVER={server};'
            f'DATABASE={database};'
            f'UID={username};'
            f'PWD={password};'
        )
        print("✓ Connection successful without TrustServerCertificate!")
        conn.close()
    except Exception as e2:
        print(f"✗ Also failed: {e2}")
