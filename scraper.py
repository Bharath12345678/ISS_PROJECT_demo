import os
import csv
import mysql.connector
import requests
from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database

load_dotenv()

conn = mysql.connector.connect(
    host=os.getenv("MYSQL_HOST"),
    user=os.getenv("MYSQL_USER"),
    password=os.getenv("MYSQL_PASSWORD"),
    database=os.getenv("MYSQL_DB")
)
cursor = conn.cursor()

cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        uid VARCHAR(255) PRIMARY KEY,
        name VARCHAR(255),
        elo_rating INT DEFAULT 1200,
        is_online BOOLEAN DEFAULT FALSE
    )
""")
conn.commit()

client = MongoClient(os.getenv("MONGO_URI"))
db = client[os.getenv("MONGO_DB_NAME")]
collection = db["profile_images"]

try:
    with open("batch_data.csv", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            uid = row["uid"]
            name = row["name"]
            base_url = row["website_url"]
            if not base_url.startswith("http"):
                base_url = "https://" + base_url
            url = base_url + "/images/pfp.jpg"

            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    cursor.execute("""
                        INSERT IGNORE INTO users (uid, name, elo_rating, is_online)
                        VALUES (%s, %s, 1200, FALSE)
                    """, (uid, name))

                    collection.update_one(
                        {"uid": uid},
                        {"$set": {"uid": uid, "image": response.content}},
                        upsert=True
                    )

                    conn.commit()
                else:
                    print(f"[SKIP] {uid} - status {response.status_code}")
            except Exception as e:
                print(f"[ERROR] {uid} - {e}")
finally:
    cursor.close()
    conn.close()
    client.close()