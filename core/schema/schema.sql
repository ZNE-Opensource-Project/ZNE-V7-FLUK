CREATE TABLE IF NOT EXISTS guilds (
    guild_id INTEGER PRIMARY KEY,
    nuke_count INTEGER DEFAULT 0,
    last_nuke REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS messages (
    message_id TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    token TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    author_id INTEGER NOT NULL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);

CREATE TABLE IF NOT EXISTS webhooks (
    webhook_id INTEGER PRIMARY KEY,
    webhook_token TEXT NOT NULL,
    channel_id INTEGER NOT NULL,
    guild_id INTEGER NOT NULL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);

CREATE TABLE IF NOT EXISTS tracked_tokens (
    token TEXT PRIMARY KEY,
    app_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL,
    created_at REAL DEFAULT (strftime('%s', 'now'))
);
