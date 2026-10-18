-- 📣 message-pusher schema
CREATE TABLE apps(id INTEGER PRIMARY KEY, name TEXT UNIQUE, key_hash TEXT, channels_json TEXT DEFAULT '{}', retry_max INTEGER DEFAULT 5, created_at DATETIME);
CREATE TABLE messages(id INTEGER PRIMARY KEY, app_id INTEGER REFERENCES apps(id), title TEXT, body TEXT, status TEXT DEFAULT 'queued', created_at DATETIME);
CREATE TABLE receipts(id INTEGER PRIMARY KEY, message_id INTEGER REFERENCES messages(id), channel TEXT, status TEXT DEFAULT 'queued', attempts INTEGER DEFAULT 0, detail TEXT, next_retry_at DATETIME, updated_at DATETIME);
