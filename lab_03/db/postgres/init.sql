-- Инициализация PostgreSQL
-- По умолчанию создается 100000 записей
-- Для изменения количества записей используй скрипт scripts/refill_database.py

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ NOT NULL
);

INSERT INTO users (id, name, email, created_at, last_login_at)
SELECT
    g AS id,
    'User ' || g AS name,
    'user' || g || '@example.com' AS email,
    NOW() - (random() * INTERVAL '365 days') AS created_at,
    NOW() - (random() * INTERVAL '365 days') AS last_login_at
FROM generate_series(1, 100000) AS g;

CREATE INDEX IF NOT EXISTS idx_users_last_login_at ON users (last_login_at);



