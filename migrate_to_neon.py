import os
from sqlalchemy import create_engine, MetaData, TIMESTAMP
from sqlalchemy.types import DateTime, Boolean, JSON
from sqlalchemy.orm import Session

# =========================================================
# CONFIGURATION
# =========================================================
LOCAL_DB_URI = "sqlite:///instance/maxcinema.db"

# PASTE YOUR NEON URL HERE
# Ensure it starts with postgresql://
NEON_DB_URI = "postgresql://neondb_owner:npg_GjPbLC7T9rtZ@ep-withered-shadow-a4a0d1w6-pooler.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"

def run_migration():
    print("🔌 Connecting to databases...")
    local_engine = create_engine(LOCAL_DB_URI)
    neon_engine = create_engine(NEON_DB_URI)

    # 1. READ LOCAL SCHEMA
    print("📖 Reading local schema...")
    metadata = MetaData()
    metadata.reflect(bind=local_engine)

    # =========================================================
    # 🛠️ THE FIX: TRANSLATE SQLITE TYPES TO POSTGRES TYPES
    # =========================================================
    print("🔧 Translating SQLite types for Postgres...")
    for table in metadata.tables.values():
        for column in table.columns:
            # Convert 'DATETIME' -> Generic 'DateTime' (which becomes TIMESTAMP in Postgres)
            if str(column.type).upper() == 'DATETIME':
                column.type = DateTime()
            # Ensure Booleans are standard
            elif str(column.type).upper() == 'BOOLEAN':
                column.type = Boolean()
            # Ensure JSON is handled correctly if detected
            elif str(column.type).upper() == 'JSON':
                column.type = JSON()

    # 2. CREATE TABLES IN CLOUD
    print("🏗️  Creating tables in Neon Postgres...")
    # Drop existing tables to avoid conflicts (Optional, safer for fresh start)
    # metadata.drop_all(bind=neon_engine) 
    metadata.create_all(bind=neon_engine)

    # 3. TRANSFER DATA
    print("🚀 Starting data transfer...")
    
    LocalSession = Session(bind=local_engine)
    NeonSession = Session(bind=neon_engine)

    table_order = [
        'user', 'genre', 'storage_servers',
        'all_video', 'video_genre', 'movie', 'series',
        'season', 'episode', 'rating', 'recent_item',
        'trailer', 'comment'
    ]

    with LocalSession as local_sess, NeonSession as neon_sess:
        for table_name in table_order:
            if table_name in metadata.tables:
                table = metadata.tables[table_name]
                print(f"   Processing table: {table_name}...")
                
                # Order by ID to prevent foreign key errors
                query = table.select()
                if 'id' in table.c:
                    query = query.order_by(table.c.id)
                
                data = local_sess.execute(query).fetchall()
                
                if data:
                    # Insert in batches
                    batch_size = 1000
                    for i in range(0, len(data), batch_size):
                        batch = data[i:i + batch_size]
                        neon_sess.execute(table.insert(), [dict(row._mapping) for row in batch])
                        neon_sess.commit()
                        print(f"        Written {len(batch)} rows...")
                    print(f"     ✅ Table complete.")
                else:
                    print("     ⚠️  Table empty, skipping.")
            else:
                print(f"   ❌ Table {table_name} not found in local DB!")

    print("\n✨ Migration Complete! Your Neon DB is populated.")

if __name__ == "__main__":
    run_migration()