import sys
import os
import zipfile
import io
import sqlite3
import gzip
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'proto'))
import schema_mihon_pb2 as pb

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS Category (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64) NOT NULL,
    "order" INT DEFAULT 0 NOT NULL,
    is_default BOOLEAN DEFAULT 0 NOT NULL,
    uuid VARCHAR(128) NULL,
    create_at BIGINT NOT NULL DEFAULT 0,
    update_at BIGINT NOT NULL DEFAULT 0,
    is_delete BOOLEAN NOT NULL DEFAULT 0,
    dirty BOOLEAN NOT NULL DEFAULT 0,
    commit_id BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS Source (
    id BIGINT NOT NULL PRIMARY KEY,
    name VARCHAR(256) NOT NULL
);

CREATE TABLE IF NOT EXISTS Manga (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url VARCHAR(2048) NOT NULL,
    artist VARCHAR(256) NULL,
    author VARCHAR(256) NULL,
    description TEXT NULL,
    genre VARCHAR(1024) NULL,
    title VARCHAR(512) NOT NULL,
    status INT DEFAULT 0 NOT NULL,
    thumbnail_url VARCHAR(2048) NULL,
    thumbnail_url_last_fetched BIGINT DEFAULT 0 NOT NULL,
    in_library BOOLEAN DEFAULT 0 NOT NULL,
    default_category BOOLEAN DEFAULT 0 NOT NULL,
    in_library_at BIGINT DEFAULT 0 NOT NULL,
    source BIGINT NOT NULL,
    real_url VARCHAR(2048) NULL,
    last_fetched_at BIGINT DEFAULT 0 NOT NULL,
    chapters_last_fetched_at BIGINT DEFAULT 0 NOT NULL,
    update_strategy VARCHAR(64) DEFAULT '0' NOT NULL,
    last_download_at BIGINT DEFAULT 0 NOT NULL,
    is_delete BOOLEAN DEFAULT 0 NOT NULL,
    create_at BIGINT NOT NULL DEFAULT 0,
    update_at BIGINT NOT NULL DEFAULT 0,
    dirty BOOLEAN NOT NULL DEFAULT 0,
    commit_id BIGINT NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '{}',
    meta TEXT NOT NULL DEFAULT '{}',
    initialized BOOLEAN NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS CategoryManga (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category INT NOT NULL,
    manga INT NOT NULL
);

CREATE TABLE IF NOT EXISTS Chapter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url VARCHAR(2048) NOT NULL,
    name VARCHAR(512) NOT NULL,
    date_upload BIGINT DEFAULT 0 NOT NULL,
    chapter_number SINGLE DEFAULT -1.0 NOT NULL,
    scanlator VARCHAR(128) NULL,
    read BOOLEAN DEFAULT 0 NOT NULL,
    bookmark BOOLEAN DEFAULT 0 NOT NULL,
    last_page_read INT DEFAULT 0 NOT NULL,
    last_read_at BIGINT DEFAULT 0 NOT NULL,
    fetched_at BIGINT DEFAULT 0 NOT NULL,
    source_order INT NOT NULL,
    real_url VARCHAR(2048) NULL,
    is_downloaded BOOLEAN DEFAULT 0 NOT NULL,
    page_count INT DEFAULT -1 NOT NULL,
    manga INT NOT NULL,
    original_chapter_id INTEGER,
    create_at BIGINT NOT NULL DEFAULT 0,
    update_at BIGINT NOT NULL DEFAULT 0,
    dirty BOOLEAN NOT NULL DEFAULT 0,
    commit_id BIGINT NOT NULL DEFAULT 0,
    memo TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS History (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    create_at BIGINT DEFAULT 0 NOT NULL,
    update_at BIGINT DEFAULT 0 NOT NULL,
    is_delete BOOLEAN DEFAULT 0 NOT NULL,
    manga_id INTEGER NOT NULL,
    last_chapter_id INTEGER NOT NULL,
    last_read_at BIGINT DEFAULT 0 NOT NULL,
    dirty BOOLEAN NOT NULL DEFAULT 0,
    commit_id BIGINT NOT NULL DEFAULT 0,
    last_chapter_name VARCHAR(512) NULL,
    read_duration INT DEFAULT 0 NOT NULL,
    sync_buff INT DEFAULT 0 NOT NULL,
    UNIQUE (manga_id) ON CONFLICT REPLACE
);

CREATE TABLE IF NOT EXISTS Repo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type INT DEFAULT 0 NOT NULL,
    name VARCHAR(1024) NOT NULL,
    meta_url VARCHAR(2048) NOT NULL,
    base_url VARCHAR(2048) NOT NULL,
    homepage VARCHAR(2048) NULL,
    deleted BOOLEAN DEFAULT 0 NOT NULL,
    create_at BIGINT DEFAULT 0 NOT NULL,
    update_at BIGINT DEFAULT 0 NOT NULL,
    dirty BOOLEAN NOT NULL DEFAULT 0,
    commit_id BIGINT NOT NULL DEFAULT 0,
    index_url VARCHAR(2048) NULL,
    extension_list_url VARCHAR(2048) NULL,
    badge_label VARCHAR(1024) NULL,
    signing_key_fingerprint VARCHAR(2048) NULL,
    contact_discord VARCHAR(2048) NULL,
    is_legacy BOOLEAN NOT NULL DEFAULT 1,
    last_meta_refresh_at BIGINT NOT NULL DEFAULT 0
);
"""

def convert_mihon_to_tachimanga(input_path, output_path, log_callback=print):
    log_callback(f"Opening Mihon backup: {input_path}")
    with gzip.open(input_path, 'rb') as f:
        data = f.read()

    backup = pb.Backup()
    backup.ParseFromString(data)

    conn = sqlite3.connect(':memory:')
    cur = conn.cursor()
    cur.executescript(CREATE_TABLES_SQL)

    now = int(time.time())

    # 1. Categories
    category_id_map = {}  # 0-indexed in protobuf order to category DB id
    for idx, cat in enumerate(backup.backupCategories):
        cur.execute(
            "INSERT INTO Category (name, `order`, is_default, create_at, update_at) VALUES (?, ?, 0, ?, ?)",
            (cat.name, cat.order if cat.HasField('order') else idx, now, now)
        )
        cat_db_id = cur.lastrowid
        category_id_map[idx] = cat_db_id
        # Also map by cat.order if available
        if cat.HasField('order'):
            category_id_map[cat.order] = cat_db_id
    log_callback(f"Inserted {len(backup.backupCategories)} categories")

    # 2. Sources
    for src in backup.backupSources:
        cur.execute("INSERT OR REPLACE INTO Source (id, name) VALUES (?, ?)", (src.sourceId, src.name))
    log_callback(f"Inserted {len(backup.backupSources)} sources")

    # 3. Extension Repos
    for repo in backup.backupExtensionRepo:
        cur.execute(
            """INSERT INTO Repo (type, name, meta_url, base_url, homepage, signing_key_fingerprint, create_at, update_at)
               VALUES (0, ?, ?, ?, ?, ?, ?, ?)""",
            (repo.name, repo.baseUrl, repo.baseUrl, repo.website or repo.baseUrl, repo.signingKeyFingerprint, now, now)
        )
    log_callback(f"Inserted {len(backup.backupExtensionRepo)} extension repos")

    # 4. Manga & Chapters
    manga_count = 0
    chapter_count = 0
    history_count = 0

    for bm in backup.backupManga:
        genres = ", ".join(bm.genre) if bm.genre else None
        strat = '1' if bm.updateStrategy == pb.UpdateStrategy.ONLY_FETCH_ONCE else '0'
        in_lib_at = bm.dateAdded if bm.HasField('dateAdded') and bm.dateAdded > 0 else (now * 1000)

        cur.execute(
            """INSERT INTO Manga (
                url, artist, author, description, genre, title, status, thumbnail_url,
                in_library, default_category, in_library_at, source, update_strategy,
                create_at, update_at, initialized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?)""",
            (
                bm.url,
                bm.artist if bm.HasField('artist') else None,
                bm.author if bm.HasField('author') else None,
                bm.description if bm.HasField('description') else None,
                genres,
                bm.title or '',
                bm.status if bm.HasField('status') else 0,
                bm.thumbnailUrl if bm.HasField('thumbnailUrl') else None,
                1 if (bm.favorite if bm.HasField('favorite') else True) else 0,
                in_lib_at,
                bm.source,
                strat,
                now,
                now,
                1 if (bm.initialized if bm.HasField('initialized') else True) else 0
            )
        )
        manga_id = cur.lastrowid
        manga_count += 1

        # Categories for Manga
        for cat_idx in bm.categories:
            if cat_idx in category_id_map:
                cur.execute(
                    "INSERT INTO CategoryManga (category, manga) VALUES (?, ?)",
                    (category_id_map[cat_idx], manga_id)
                )

        # Chapters
        ch_url_to_id = {}
        for b_ch in bm.chapters:
            cur.execute(
                """INSERT INTO Chapter (
                    url, name, date_upload, chapter_number, scanlator, read, bookmark,
                    last_page_read, last_read_at, fetched_at, source_order, manga,
                    create_at, update_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    b_ch.url,
                    b_ch.name,
                    b_ch.dateUpload if b_ch.HasField('dateUpload') else 0,
                    b_ch.chapterNumber if b_ch.HasField('chapterNumber') else -1.0,
                    b_ch.scanlator if b_ch.HasField('scanlator') else None,
                    1 if b_ch.read else 0,
                    1 if b_ch.bookmark else 0,
                    b_ch.lastPageRead if b_ch.HasField('lastPageRead') else 0,
                    b_ch.lastModifiedAt if b_ch.HasField('lastModifiedAt') else 0,
                    b_ch.dateFetch if b_ch.HasField('dateFetch') else 0,
                    b_ch.sourceOrder if b_ch.HasField('sourceOrder') else 0,
                    manga_id,
                    now,
                    now
                )
            )
            ch_id = cur.lastrowid
            ch_url_to_id[b_ch.url] = (ch_id, b_ch.name)
            chapter_count += 1

        # History
        for h in bm.history:
            ch_info = ch_url_to_id.get(h.url)
            last_ch_id = ch_info[0] if ch_info else 0
            last_ch_name = ch_info[1] if ch_info else None
            read_time = h.lastRead if h.HasField('lastRead') else 0
            dur = h.readDuration if h.HasField('readDuration') else 0

            cur.execute(
                """INSERT OR REPLACE INTO History (
                    create_at, update_at, is_delete, manga_id, last_chapter_id,
                    last_read_at, last_chapter_name, read_duration
                ) VALUES (?, ?, 0, ?, ?, ?, ?, ?)""",
                (now, now, manga_id, last_ch_id, read_time, last_ch_name, dur)
            )
            history_count += 1

    conn.commit()
    log_callback(f"Processed {manga_count} mangas, {chapter_count} chapters, {history_count} histories")

    # Serialize SQLite database to bytes
    db_bytes = conn.serialize()

    # Build contents.zip
    contents_bio = io.BytesIO()
    with zipfile.ZipFile(contents_bio, 'w', zipfile.ZIP_DEFLATED) as zc:
        zc.writestr('tachimanga.db', db_bytes)
        zc.writestr('pref.json', json.dumps({"flutter.showStatusBar": False, "flutter.tabBarShowLabel": True}, indent=2))
        zc.writestr('pref-all.json', "{\n    AKLastIDMSEnvironment = 0;\n}\n")
    contents_zip_bytes = contents_bio.getvalue()

    # Build meta.json
    out_filename = os.path.basename(output_path)
    meta = {
        "state": 1,
        "extInfo": None,
        "downloadProgress": 0,
        "version": 520,
        "cloudBackup": False,
        "createAt": now,
        "checksum": "",
        "size": len(contents_zip_bytes),
        "type": 0,
        "updateAt": now,
        "backupId": 0,
        "downloaded": False,
        "remoteBackup": False,
        "name": out_filename
    }

    # Build final .tmb zip archive
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zt:
        zt.writestr('meta.json', json.dumps(meta, indent=2))
        zt.writestr('contents.zip', contents_zip_bytes)

    out_size = os.path.getsize(output_path)
    log_callback(f"Successfully created Tachimanga backup: {output_path} ({out_size:,} bytes)")
    return output_path

if __name__ == '__main__':
    src = sys.argv[1] if len(sys.argv) > 1 else 'Tachimanga_para_Mihon.tachibk'
    dst = sys.argv[2] if len(sys.argv) > 2 else 'test_output.tmb'
    convert_mihon_to_tachimanga(src, dst)
