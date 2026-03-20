# setup_db.py
import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv

load_dotenv()

MASTER_USER = os.environ.get("MASTER_DB_USER")
MASTER_PASSWORD = os.environ.get("MASTER_DB_PASSWORD")
DB_NAME = os.environ.get("DB_NAME")
DB_USER = os.environ.get("DB_USER")
DB_PASSWORD = os.environ.get("DB_PASSWORD")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = os.environ.get("DB_PORT", "5432")

def setup_database():
    if not MASTER_PASSWORD:
        print("❌ Error: MASTER_DB_PASSWORD is missing from your .env file.")
        return

    print("Starting database setup using secure environment variables...")
    
    try:
        conn = psycopg2.connect(
            dbname='postgres', 
            user=MASTER_USER,   
            password=MASTER_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        print(f"Creating user '{DB_USER}'...")
        try:
            cursor.execute(f"CREATE USER {DB_USER} WITH PASSWORD '{DB_PASSWORD}';")
        except psycopg2.errors.DuplicateObject:
            print("User already exists, skipping.")

        print(f"Creating database '{DB_NAME}'...")
        try:
            cursor.execute(f"CREATE DATABASE {DB_NAME};")
        except psycopg2.errors.DuplicateDatabase:
            print("Database already exists, skipping.")

        cursor.execute(f"GRANT ALL PRIVILEGES ON DATABASE {DB_NAME} TO {DB_USER};")
        cursor.execute(f"ALTER USER {DB_USER} CREATEDB;")
        
        cursor.close()
        conn.close()
        print("Base database created successfully.")

        print(f"Connecting to '{DB_NAME}' to configure schema permissions...")
        conn_new = psycopg2.connect(
            dbname=DB_NAME,
            user=MASTER_USER,
            password=MASTER_PASSWORD,
            host=DB_HOST,
            port=DB_PORT
        )
        conn_new.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
        cursor_new = conn_new.cursor()
        cursor_new.execute(f"GRANT ALL ON SCHEMA public TO {DB_USER};")
        cursor_new.execute(f"ALTER DATABASE {DB_NAME} OWNER TO {DB_USER};")
        
        cursor_new.close()
        conn_new.close()
        
        print("✅ Database setup complete!")

    except Exception as e:
        print(f"❌ An error occurred: {e}")

if __name__ == "__main__":
    setup_database()
