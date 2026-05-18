Book Coach API

Personal Calibre-Web recommendation and shelf API.

Designed for use with custom ChatGPT GPTs and ChatGPT Actions.

The API provides:

* mood-based recommendations
* full library metadata search
* reader-aware shelves
* multi-user support
* Kobo-friendly workflows
* series-aware recommendations

⸻

Setup

Create and activate the virtual environment

python3 -m venv venv
source venv/bin/activate

Install dependencies

pip install -r requirements.txt

Create .env

Copy .env from the example values and set your own credentials and paths.

⸻

Required .env settings

CALIBRE_READERS=peter,pam
PETER_CALIBRE_USERNAME=
PETER_CALIBRE_PASSWORD=
PETER_RECOMMEND_SHELF=AI Recommended
PAM_CALIBRE_USERNAME=
PAM_CALIBRE_PASSWORD=
PAM_RECOMMEND_SHELF=Pams Books
CALIBRE_BASE_URL=
BOOK_API_KEY=
CALIBRE_WEB_DB=
CALIBRE_LIBRARY_DB=

You can replace peter and pam with any reader keys you want.

Example:

CALIBRE_READERS=alice,bob
ALICE_CALIBRE_USERNAME=
ALICE_CALIBRE_PASSWORD=
ALICE_RECOMMEND_SHELF=Alice Books
BOB_CALIBRE_USERNAME=
BOB_CALIBRE_PASSWORD=
BOB_RECOMMEND_SHELF=Bob Books

⸻

Reader Notes

* CALIBRE_READERS defines the available reader keys.
* If CALIBRE_READERS is omitted, defaults are peter,pam.
* For each reader key the API loads:
    * ${READER}_CALIBRE_USERNAME
    * ${READER}_CALIBRE_PASSWORD
    * ${READER}_RECOMMEND_SHELF
* The reader query parameter defaults to the first reader listed.

⸻

Database Notes

CALIBRE_WEB_DB

Used for:

* shelves
* user accounts
* Kobo sync information
* Calibre-Web internal state

Example:

CALIBRE_WEB_DB=/data/calibre-web-app.db

CALIBRE_LIBRARY_DB

Used for:

* full metadata search
* series information
* tags
* authors
* descriptions/comments

Example:

CALIBRE_LIBRARY_DB=/data/calibre-library-metadata.db

⸻

Docker Example

services:
  book-coach:
    build: .
    container_name: book-coach
    ports:
      - "8095:8095"
    volumes:
      - /mnt/user/appdata/calibre-web-automated/app.db:/data/calibre-web-app.db
      - /mnt/user/appdata/calibre-web-automated/app.db-wal:/data/calibre-web-app.db-wal
      - /mnt/user/appdata/calibre-web-automated/app.db-shm:/data/calibre-web-app.db-shm
      - /mnt/user/media/ebooks/metadata.db:/data/calibre-library-metadata.db:ro
    env_file:
      - .env
    restart: unless-stopped

⸻

Running the App

uvicorn main:app --reload --host 0.0.0.0 --port 8095

API docs:

http://127.0.0.1:8095/docs

OpenAPI schema:

http://127.0.0.1:8095/openapi.json

⸻

Using with Custom ChatGPT GPTs

Create a Custom GPT

1. Open ChatGPT.
2. Go to Explore GPTs.
3. Click Create.
4. Open the Configure tab.

⸻

Add the API as an Action

Under Actions:

1. Click Create new action.
2. Import from URL:

https://your-api-domain/openapi.json

Example:

https://bookapi.example.com/openapi.json

The GPT will automatically load the available endpoints.

⸻

Authentication

Use:

API Key

Header name:

x-api-key

Paste the same value used for:

BOOK_API_KEY=

⸻

Example GPT Instructions

This GPT acts as a thoughtful literary companion.
Always use reader=peter when calling the Book Coach API.
For mood-based recommendations, use:
/books/recommend-ai
For deliberate searches such as:
- “do I own”
- “find books about”
- “books by”
- “search for”
use:
/books/search-complete
When adding books to shelves, use:
/shelves/add-book-for-reader
Avoid recommending later books in a series without warning the user.
If a book is part of a series, mention the series name and book number.

⸻

Multi-Reader Support

The API supports multiple readers using separate Calibre-Web accounts.

Each reader can have:

* their own shelves
* recommendation targets
* Kobo sync workflow
* personalised GPT instructions

Example:

reader=peter
reader=pam

This allows multiple GPTs to share the same library while maintaining separate recommendation flows and shelves.

⸻

Available Endpoints

Mood-Based Recommendations

/books/recommend-ai?reader=peter&mood=quiet&limit=5

⸻

Full Metadata Search

/books/search-complete?q=moscow&reader=peter

Searches:

* titles
* authors
* tags
* series
* descriptions/comments

⸻

Add a Book to Reader Shelf

POST /shelves/add-book-for-reader

Payload:

{
  "reader": "peter",
  "book_id": 1234
}

⸻

Series Awareness

Recommendations include:

* series name
* book number in series
* warnings for mid-series books

Example:

Book 3 in the 'Three Pines' series.
This may work best if earlier books have already been read.

⸻

Reverse Proxy Example (Caddy)

bookapi.example.com {
    reverse_proxy 192.168.1.100:8095
}

HTTPS is strongly recommended because ChatGPT Actions require a public HTTPS endpoint.

⸻

Suggested Architecture

Unraid
├── Calibre-Web Automated
├── ebook library
├── metadata.db
└── storage
Proxmox VM
├── Book Coach API
├── Running Coach API
└── future lightweight helper APIs

This keeps storage-heavy services separate from lightweight Python APIs.

⸻

Important Notes

* Use HTTPS.
* Keep API keys private.
* SQLite databases should preferably be mounted read-only where possible.
* The API is designed as a lightweight personal library assistant rather than a public multi-tenant service.
* Custom GPT behaviour is heavily influenced by the system instructions used in the GPT configuration.

⸻

Current Features

* mood-based recommendations
* multi-reader support
* reader-aware shelves
* full metadata search
* OPDS integration
* Calibre database integration
* series-aware recommendation metadata
* Kobo-friendly workflows

⸻

Future Ideas

* library statistics endpoint
* author endpoints
* series completion tracking
* recommendation constraints
* duplicate metadata detection
* recent additions endpoint
* advanced tag filtering
* optional reading-state tracking