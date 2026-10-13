import os
import sys
import io
import json
import time
import gzip
import zipfile
import sqlite3
import plistlib
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

# Ensure proto dir is in sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
proto_dir = os.path.join(current_dir, 'proto')
if proto_dir not in sys.path:
    sys.path.insert(0, proto_dir)

import schema_mihon_pb2 as pb

# ----------------- Data Structures -----------------

@dataclass
class UnifiedChapter:
    name: str = ""
    url: str = ""
    chapter_number: float = -1.0
    date_upload: int = 0
    scanlator: Optional[str] = None
    read: bool = False
    bookmark: bool = False
    last_page_read: int = 0
    last_read_at: int = 0
    source_order: int = 0

@dataclass
class UnifiedHistory:
    chapter_url: str = ""
    last_read_at: int = 0
    read_duration: int = 0

@dataclass
class UnifiedManga:
    title: str = ""
    url: str = ""
    source_id: str = "0"
    source_name: Optional[str] = None
    author: Optional[str] = None
    artist: Optional[str] = None
    description: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    status: int = 0
    thumbnail_url: Optional[str] = None
    in_library: bool = True
    date_added: int = 0
    categories: List[str] = field(default_factory=list)
    chapters: List[UnifiedChapter] = field(default_factory=list)
    history: List[UnifiedHistory] = field(default_factory=list)

@dataclass
class UnifiedCategory:
    name: str = ""
    order: int = 0

@dataclass
class UnifiedSource:
    id: str = "0"
    name: str = ""

@dataclass
class UnifiedRepo:
    name: str = ""
    base_url: str = ""
    signing_key_fingerprint: str = ""
    website: str = ""

@dataclass
class UnifiedBackup:
    categories: List[UnifiedCategory] = field(default_factory=list)
    sources: List[UnifiedSource] = field(default_factory=list)
    repos: List[UnifiedRepo] = field(default_factory=list)
    manga: List[UnifiedManga] = field(default_factory=list)

# ----------------- Format Detection -----------------

def detect_backup_format(filepath: str) -> str:
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.tmb':
        return 'tachimanga'
    elif ext == '.tachibk':
        return 'mihon'
    elif ext == '.backup':
        return 'mangayomi'
    elif ext == '.aib':
        return 'aidoku'
    elif ext == '.pas4':
        return 'paperback'
    elif ext == '.gz' and filepath.lower().endswith('.proto.gz'):
        return 'tachiyomi'

    # Check magic bytes and zip contents
    try:
        with open(filepath, 'rb') as f:
            header = f.read(4)
        if header.startswith(b'\x1f\x8b'):
            return 'mihon'
        elif header.startswith(b'PK\x03\x04'):
            with zipfile.ZipFile(filepath, 'r') as z:
                names = z.namelist()
                if 'meta.json' in names and 'contents.zip' in names:
                    return 'tachimanga'
                if any(n.endswith('.db') for n in names):
                    return 'mangayomi'
                if any('__MANGA_INFO' in n for n in names):
                    return 'paperback'
        elif header.startswith(b'bplist'):
            return 'aidoku'
    except Exception:
        pass
    return 'unknown'

# ----------------- Importers -----------------

def import_tachimanga(filepath: str, log_cb=print) -> UnifiedBackup:
    log_cb(f"Lendo backup Tachimanga: {os.path.basename(filepath)}")
    with zipfile.ZipFile(filepath, 'r') as z:
        contents_zip_bytes = z.read('contents.zip')
    with zipfile.ZipFile(io.BytesIO(contents_zip_bytes), 'r') as c:
        db_bytes = c.read('tachimanga.db')

    conn = sqlite3.connect(':memory:')
    conn.deserialize(db_bytes)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    backup = UnifiedBackup()

    # Categories
    cur.execute("SELECT * FROM Category WHERE is_delete = 0 ORDER BY `order` ASC, id ASC")
    cat_rows = cur.fetchall()
    cat_id_to_name = {}
    for r in cat_rows:
        cat_id_to_name[r['id']] = r['name']
        backup.categories.append(UnifiedCategory(name=r['name'], order=r['order']))

    # Sources
    cur.execute("SELECT DISTINCT id, name FROM Source")
    for r in cur.fetchall():
        backup.sources.append(UnifiedSource(id=str(r['id']), name=r['name']))

    # Repos
    try:
        cur.execute("SELECT * FROM Repo WHERE deleted = 0")
        for r in cur.fetchall():
            cols = r.keys()
            fp = r['signing_key_fingerprint'] if 'signing_key_fingerprint' in cols and r['signing_key_fingerprint'] else ''
            backup.repos.append(UnifiedRepo(
                name=r['name'],
                base_url=r['base_url'],
                signing_key_fingerprint=fp,
                website=r['homepage'] or r['base_url']
            ))
    except Exception:
        pass

    # Category mappings
    cur.execute("SELECT category, manga FROM CategoryManga")
    manga_to_cats = {}
    for r in cur.fetchall():
        if r['category'] in cat_id_to_name:
            manga_to_cats.setdefault(r['manga'], []).append(cat_id_to_name[r['category']])

    # Chapters
    cur.execute("SELECT * FROM Chapter ORDER BY source_order ASC")
    manga_to_chaps = {}
    chap_id_to_url = {}
    for r in cur.fetchall():
        url = r['real_url'] or r['url']
        chap_id_to_url[r['id']] = url
        last_read = r['last_read_at'] or 0
        if 0 < last_read < 10000000000:
            last_read *= 1000
        ch = UnifiedChapter(
            name=r['name'],
            url=url,
            chapter_number=float(r['chapter_number'] or 0.0),
            date_upload=int(r['date_upload'] or 0),
            scanlator=r['scanlator'] or None,
            read=bool(r['read']),
            bookmark=bool(r['bookmark']),
            last_page_read=int(r['last_page_read'] or 0),
            last_read_at=last_read,
            source_order=int(r['source_order'] or 0)
        )
        manga_to_chaps.setdefault(r['manga'], []).append(ch)

    # History
    cur.execute("SELECT * FROM History WHERE is_delete = 0")
    manga_to_hist = {}
    for r in cur.fetchall():
        ch_url = chap_id_to_url.get(r['last_chapter_id'], '')
        read_time = r['last_read_at'] or 0
        if 0 < read_time < 10000000000:
            read_time *= 1000
        manga_to_hist.setdefault(r['manga_id'], []).append(UnifiedHistory(
            chapter_url=ch_url,
            last_read_at=read_time,
            read_duration=int(r['read_duration'] or 0)
        ))

    # Manga
    cur.execute("SELECT * FROM Manga WHERE in_library = 1 OR id IN (SELECT manga FROM Chapter) OR id IN (SELECT manga_id FROM History)")
    manga_rows = cur.fetchall()
    for r in manga_rows:
        m_id = r['id']
        genres = [g.strip() for g in (r['genre'] or '').split(',') if g.strip()]
        date_add = r['in_library_at'] if r['in_library_at'] and r['in_library_at'] > 0 else int(time.time() * 1000)
        manga = UnifiedManga(
            title=r['title'] or '',
            url=r['real_url'] or r['url'],
            source_id=str(r['source']),
            author=r['author'] or None,
            artist=r['artist'] or None,
            description=r['description'] or None,
            genres=genres,
            status=int(r['status'] or 0),
            thumbnail_url=r['thumbnail_url'] or None,
            in_library=bool(r['in_library']),
            date_added=date_add,
            categories=manga_to_cats.get(m_id, []),
            chapters=manga_to_chaps.get(m_id, []),
            history=manga_to_hist.get(m_id, [])
        )
        backup.manga.append(manga)

    log_cb(f"Lidos {len(backup.manga)} mangás, {sum(len(m.chapters) for m in backup.manga)} capítulos")
    return backup

def import_mihon(filepath: str, log_cb=print) -> UnifiedBackup:
    log_cb(f"Lendo backup Mihon/Tachiyomi: {os.path.basename(filepath)}")
    with gzip.open(filepath, 'rb') as f:
        data = f.read()
    pb_backup = pb.Backup()
    pb_backup.ParseFromString(data)

    backup = UnifiedBackup()

    # Categories
    for idx, c in enumerate(pb_backup.backupCategories):
        order = c.order if c.HasField('order') else idx
        backup.categories.append(UnifiedCategory(name=c.name, order=order))

    # Sources
    for s in pb_backup.backupSources:
        backup.sources.append(UnifiedSource(id=str(s.sourceId), name=s.name))

    # Repos
    for r in pb_backup.backupExtensionRepo:
        backup.repos.append(UnifiedRepo(
            name=r.name,
            base_url=r.baseUrl,
            signing_key_fingerprint=r.signingKeyFingerprint,
            website=r.website or r.baseUrl
        ))

    # Manga
    for bm in pb_backup.backupManga:
        cat_names = []
        for cat_idx in bm.categories:
            if 0 <= cat_idx < len(backup.categories):
                cat_names.append(backup.categories[cat_idx].name)

        chaps = []
        for ch in bm.chapters:
            chaps.append(UnifiedChapter(
                name=ch.name,
                url=ch.url,
                chapter_number=float(ch.chapterNumber if ch.HasField('chapterNumber') else -1.0),
                date_upload=int(ch.dateUpload if ch.HasField('dateUpload') else 0),
                scanlator=ch.scanlator if ch.HasField('scanlator') else None,
                read=bool(ch.read),
                bookmark=bool(ch.bookmark),
                last_page_read=int(ch.lastPageRead if ch.HasField('lastPageRead') else 0),
                last_read_at=int(ch.lastModifiedAt if ch.HasField('lastModifiedAt') else 0),
                source_order=int(ch.sourceOrder if ch.HasField('sourceOrder') else 0)
            ))

        hist = []
        for h in bm.history:
            hist.append(UnifiedHistory(
                chapter_url=h.url,
                last_read_at=int(h.lastRead if h.HasField('lastRead') else 0),
                read_duration=int(h.readDuration if h.HasField('readDuration') else 0)
            ))

        date_add = int(bm.dateAdded if bm.HasField('dateAdded') and bm.dateAdded > 0 else (time.time() * 1000))
        backup.manga.append(UnifiedManga(
            title=bm.title or '',
            url=bm.url,
            source_id=str(bm.source),
            author=bm.author if bm.HasField('author') else None,
            artist=bm.artist if bm.HasField('artist') else None,
            description=bm.description if bm.HasField('description') else None,
            genres=list(bm.genre),
            status=int(bm.status if bm.HasField('status') else 0),
            thumbnail_url=bm.thumbnailUrl if bm.HasField('thumbnailUrl') else None,
            in_library=bool(bm.favorite if bm.HasField('favorite') else True),
            date_added=date_add,
            categories=cat_names,
            chapters=chaps,
            history=hist
        ))

    log_cb(f"Lidos {len(backup.manga)} mangás, {sum(len(m.chapters) for m in backup.manga)} capítulos")
    return backup

def import_mangayomi(filepath: str, log_cb=print) -> UnifiedBackup:
    log_cb(f"Lendo backup Mangayomi: {os.path.basename(filepath)}")
    with zipfile.ZipFile(filepath, 'r') as z:
        db_file = next(f for f in z.namelist() if f.endswith('.db'))
        db_json = json.loads(z.read(db_file).decode('utf-8'))

    backup = UnifiedBackup()
    cat_id_to_name = {}
    for c in db_json.get('categories', []):
        name = c.get('name', 'Default')
        cid = c.get('id')
        if cid is not None:
            cat_id_to_name[str(cid)] = name
        backup.categories.append(UnifiedCategory(name=name, order=c.get('id', 0)))

    # Chapters by mangaId
    chapters_by_manga = {}
    chap_id_to_url = {}
    for ch in db_json.get('chapters', []):
        m_id = str(ch.get('mangaId'))
        url = ch.get('url') or ch.get('name') or ''
        chap_id_to_url[ch.get('id')] = url
        d_up = int(ch.get('dateUpload') or 0)
        c_obj = UnifiedChapter(
            name=ch.get('name', ''),
            url=url,
            chapter_number=float(ch.get('chapterNumber') or -1.0),
            date_upload=d_up,
            scanlator=ch.get('scanlator'),
            read=bool(ch.get('isRead')),
            bookmark=bool(ch.get('isBookmarked')),
            last_page_read=int(ch.get('lastPageRead') or 0),
            source_order=int(ch.get('sourceOrder') or 0)
        )
        chapters_by_manga.setdefault(m_id, []).append(c_obj)

    # History by mangaId
    hist_by_manga = {}
    for h in db_json.get('history', []):
        m_id = str(h.get('mangaId'))
        c_id = h.get('chapterId')
        c_url = chap_id_to_url.get(c_id, '')
        hist_by_manga.setdefault(m_id, []).append(UnifiedHistory(
            chapter_url=c_url,
            last_read_at=int(h.get('date') or 0)
        ))

    # Manga
    for m in db_json.get('manga', []):
        m_id = str(m.get('id'))
        cats_raw = str(m.get('categories') or '')
        cats = [cat_id_to_name.get(c.strip(), c.strip()) for c in cats_raw.split(',') if c.strip()]
        genres = m.get('genre') or m.get('genres') or []
        backup.manga.append(UnifiedManga(
            title=m.get('name') or m.get('title') or '',
            url=m.get('link') or m.get('url') or '',
            source_id=str(m.get('source') or '0'),
            author=m.get('author'),
            artist=m.get('artist'),
            description=m.get('description'),
            genres=genres,
            status=int(m.get('status') or 0),
            thumbnail_url=m.get('imageUrl') or m.get('customCoverImage'),
            in_library=bool(m.get('favorite', True)),
            date_added=int(m.get('dateAdded') or (time.time() * 1000)),
            categories=cats,
            chapters=chapters_by_manga.get(m_id, []),
            history=hist_by_manga.get(m_id, [])
        ))

    log_cb(f"Lidos {len(backup.manga)} mangás do Mangayomi")
    return backup

def import_aidoku(filepath: str, log_cb=print) -> UnifiedBackup:
    log_cb(f"Lendo backup Aidoku: {os.path.basename(filepath)}")
    with open(filepath, 'rb') as f:
        data = plistlib.load(f)

    backup = UnifiedBackup()
    for cat in data.get('categories', []):
        backup.categories.append(UnifiedCategory(name=str(cat)))

    manga_dict = {m.get('id'): m for m in data.get('manga', [])}
    chap_by_manga = {}
    chap_id_to_name = {}
    for ch in data.get('chapters', []):
        m_id = ch.get('mangaId')
        c_id = ch.get('id')
        chap_id_to_name[c_id] = ch.get('title', '')
        d_up = 0
        if isinstance(ch.get('dateUploaded'), datetime):
            d_up = int(ch['dateUploaded'].timestamp() * 1000)
        chap_by_manga.setdefault(m_id, []).append(UnifiedChapter(
            name=ch.get('title', ''),
            url=ch.get('id', ''),
            chapter_number=float(ch.get('chapter') or -1.0),
            date_upload=d_up,
            scanlator=ch.get('scanlator'),
            read=False,
            source_order=int(ch.get('sourceOrder') or 0)
        ))

    hist_by_manga = {}
    for h in data.get('history', []):
        m_id = h.get('mangaId')
        c_id = h.get('chapterId')
        r_time = 0
        if isinstance(h.get('dateRead'), datetime):
            r_time = int(h['dateRead'].timestamp() * 1000)
        hist_by_manga.setdefault(m_id, []).append(UnifiedHistory(
            chapter_url=c_id or '',
            last_read_at=r_time
        ))

    for lib in data.get('library', []):
        m_id = lib.get('mangaId')
        m_info = manga_dict.get(m_id, {})
        d_add = 0
        if isinstance(lib.get('dateAdded'), datetime):
            d_add = int(lib['dateAdded'].timestamp() * 1000)
        backup.manga.append(UnifiedManga(
            title=m_info.get('title') or m_id or '',
            url=m_info.get('url') or m_id or '',
            source_id=str(lib.get('sourceId') or '0'),
            author=m_info.get('author'),
            artist=m_info.get('artist'),
            description=m_info.get('description'),
            genres=m_info.get('tags') or [],
            status=int(m_info.get('status') or 0),
            thumbnail_url=m_info.get('cover'),
            in_library=True,
            date_added=d_add or int(time.time() * 1000),
            categories=lib.get('categories') or [],
            chapters=chap_by_manga.get(m_id, []),
            history=hist_by_manga.get(m_id, [])
        ))

    log_cb(f"Lidos {len(backup.manga)} mangás do Aidoku")
    return backup

def import_paperback(filepath: str, log_cb=print) -> UnifiedBackup:
    log_cb(f"Lendo backup Paperback: {os.path.basename(filepath)}")
    with zipfile.ZipFile(filepath, 'r') as z:
        manga_info = json.loads(z.read('__MANGA_INFO_V4').decode('utf-8')) if '__MANGA_INFO_V4' in z.namelist() else {}
        chapters = json.loads(z.read('__CHAPTER_V4').decode('utf-8')) if '__CHAPTER_V4' in z.namelist() else {}
        lib_manga = json.loads(z.read('__LIBRARY_MANGA_V4').decode('utf-8')) if '__LIBRARY_MANGA_V4' in z.namelist() else {}

    backup = UnifiedBackup()
    for m_id, info in manga_info.items():
        titles = info.get('titles', [])
        title = titles[0] if titles else info.get('id', '')
        backup.manga.append(UnifiedManga(
            title=title,
            url=info.get('id', ''),
            source_id="paperback",
            author=info.get('author'),
            artist=info.get('artist'),
            description=info.get('desc'),
            genres=[t.get('label', '') for t in info.get('tags', []) if isinstance(t, dict)],
            thumbnail_url=info.get('image'),
            in_library=m_id in lib_manga,
            date_added=int(time.time() * 1000)
        ))
    log_cb(f"Lidos {len(backup.manga)} mangás do Paperback")
    return backup

def load_any_backup(filepath: str, log_cb=print) -> UnifiedBackup:
    fmt = detect_backup_format(filepath)
    if fmt == 'tachimanga':
        return import_tachimanga(filepath, log_cb)
    elif fmt in ('mihon', 'tachiyomi'):
        return import_mihon(filepath, log_cb)
    elif fmt == 'mangayomi':
        return import_mangayomi(filepath, log_cb)
    elif fmt == 'aidoku':
        return import_aidoku(filepath, log_cb)
    elif fmt == 'paperback':
        return import_paperback(filepath, log_cb)
    else:
        # Fallback try mihon then tachimanga
        try:
            return import_mihon(filepath, log_cb)
        except Exception:
            return import_tachimanga(filepath, log_cb)

# ----------------- Exporters -----------------

def export_mihon(backup: UnifiedBackup, output_path: str, log_cb=print) -> str:
    log_cb("Exportando para formato Mihon / Tachiyomi (.tachibk)...")
    pb_backup = pb.Backup()

    # Categories
    cat_name_to_order = {}
    for idx, c in enumerate(backup.categories):
        cat_name_to_order[c.name] = idx
        pb_cat = pb.BackupCategory(name=c.name, order=idx, flags=1)
        pb_backup.backupCategories.append(pb_cat)

    # Extension Repos
    for r in backup.repos:
        pb_repo = pb.BackupExtensionRepos(
            baseUrl=r.base_url,
            name=r.name,
            shortName=r.name,
            website=r.website or r.base_url,
            signingKeyFingerprint=r.signing_key_fingerprint
        )
        pb_backup.backupExtensionRepo.append(pb_repo)

    # Sources
    sources_seen = set()
    for s in backup.sources:
        try:
            s_id = int(s.id)
            if s_id not in sources_seen:
                pb_backup.backupSources.append(pb.BackupSource(name=s.name, sourceId=s_id))
                sources_seen.add(s_id)
        except Exception:
            pass

    # Manga
    for m in backup.manga:
        bm = pb.BackupManga()
        try:
            bm.source = int(m.source_id)
        except Exception:
            bm.source = 0
        bm.url = m.url
        bm.title = m.title
        if m.artist: bm.artist = m.artist
        if m.author: bm.author = m.author
        if m.description: bm.description = m.description
        if m.genres: bm.genre.extend(m.genres)
        bm.status = m.status
        if m.thumbnail_url: bm.thumbnailUrl = m.thumbnail_url
        bm.dateAdded = m.date_added or int(time.time() * 1000)
        bm.favorite = m.in_library
        bm.initialized = True
        bm.updateStrategy = pb.UpdateStrategy.ALWAYS_UPDATE

        # Categories
        for cname in m.categories:
            if cname in cat_name_to_order:
                bm.categories.append(cat_name_to_order[cname])

        # Chapters
        for ch in m.chapters:
            b_ch = pb.BackupChapter()
            b_ch.url = ch.url
            b_ch.name = ch.name
            if ch.scanlator: b_ch.scanlator = ch.scanlator
            b_ch.read = ch.read
            b_ch.bookmark = ch.bookmark
            b_ch.lastPageRead = ch.last_page_read
            b_ch.dateUpload = ch.date_upload
            b_ch.chapterNumber = ch.chapter_number
            b_ch.sourceOrder = ch.source_order
            b_ch.lastModifiedAt = ch.last_read_at
            b_ch.version = 1
            bm.chapters.append(b_ch)

        # History
        for h in m.history:
            bm.history.append(pb.BackupHistory(
                url=h.chapter_url or m.url,
                lastRead=h.last_read_at,
                readDuration=h.read_duration
            ))

        pb_backup.backupManga.append(bm)

    proto_bytes = pb_backup.SerializeToString()
    with gzip.open(output_path, 'wb') as f_out:
        f_out.write(proto_bytes)

    out_size = os.path.getsize(output_path)
    log_cb(f"Salvo com sucesso: {output_path} ({out_size:,} bytes)")
    return output_path

def export_tachimanga(backup: UnifiedBackup, output_path: str, log_cb=print) -> str:
    from convert_mihon_to_tachimanga import CREATE_TABLES_SQL
    log_cb("Exportando para formato Tachimanga (.tmb)...")

    conn = sqlite3.connect(':memory:')
    cur = conn.cursor()
    cur.executescript(CREATE_TABLES_SQL)
    now = int(time.time())

    # Categories
    cat_name_to_db_id = {}
    for idx, c in enumerate(backup.categories):
        cur.execute(
            "INSERT INTO Category (name, `order`, is_default, create_at, update_at) VALUES (?, ?, 0, ?, ?)",
            (c.name, c.order, now, now)
        )
        cat_name_to_db_id[c.name] = cur.lastrowid

    # Sources
    for s in backup.sources:
        try:
            cur.execute("INSERT OR REPLACE INTO Source (id, name) VALUES (?, ?)", (int(s.id), s.name))
        except Exception:
            pass

    # Repos
    for r in backup.repos:
        cur.execute(
            """INSERT INTO Repo (type, name, meta_url, base_url, homepage, signing_key_fingerprint, create_at, update_at)
               VALUES (0, ?, ?, ?, ?, ?, ?, ?)""",
            (r.name, r.base_url, r.base_url, r.website or r.base_url, r.signing_key_fingerprint, now, now)
        )

    # Manga & Chapters
    for m in backup.manga:
        try:
            src_num = int(m.source_id)
        except Exception:
            src_num = 0
        cur.execute(
            """INSERT INTO Manga (
                url, artist, author, description, genre, title, status, thumbnail_url,
                in_library, default_category, in_library_at, source, update_strategy,
                create_at, update_at, initialized
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '0', ?, ?, 1)""",
            (
                m.url, m.artist, m.author, m.description, ", ".join(m.genres), m.title,
                m.status, m.thumbnail_url, 1 if m.in_library else 0,
                m.date_added or (now * 1000), src_num, now, now
            )
        )
        m_id = cur.lastrowid

        # Categories
        for cname in m.categories:
            if cname in cat_name_to_db_id:
                cur.execute("INSERT INTO CategoryManga (category, manga) VALUES (?, ?)", (cat_name_to_db_id[cname], m_id))

        # Chapters
        ch_url_to_id = {}
        for ch in m.chapters:
            cur.execute(
                """INSERT INTO Chapter (
                    url, name, date_upload, chapter_number, scanlator, read, bookmark,
                    last_page_read, last_read_at, fetched_at, source_order, manga, create_at, update_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
                (
                    ch.url, ch.name, ch.date_upload, ch.chapter_number, ch.scanlator,
                    1 if ch.read else 0, 1 if ch.bookmark else 0, ch.last_page_read,
                    ch.last_read_at, ch.source_order, m_id, now, now
                )
            )
            ch_url_to_id[ch.url] = (cur.lastrowid, ch.name)

        # History
        for h in m.history:
            info = ch_url_to_id.get(h.chapter_url)
            last_ch_id = info[0] if info else 0
            last_ch_name = info[1] if info else None
            cur.execute(
                """INSERT OR REPLACE INTO History (
                    create_at, update_at, is_delete, manga_id, last_chapter_id,
                    last_read_at, last_chapter_name, read_duration
                ) VALUES (?, ?, 0, ?, ?, ?, ?, ?)""",
                (now, now, m_id, last_ch_id, h.last_read_at, last_ch_name, h.read_duration)
            )

    conn.commit()
    db_bytes = conn.serialize()

    contents_bio = io.BytesIO()
    with zipfile.ZipFile(contents_bio, 'w', zipfile.ZIP_DEFLATED) as zc:
        zc.writestr('tachimanga.db', db_bytes)
        zc.writestr('pref.json', json.dumps({"flutter.showStatusBar": False, "flutter.tabBarShowLabel": True}, indent=2))
        zc.writestr('pref-all.json', "{\n    AKLastIDMSEnvironment = 0;\n}\n")
    contents_zip_bytes = contents_bio.getvalue()

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
        "name": os.path.basename(output_path)
    }

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zt:
        zt.writestr('meta.json', json.dumps(meta, indent=2))
        zt.writestr('contents.zip', contents_zip_bytes)

    out_size = os.path.getsize(output_path)
    log_cb(f"Salvo com sucesso: {output_path} ({out_size:,} bytes)")
    return output_path

def export_mangayomi(backup: UnifiedBackup, output_path: str, log_cb=print) -> str:
    log_cb("Exportando para formato Mangayomi (.backup)...")
    db_obj = {
        "version": "2",
        "categories": [],
        "manga": [],
        "chapters": [],
        "history": [],
        "tracks": []
    }

    cat_name_to_id = {}
    for idx, c in enumerate(backup.categories):
        cid = idx + 1
        cat_name_to_id[c.name] = cid
        db_obj["categories"].append({
            "id": cid,
            "name": c.name,
            "forItemType": 0
        })

    manga_id_counter = 1
    chapter_id_counter = 1

    for m in backup.manga:
        m_id = manga_id_counter
        manga_id_counter += 1

        cat_ids_str = ",".join(str(cat_name_to_id[c]) for c in m.categories if c in cat_name_to_id)
        db_obj["manga"].append({
            "id": m_id,
            "name": m.title,
            "source": m.source_id,
            "author": m.author or "",
            "artist": m.artist or "",
            "genre": m.genres,
            "imageUrl": m.thumbnail_url or "",
            "link": m.url,
            "status": m.status,
            "description": m.description or "",
            "categories": cat_ids_str,
            "favorite": m.in_library,
            "dateAdded": m.date_added or int(time.time() * 1000)
        })

        ch_url_to_id = {}
        for ch in m.chapters:
            c_id = chapter_id_counter
            chapter_id_counter += 1
            ch_url_to_id[ch.url] = c_id
            db_obj["chapters"].append({
                "id": c_id,
                "mangaId": m_id,
                "name": ch.name,
                "url": ch.url,
                "chapterNumber": ch.chapter_number,
                "dateUpload": str(ch.date_upload),
                "scanlator": ch.scanlator or "",
                "isRead": ch.read,
                "isBookmarked": ch.bookmark,
                "lastPageRead": ch.last_page_read,
                "sourceOrder": ch.source_order
            })

        for h in m.history:
            c_id = ch_url_to_id.get(h.chapter_url, 0)
            db_obj["history"].append({
                "mangaId": m_id,
                "chapterId": c_id,
                "date": str(h.last_read_at)
            })

    # Save to zip containing mangayomi.db
    json_bytes = json.dumps(db_obj, ensure_ascii=False, indent=2).encode('utf-8')
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('mangayomi.db', json_bytes)

    out_size = os.path.getsize(output_path)
    log_cb(f"Salvo com sucesso: {output_path} ({out_size:,} bytes)")
    return output_path

def export_aidoku(backup: UnifiedBackup, output_path: str, log_cb=print) -> str:
    log_cb("Exportando para formato Aidoku (.aib)...")
    now_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    aidoku_obj = {
        "categories": [c.name for c in backup.categories],
        "sources": [s.name for s in backup.sources],
        "library": [],
        "manga": [],
        "chapters": [],
        "history": [],
        "date": now_naive,
        "version": "1"
    }

    manga_id_counter = 1
    for m in backup.manga:
        m_id = str(manga_id_counter)
        manga_id_counter += 1

        d_add = datetime.fromtimestamp(m.date_added / 1000.0, timezone.utc).replace(tzinfo=None) if m.date_added else now_naive
        aidoku_obj["manga"].append({
            "id": m_id,
            "title": m.title,
            "author": m.author or "",
            "artist": m.artist or "",
            "description": m.description or "",
            "tags": m.genres,
            "status": m.status,
            "cover": m.thumbnail_url or "",
            "url": m.url
        })

        if m.in_library:
            aidoku_obj["library"].append({
                "mangaId": m_id,
                "sourceId": m.source_id,
                "categories": m.categories,
                "dateAdded": d_add
            })

        ch_counter = 1
        ch_url_to_id = {}
        for ch in m.chapters:
            cid = f"{m_id}_{ch_counter}"
            ch_counter += 1
            ch_url_to_id[ch.url] = cid
            d_up = datetime.fromtimestamp(ch.date_upload / 1000.0, timezone.utc).replace(tzinfo=None) if ch.date_upload > 0 else now_naive
            aidoku_obj["chapters"].append({
                "id": cid,
                "mangaId": m_id,
                "sourceId": m.source_id,
                "title": ch.name,
                "chapter": ch.chapter_number,
                "scanlator": ch.scanlator or "",
                "lang": "pt",
                "dateUploaded": d_up,
                "sourceOrder": ch.source_order
            })

        for h in m.history:
            cid = ch_url_to_id.get(h.chapter_url, "")
            d_read = datetime.fromtimestamp(h.last_read_at / 1000.0, timezone.utc).replace(tzinfo=None) if h.last_read_at > 0 else now_naive
            aidoku_obj["history"].append({
                "chapterId": cid,
                "mangaId": m_id,
                "sourceId": m.source_id,
                "dateRead": d_read
            })

    with open(output_path, 'wb') as f:
        plistlib.dump(aidoku_obj, f, fmt=plistlib.FMT_BINARY)

    out_size = os.path.getsize(output_path)
    log_cb(f"Salvo com sucesso: {output_path} ({out_size:,} bytes)")
    return output_path

def export_paperback(backup: UnifiedBackup, output_path: str, log_cb=print) -> str:
    log_cb("Exportando para formato Paperback (.pas4)...")
    manga_info = {}
    lib_manga = {}
    chapters_map = {}

    for idx, m in enumerate(backup.manga):
        m_id = f"manga_{idx+1}"
        manga_info[m_id] = {
            "id": m_id,
            "titles": [m.title],
            "covers": [m.thumbnail_url] if m.thumbnail_url else [],
            "image": m.thumbnail_url or "",
            "desc": m.description or "",
            "author": m.author or "",
            "artist": m.artist or "",
            "hentai": False,
            "status": "Ongoing" if m.status == 1 else "Completed",
            "tags": [{"id": g, "label": g} for g in m.genres],
            "additionalInfo": {}
        }
        if m.in_library:
            lib_manga[m_id] = {"id": m_id}

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('__MANGA_INFO_V4', json.dumps(manga_info, indent=2))
        z.writestr('__LIBRARY_MANGA_V4', json.dumps(lib_manga, indent=2))
        z.writestr('__CHAPTER_V4', json.dumps(chapters_map, indent=2))
        z.writestr('__SOURCE_MANGA_V4', json.dumps({}, indent=2))
        z.writestr('__CHAPTER_PROGRESS_MARKER_V4-1', json.dumps({}, indent=2))

    out_size = os.path.getsize(output_path)
    log_cb(f"Salvo com sucesso: {output_path} ({out_size:,} bytes)")
    return output_path

# ----------------- Main Converter Dispatcher -----------------

TARGET_FORMATS = {
    "mihon": ("Mihon (.tachibk)", ".tachibk", export_mihon),
    "tachi": ("Tachiyomi (.proto.gz)", ".proto.gz", export_mihon),
    "sy": ("TachiyomiSY (.tachibk)", ".tachibk", export_mihon),
    "j2k": ("TachiyomiJ2K (.tachibk)", ".tachibk", export_mihon),
    "yokai": ("Yokai (.tachibk)", ".tachibk", export_mihon),
    "neko": ("Neko (.tachibk)", ".tachibk", export_mihon),
    "tachimanga": ("Tachimanga (.tmb)", ".tmb", export_tachimanga),
    "mangayomi": ("Mangayomi (.backup)", ".backup", export_mangayomi),
    "aidoku": ("Aidoku (.aib)", ".aib", export_aidoku),
    "paperback": ("Paperback (.pas4)", ".pas4", export_paperback)
}

def convert_any(input_path: str, output_path: str, target_format: str, log_cb=print) -> str:
    target_key = target_format.lower()
    if target_key not in TARGET_FORMATS:
        raise ValueError(f"Formato '{target_format}' não é suportado. Formatos válidos: {list(TARGET_FORMATS.keys())}")

    log_cb(f"Iniciando conversão...")
    log_cb(f"Arquivo de origem: {input_path}")
    backup = load_any_backup(input_path, log_cb)

    exporter = TARGET_FORMATS[target_key][2]
    return exporter(backup, output_path, log_cb)
