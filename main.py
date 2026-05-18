import os
import random
import sqlite3
from typing import Optional
from urllib.parse import urljoin
from dotenv import load_dotenv

load_dotenv()

import feedparser
import requests
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel


def resolve_db_path(env_key: str, fallback_names: list[str]) -> str | None:
    value = os.getenv(env_key)
    if value:
        return value

    for fallback_name in fallback_names:
        candidate = os.path.join(os.getcwd(), fallback_name)
        if os.path.isfile(candidate):
            return candidate

    return None


app = FastAPI(
    title="Book Coach API",
    description="Personal Calibre-Web recommendation and shelf API.",
    version="0.4.0",
    servers=[{"url": "https://bookapi.murffysplace.com"}],
)

CALIBRE_BASE_URL = os.getenv("CALIBRE_BASE_URL", "").rstrip("/")
BOOK_API_KEY = os.getenv("BOOK_API_KEY")
CALIBRE_WEB_DB = resolve_db_path(
    "CALIBRE_WEB_DB",
    ["app.db", "calibre-web.db", "db/app.db", "database/app.db"],
)
CALIBRE_LIBRARY_DB = resolve_db_path(
    "CALIBRE_LIBRARY_DB",
    ["metadata.db", "library.db", "db/metadata.db", "database/metadata.db"],
)
CALIBRE_WEB_DB_SOURCE = (
    "env" if os.getenv("CALIBRE_WEB_DB") else ("fallback" if CALIBRE_WEB_DB else "missing")
)
CALIBRE_LIBRARY_DB_SOURCE = (
    "env" if os.getenv("CALIBRE_LIBRARY_DB") else ("fallback" if CALIBRE_LIBRARY_DB else "missing")
)

READERS = {
    "peter": {
        "username": os.getenv("PETER_CALIBRE_USERNAME"),
        "password": os.getenv("PETER_CALIBRE_PASSWORD"),
        "recommend_shelf": "AI Recommended",
    },
    "pam": {
        "username": os.getenv("PAM_CALIBRE_USERNAME"),
        "password": os.getenv("PAM_CALIBRE_PASSWORD"),
        "recommend_shelf": "Pams Books",
    },
}

api_key_header = APIKeyHeader(name="x-api-key", auto_error=False)


class ShelfAddRequest(BaseModel):
    book_id: int
    shelf_name: str = "AI Recommended"


class ReaderShelfAddRequest(BaseModel):
    book_id: int
    reader: str = "peter"


def require_api_key(x_api_key: str = Depends(api_key_header)):
    if not BOOK_API_KEY or x_api_key != BOOK_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


def get_reader(reader: str):
    reader_key = reader.lower().strip()

    if reader_key not in READERS:
        raise HTTPException(status_code=400, detail=f"Unknown reader: {reader}")

    profile = READERS[reader_key]

    if not profile["username"] or not profile["password"]:
        raise HTTPException(
            status_code=500,
            detail=f"Credentials not set for reader: {reader_key}",
        )

    return reader_key, profile


def fetch_opds(path: str, reader: str = "peter"):
    if not CALIBRE_BASE_URL:
        raise HTTPException(status_code=500, detail="CALIBRE_BASE_URL not set")

    reader_key, profile = get_reader(reader)
    url = urljoin(CALIBRE_BASE_URL + "/", path.lstrip("/"))

    try:
        response = requests.get(
            url,
            auth=(profile["username"], profile["password"]),
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(
            status_code=502,
            detail=f"Calibre-Web request failed for reader '{reader_key}': {e}",
        )

    return feedparser.parse(response.text)


def fetch_books_from_feed(path: str, limit: int, reader: str = "peter"):
    feed = fetch_opds(path, reader)
    return [normalise_entry(entry) for entry in feed.entries[:limit]]


def db_connect():
    if not CALIBRE_WEB_DB:
        raise HTTPException(status_code=500, detail="CALIBRE_WEB_DB not set")

    try:
        conn = sqlite3.connect(
            f"file:{CALIBRE_WEB_DB}?mode=rw",
            uri=True,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")


def library_db_connect():
    if not CALIBRE_LIBRARY_DB:
        raise HTTPException(status_code=500, detail="CALIBRE_LIBRARY_DB not set")

    try:
        conn = sqlite3.connect(
            f"file:{CALIBRE_LIBRARY_DB}?mode=ro",
            uri=True,
            timeout=10,
        )
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, detail=f"Library database connection failed: {e}")


def extract_book_id(links):
    for link in links:
        href = link.get("href", "")
        parts = href.strip("/").split("/")

        if "download" in parts:
            idx = parts.index("download")
            if len(parts) > idx + 1:
                return parts[idx + 1]

    return None


def normalise_entry(entry):
    authors = entry.get("authors", [])
    author_names = [a.get("name") for a in authors if a.get("name")]

    links = []
    for link in entry.get("links", []):
        links.append(
            {
                "rel": link.get("rel"),
                "type": link.get("type"),
                "href": urljoin(CALIBRE_BASE_URL + "/", link.get("href", "")),
            }
        )

    return {
        "book_id": extract_book_id(links),
        "title": entry.get("title"),
        "authors": author_names,
        "summary": entry.get("summary", ""),
        "id": entry.get("id"),
        "links": links,
    }


def get_library_metadata(book_id):
    if not CALIBRE_LIBRARY_DB or not book_id:
        return {}

    try:
        book_id_int = int(book_id)
    except (TypeError, ValueError):
        return {}

    try:
        with library_db_connect() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    books.id AS book_id,
                    books.title AS title,
                    comments.text AS summary,
                    series.name AS series,
                    books.series_index AS series_index
                FROM books
                LEFT JOIN comments
                    ON comments.book = books.id
                LEFT JOIN books_series_link
                    ON books_series_link.book = books.id
                LEFT JOIN series
                    ON series.id = books_series_link.series
                WHERE books.id = ?
                LIMIT 1
                """,
                (book_id_int,),
            )

            row = cur.fetchone()

            if not row:
                return {}

            cur.execute(
                """
                SELECT authors.name
                FROM authors
                JOIN books_authors_link
                    ON books_authors_link.author = authors.id
                WHERE books_authors_link.book = ?
                ORDER BY authors.sort
                """,
                (book_id_int,),
            )
            authors = [author["name"] for author in cur.fetchall()]

            cur.execute(
                """
                SELECT tags.name
                FROM tags
                JOIN books_tags_link
                    ON books_tags_link.tag = tags.id
                WHERE books_tags_link.book = ?
                ORDER BY tags.name
                """,
                (book_id_int,),
            )
            tags = [tag["name"] for tag in cur.fetchall()]

            return {
                "series": row["series"],
                "series_index": row["series_index"],
                "is_series": bool(row["series"]),
                "tags": tags,
                "db_authors": authors,
                "db_summary": row["summary"] or "",
            }

    except HTTPException:
        return {}
    except Exception:
        return {}


def build_series_note(series, series_index):
    if not series:
        return None

    if series_index is None:
        return f"Part of the '{series}' series."

    try:
        index_value = float(series_index)
        if index_value.is_integer():
            index_display = str(int(index_value))
        else:
            index_display = str(index_value)
    except (TypeError, ValueError):
        index_display = str(series_index)

    note = f"Book {index_display} in the '{series}' series."

    try:
        if float(series_index) > 1:
            note += " This may work best if earlier books in the series have already been read."
    except (TypeError, ValueError):
        pass

    return note


def find_user_id_for_reader(reader: str):
    reader_key, profile = get_reader(reader)
    username = profile["username"]

    with db_connect() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id
            FROM user
            WHERE lower(name) = lower(?)
               OR lower(email) = lower(?)
            LIMIT 1
            """,
            (username, username),
        )

        row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Calibre-Web user not found for reader: {reader_key}",
            )

        return row["id"]


def get_shelf_by_name(shelf_name: str, reader: Optional[str] = None):
    with db_connect() as conn:
        cur = conn.cursor()

        if reader:
            user_id = find_user_id_for_reader(reader)

            cur.execute(
                """
                SELECT *
                FROM shelf
                WHERE name = ?
                  AND user_id = ?
                LIMIT 1
                """,
                (shelf_name, user_id),
            )
        else:
            cur.execute(
                """
                SELECT *
                FROM shelf
                WHERE name = ?
                LIMIT 1
                """,
                (shelf_name,),
            )

        row = cur.fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail=f"Shelf not found: {shelf_name}",
            )

        return dict(row)


def add_book_to_named_shelf(book_id: int, shelf_name: str, reader: Optional[str] = None):
    shelf = get_shelf_by_name(shelf_name, reader)
    shelf_id = shelf["id"]

    with db_connect() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT 1
            FROM book_shelf_link
            WHERE book_id = ? AND shelf = ?
            """,
            (book_id, shelf_id),
        )

        if cur.fetchone():
            return {
                "status": "already_exists",
                "book_id": book_id,
                "shelf_id": shelf_id,
                "shelf_name": shelf_name,
                "reader": reader,
            }

        cur.execute(
            """
            SELECT COALESCE(MAX("order"), 0) + 1
            FROM book_shelf_link
            WHERE shelf = ?
            """,
            (shelf_id,),
        )

        next_order = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO book_shelf_link(book_id, "order", shelf, date_added)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (book_id, next_order, shelf_id),
        )

        conn.commit()

    return {
        "status": "added",
        "book_id": book_id,
        "shelf_id": shelf_id,
        "shelf_name": shelf_name,
        "reader": reader,
    }


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "book-coach",
        "calibre": CALIBRE_BASE_URL,
        "auth": "enabled" if BOOK_API_KEY else "disabled",
        "db": "enabled" if CALIBRE_WEB_DB else "disabled",
        "library_db": "enabled" if CALIBRE_LIBRARY_DB else "disabled",
        "readers": list(READERS.keys()),
        "selection_model": "50% discover, 35% unread, 15% recent",
        "docs": "/docs",
        "openapi": "/openapi.json",
    }


@app.get("/config", dependencies=[Depends(require_api_key)])
def config():
    return {
        "calibre_base_url": CALIBRE_BASE_URL,
        "db": {
            "path": CALIBRE_WEB_DB,
            "source": CALIBRE_WEB_DB_SOURCE,
        },
        "library_db": {
            "path": CALIBRE_LIBRARY_DB,
            "source": CALIBRE_LIBRARY_DB_SOURCE,
        },
        "auth_enabled": bool(BOOK_API_KEY),
        "readers": {
            reader: {
                "recommend_shelf": profile["recommend_shelf"],
                "credentials_set": bool(profile["username"] and profile["password"]),
            }
            for reader, profile in READERS.items()
        },
    }


@app.get("/books/unread", dependencies=[Depends(require_api_key)])
def unread_books(
    reader: str = "peter",
    limit: int = Query(default=20, ge=1, le=100),
):
    feed = fetch_opds("/opds/unreadbooks", reader)
    books = [normalise_entry(entry) for entry in feed.entries[:limit]]

    return {
        "reader": reader,
        "source": "unread",
        "count": len(books),
        "books": books,
    }


@app.get("/books/random", dependencies=[Depends(require_api_key)])
def random_books(
    reader: str = "peter",
    limit: int = Query(default=20, ge=1, le=100),
):
    feed = fetch_opds("/opds/discover", reader)
    books = [normalise_entry(entry) for entry in feed.entries[:limit]]

    return {
        "reader": reader,
        "source": "random",
        "count": len(books),
        "books": books,
    }


@app.get("/books/search", dependencies=[Depends(require_api_key)])
def search_books(
    q: str = Query(..., min_length=1),
    reader: str = "peter",
    limit: int = Query(default=20, ge=1, le=100),
):
    feed = fetch_opds(f"/opds/search/{q}", reader)
    books = [normalise_entry(entry) for entry in feed.entries[:limit]]

    return {
        "reader": reader,
        "source": "search",
        "query": q,
        "count": len(books),
        "books": books,
    }


@app.get("/books/search-complete", dependencies=[Depends(require_api_key)])
def search_complete(
    q: str = Query(..., min_length=1),
    reader: str = "peter",
    limit: int = Query(default=25, ge=1, le=100),
):
    search_term = f"%{q.strip()}%"

    with library_db_connect() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT DISTINCT
                books.id AS book_id,
                books.title AS title,
                books.sort AS sort_title,
                books.timestamp AS added,
                comments.text AS summary,
                series.name AS series,
                books.series_index AS series_index
            FROM books
            LEFT JOIN comments
                ON comments.book = books.id
            LEFT JOIN books_series_link
                ON books_series_link.book = books.id
            LEFT JOIN series
                ON series.id = books_series_link.series
            LEFT JOIN books_authors_link
                ON books_authors_link.book = books.id
            LEFT JOIN authors
                ON authors.id = books_authors_link.author
            LEFT JOIN books_tags_link
                ON books_tags_link.book = books.id
            LEFT JOIN tags
                ON tags.id = books_tags_link.tag
            WHERE books.title LIKE ?
               OR authors.name LIKE ?
               OR series.name LIKE ?
               OR tags.name LIKE ?
               OR comments.text LIKE ?
            ORDER BY books.sort
            LIMIT ?
            """,
            (
                search_term,
                search_term,
                search_term,
                search_term,
                search_term,
                limit,
            ),
        )

        rows = cur.fetchall()
        results = []

        for row in rows:
            book_id = row["book_id"]

            cur.execute(
                """
                SELECT authors.name
                FROM authors
                JOIN books_authors_link
                    ON books_authors_link.author = authors.id
                WHERE books_authors_link.book = ?
                ORDER BY authors.sort
                """,
                (book_id,),
            )
            authors = [author["name"] for author in cur.fetchall()]

            cur.execute(
                """
                SELECT tags.name
                FROM tags
                JOIN books_tags_link
                    ON books_tags_link.tag = tags.id
                WHERE books_tags_link.book = ?
                ORDER BY tags.name
                """,
                (book_id,),
            )
            tags = [tag["name"] for tag in cur.fetchall()]

            series_note = build_series_note(row["series"], row["series_index"])

            results.append(
                {
                    "reader": reader,
                    "book_id": book_id,
                    "title": row["title"],
                    "authors": authors,
                    "series": row["series"],
                    "series_index": row["series_index"],
                    "is_series": bool(row["series"]),
                    "series_note": series_note,
                    "tags": tags,
                    "summary": row["summary"] or "",
                    "cover": f"{CALIBRE_BASE_URL}/opds/cover/{book_id}",
                    "download_epub": f"{CALIBRE_BASE_URL}/opds/download/{book_id}/epub/",
                    "download_kepub": f"{CALIBRE_BASE_URL}/opds/download/{book_id}/kepub/",
                }
            )

    return {
        "reader": reader,
        "source": "calibre_metadata_db",
        "query": q,
        "count": len(results),
        "books": results,
    }


@app.get("/books/recommend", dependencies=[Depends(require_api_key)])
def recommend_books(
    mood: str = "general",
    reader: str = "peter",
    limit: int = Query(default=10, ge=1, le=50),
):
    feed = fetch_opds("/opds/unreadbooks", reader)
    books = [normalise_entry(entry) for entry in feed.entries[:limit]]

    return {
        "reader": reader,
        "mood": mood,
        "note": "Basic candidate list only. AI selection comes from ChatGPT using this metadata.",
        "count": len(books),
        "books": books,
    }


@app.get("/books/recommend-ai", dependencies=[Depends(require_api_key)])
def recommend_ai(
    mood: str = "general",
    reader: str = "peter",
    limit: int = Query(default=5, ge=1, le=20),
    pool: int = Query(default=300, ge=50, le=1000),
):
    discover_count = int(pool * 0.50)
    unread_count = int(pool * 0.35)
    recent_count = pool - discover_count - unread_count

    combined = []
    combined.extend(fetch_books_from_feed("/opds/discover", discover_count, reader))
    combined.extend(fetch_books_from_feed("/opds/unreadbooks", unread_count, reader))
    combined.extend(fetch_books_from_feed("/opds/new", recent_count, reader))

    seen = set()
    books = []

    for book in combined:
        key = book.get("book_id") or book.get("id") or book.get("title")

        if key in seen:
            continue

        seen.add(key)
        books.append(book)

    random.shuffle(books)
    selected = books[:limit]

    recommendations = []

    for book in selected:
        metadata = get_library_metadata(book.get("book_id"))

        series = metadata.get("series")
        series_index = metadata.get("series_index")
        series_note = build_series_note(series, series_index)

        reason = (
            f"Candidate for a '{mood}' reading mood. "
            "Final judgement should be made by ChatGPT using the summary, author, and reader preferences."
        )

        if series_note:
            reason += f" {series_note}"

        recommendations.append(
            {
                "book_id": book["book_id"],
                "title": book["title"],
                "authors": book["authors"] or metadata.get("db_authors", []),
                "summary": (book["summary"] or metadata.get("db_summary", ""))[:500],
                "series": series,
                "series_index": series_index,
                "is_series": bool(series),
                "series_note": series_note,
                "tags": metadata.get("tags", []),
                "reason": reason,
                "links": book["links"],
            }
        )

    return {
        "reader": reader,
        "mood": mood,
        "source": "blended",
        "selection_model": "50% discover, 35% unread, 15% recent",
        "pool_requested": pool,
        "pool_size": len(books),
        "count": len(recommendations),
        "mix": {
            "discover": discover_count,
            "unread": unread_count,
            "recent": recent_count,
        },
        "recommendations": recommendations,
    }


@app.get("/shelves", dependencies=[Depends(require_api_key)])
def list_shelves():
    with db_connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM shelf ORDER BY name")
        shelves = [dict(row) for row in cur.fetchall()]

    return {
        "count": len(shelves),
        "shelves": shelves,
    }


@app.post(
    "/shelves/add-book",
    dependencies=[Depends(require_api_key)],
    include_in_schema=False,
)
def add_book_to_shelf(request: ShelfAddRequest):
    return add_book_to_named_shelf(
        book_id=request.book_id,
        shelf_name=request.shelf_name,
    )


@app.post("/shelves/add-book-for-reader", dependencies=[Depends(require_api_key)])
def add_book_for_reader(request: ReaderShelfAddRequest):
    reader_key, profile = get_reader(request.reader)

    return add_book_to_named_shelf(
        book_id=request.book_id,
        shelf_name=profile["recommend_shelf"],
        reader=reader_key,
    )
