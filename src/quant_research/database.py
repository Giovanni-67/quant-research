"""Local SQLite state. Short transactions, foreign keys and explicit schema version."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def connect(path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path,timeout=30,isolation_level=None)
    db.row_factory=sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('PRAGMA synchronous=FULL')
        version=db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0,1): raise ValueError('unsupported database schema')
        db.executescript('''
        CREATE TABLE IF NOT EXISTS portfolios(id TEXT PRIMARY KEY, spec TEXT NOT NULL, status TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS source_snapshots(hash TEXT PRIMARY KEY, payload TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS paper_updates(portfolio TEXT NOT NULL REFERENCES portfolios(id), revision INTEGER NOT NULL,
          identity TEXT NOT NULL, raw BLOB NOT NULL, actions BLOB NOT NULL, provenance TEXT NOT NULL, result TEXT NOT NULL, summary TEXT NOT NULL,
          PRIMARY KEY(portfolio,revision), UNIQUE(portfolio,identity));
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL,
          due REAL NOT NULL, interval REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, token TEXT, lease REAL, error TEXT, result TEXT);
        CREATE TABLE IF NOT EXISTS research(id TEXT PRIMARY KEY, request TEXT NOT NULL, state TEXT NOT NULL, response TEXT, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, time TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          kind TEXT NOT NULL, subject TEXT NOT NULL, detail TEXT NOT NULL);
        PRAGMA user_version=1;
        ''')
        yield db
    finally: db.close()


@contextmanager
def transaction(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield db
        db.execute('COMMIT')
    except BaseException:
        db.execute('ROLLBACK')
        raise
