#!/bin/bash
# Параметризованный скрипт инициализации PostgreSQL
# Использование: POSTGRES_RECORDS_COUNT=50000 ./init-parametrized.sh

RECORDS_COUNT=${POSTGRES_RECORDS_COUNT:-100000}

echo "Инициализация PostgreSQL с $RECORDS_COUNT записями..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    CREATE TABLE IF NOT EXISTS users (
        id BIGINT PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        created_at TIMESTAMPTZ NOT NULL,
        last_login_at TIMESTAMPTZ NOT NULL
    );
    
    TRUNCATE TABLE users;
    
    INSERT INTO users (id, name, email, created_at, last_login_at)
    SELECT
        g AS id,
        'User ' || g AS name,
        'user' || g || '@example.com' AS email,
        NOW() - (random() * INTERVAL '365 days') AS created_at,
        NOW() - (random() * INTERVAL '365 days') AS last_login_at
    FROM generate_series(1, $RECORDS_COUNT) AS g;
    
    CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users (last_login_at);
    
    SELECT COUNT(*) as total_records FROM users;
EOSQL

echo "Инициализация завершена."




