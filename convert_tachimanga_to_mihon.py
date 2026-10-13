import sys
import os
import zipfile
import io
import sqlite3
import gzip
import time
from pathlib import Path

# Add proto to sys.path
proto_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proto')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)
import schema_mihon_pb2 as pb

def convert(tmb_path, output_path, include_all=False, log_callback=print):
    log_callback(f"Opening Tachimanga backup: {tmb_path}")
    with zipfile.ZipFile(tmb_path, 'r') as z:
        contents_zip_bytes = z.read('contents.zip')
    
    with zipfile.ZipFile(io.BytesIO(contents_zip_bytes), 'r') as c:
        db_bytes = c.read('tachimanga.db')
        
    conn = sqlite3.connect(':memory:')
    conn.deserialize(db_bytes)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    backup = pb.Backup()

    # 1. Categories
    cur.execute("SELECT * FROM Category WHERE is_delete = 0 ORDER BY `order` ASC, id ASC")
    categories = cur.fetchall()
    category_id_to_order = {}
    
    for idx, cat in enumerate(categories):
        category_id_to_order[cat['id']] = idx
        backup_cat = pb.BackupCategory(
            name=cat['name'],
            order=idx,
            flags=1
        )
        backup.backupCategories.append(backup_cat)
    log_callback(f"Exported {len(backup.backupCategories)} categories: {[c.name for c in backup.backupCategories]}")

    # 2. Extension Repos
    cur.execute("SELECT * FROM Repo WHERE deleted = 0")
    repos = cur.fetchall()
    for repo in repos:
        # Check available columns in repo
        repo_cols = repo.keys()
        fp = repo['signing_key_fingerprint'] if 'signing_key_fingerprint' in repo_cols and repo['signing_key_fingerprint'] else ''
        short_name = repo['short_name'] if 'short_name' in repo_cols and repo['short_name'] else repo['name']
        backup_repo = pb.BackupExtensionRepos(
            baseUrl=repo['base_url'],
            name=repo['name'],
            shortName=short_name,
            website=repo['homepage'] or repo['base_url'],
            signingKeyFingerprint=fp
        )
        backup.backupExtensionRepo.append(backup_repo)
    log_callback(f"Exported {len(backup.backupExtensionRepo)} extension repos")

    # 3. Sources
    cur.execute("SELECT DISTINCT id, name FROM Source")
    sources = cur.fetchall()
    for src in sources:
        backup_source = pb.BackupSource(
            name=src['name'],
            sourceId=src['id']
        )
        backup.backupSources.append(backup_source)
    log_callback(f"Exported {len(backup.backupSources)} sources")

    # 4. Manga & Chapters & History
    # Category mappings
    cur.execute("SELECT category, manga FROM CategoryManga")
    category_manga_rows = cur.fetchall()
    manga_to_categories = {}
    for cm in category_manga_rows:
        cat_id = cm['category']
        manga_id = cm['manga']
        if cat_id in category_id_to_order:
            manga_to_categories.setdefault(manga_id, []).append(category_id_to_order[cat_id])

    # History entries
    cur.execute("SELECT * FROM History WHERE is_delete = 0")
    history_rows = cur.fetchall()
    manga_to_history = {}
    for h in history_rows:
        manga_to_history.setdefault(h['manga_id'], []).append(h)

    # Chapters
    cur.execute("SELECT * FROM Chapter ORDER BY source_order ASC")
    chapter_rows = cur.fetchall()
    manga_to_chapters = {}
    chapter_id_to_row = {}
    for ch in chapter_rows:
        manga_to_chapters.setdefault(ch['manga'], []).append(ch)
        chapter_id_to_row[ch['id']] = ch

    # Select manga
    if include_all:
        cur.execute("SELECT * FROM Manga")
    else:
        # Manga in library, or with chapters, or with history
        cur.execute("""
            SELECT DISTINCT m.* FROM Manga m
            WHERE m.in_library = 1
               OR EXISTS (SELECT 1 FROM History h WHERE h.manga_id = m.id AND h.is_delete = 0)
               OR EXISTS (SELECT 1 FROM Chapter ch WHERE ch.manga = m.id)
        """)
    manga_rows = cur.fetchall()
    log_callback(f"Processing {len(manga_rows)} manga...")

    library_count = 0
    total_chapters_count = 0
    total_history_count = 0

    for m in manga_rows:
        m_id = m['id']
        is_library = bool(m['in_library'])
        if is_library:
            library_count += 1

        bm = pb.BackupManga()
        bm.source = m['source']
        bm.url = m['real_url'] or m['url']
        bm.title = m['title'] or ''
        if m['artist']: bm.artist = m['artist']
        if m['author']: bm.author = m['author']
        if m['description']: bm.description = m['description']
        if m['genre']:
            bm.genre.extend([g.strip() for g in m['genre'].split(',') if g.strip()])
        bm.status = int(m['status']) if m['status'] is not None else 0
        if m['thumbnail_url']: bm.thumbnailUrl = m['thumbnail_url']
        
        date_added = m['in_library_at'] if m['in_library_at'] and m['in_library_at'] > 0 else int(time.time() * 1000)
        bm.dateAdded = date_added
        bm.viewer = 0
        bm.chapterFlags = 0
        bm.viewer_flags = 0
        bm.favorite = is_library
        bm.initialized = bool(m['initialized'])

        # Update strategy
        strat_str = str(m['update_strategy'])
        if strat_str in ('1', 'ONLY_FETCH_ONCE'):
            bm.updateStrategy = pb.UpdateStrategy.ONLY_FETCH_ONCE
        else:
            bm.updateStrategy = pb.UpdateStrategy.ALWAYS_UPDATE

        # Categories
        if m_id in manga_to_categories:
            bm.categories.extend(manga_to_categories[m_id])

        # Chapters
        m_chapters = manga_to_chapters.get(m_id, [])
        for ch in m_chapters:
            b_ch = pb.BackupChapter()
            b_ch.url = ch['real_url'] or ch['url']
            b_ch.name = ch['name']
            if ch['scanlator']: b_ch.scanlator = ch['scanlator']
            b_ch.read = bool(ch['read'])
            b_ch.bookmark = bool(ch['bookmark'])
            b_ch.lastPageRead = int(ch['last_page_read'] or 0)
            b_ch.dateFetch = int(ch['fetched_at'] or 0)
            b_ch.dateUpload = int(ch['date_upload'] or 0)
            b_ch.chapterNumber = float(ch['chapter_number'] or 0.0)
            b_ch.sourceOrder = int(ch['source_order'] or 0)
            
            # lastReadAt / lastModifiedAt
            last_mod = ch['last_read_at'] or 0
            if last_mod > 0 and last_mod < 10000000000:
                last_mod *= 1000
            b_ch.lastModifiedAt = last_mod
            b_ch.version = 1
            
            bm.chapters.append(b_ch)
            total_chapters_count += 1

        # History
        m_histories = manga_to_history.get(m_id, [])
        for h in m_histories:
            last_ch_id = h['last_chapter_id']
            ch_row = chapter_id_to_row.get(last_ch_id)
            ch_url = (ch_row['real_url'] or ch_row['url']) if ch_row else (m['real_url'] or m['url'])
            
            read_time = h['last_read_at'] or 0
            if read_time > 0 and read_time < 10000000000:
                read_time *= 1000
                
            b_hist = pb.BackupHistory(
                url=ch_url,
                lastRead=read_time,
                readDuration=int(h['read_duration'] or 0)
            )
            bm.history.append(b_hist)
            total_history_count += 1

        backup.backupManga.append(bm)

    log_callback(f"Total Manga in backup: {len(backup.backupManga)} (Library: {library_count})")
    log_callback(f"Total Chapters in backup: {total_chapters_count}")
    log_callback(f"Total History records in backup: {total_history_count}")

    # Serialize and compress with gzip
    proto_bytes = backup.SerializeToString()
    log_callback(f"Serialized protobuf size: {len(proto_bytes):,} bytes")
    
    with gzip.open(output_path, 'wb') as f_out:
        f_out.write(proto_bytes)

    out_size = os.path.getsize(output_path)
    log_callback(f"Saved Mihon backup to {output_path} ({out_size:,} bytes)")
    return output_path

if __name__ == '__main__':
    tmb = sys.argv[1] if len(sys.argv) > 1 else 'Tachimanga_backup_2026-10-12_19-05-54-167.tmb'
    out = sys.argv[2] if len(sys.argv) > 2 else 'Tachimanga_para_Mihon.tachibk'
    convert(tmb, out)
