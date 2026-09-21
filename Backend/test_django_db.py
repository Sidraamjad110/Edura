import os
import sys

# Set up Django environment
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'EduraAPI.settings')

try:
    import django
    django.setup()
    print("? Django setup complete")
except Exception as e:
    print(f"? Django setup failed: {e}")
    sys.exit(1)

from django.db import connection

print("\nTesting Django database connection...")
print("=" * 50)

try:
    # Test 1: Check connection settings
    print("\n1. Database settings:")
    settings = connection.settings_dict
    print(f"   ENGINE: {settings.get('ENGINE')}")
    print(f"   NAME: {settings.get('NAME')}")
    print(f"   HOST: {settings.get('HOST')}")
    print(f"   PORT: {settings.get('PORT')}")
    print(f"   USER: {settings.get('USER')}")
    print(f"   OPTIONS: {settings.get('OPTIONS', {})}")
    
    # Test 2: Try to connect
    print("\n2. Testing connection...")
    connection.ensure_connection()
    print("   ? Connection.ensure_connection() successful")
    
    # Test 3: Execute a query
    print("\n3. Executing test query...")
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 as test, DB_NAME() as db, @@VERSION as version")
        row = cursor.fetchone()
        print(f"   ? Query executed successfully")
        print(f"   Test result: {row[0]}")
        print(f"   Database: {row[1]}")
        print(f"   Version: {row[2][:50]}...")
    
    print("\n" + "=" * 50)
    print("? All tests passed! Django can connect to the database.")
    
except Exception as e:
    print(f"\n? Error: {e}")
    
    # Show more details
    import traceback
    print("\nDetailed traceback:")
    traceback.print_exc()
    
    print("\n" + "=" * 50)
    print("Possible solutions:")
    print("1. Check if the 'mssql' backend is properly installed")
    print("2. Verify the connection string format")
    print("3. Check if there are any special characters in the password")
