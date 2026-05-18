# Book Coach API

Personal Calibre-Web recommendation and shelf API.

## Setup

1. Create and activate the virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env` from the example values and set your own credentials and paths.

## Required `.env` settings

Create a `.env` file in the project root with the following values:

```env
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
```

### Notes

- `CALIBRE_READERS` defines the reader keys used by the API.
- If `CALIBRE_READERS` is omitted, the default readers are `peter,pam`.
- For each reader key, the app loads `${READER}_CALIBRE_USERNAME`, `${READER}_CALIBRE_PASSWORD`, and optionally `${READER}_RECOMMEND_SHELF`.
- The `reader` query parameter in endpoints defaults to the first reader listed in `CALIBRE_READERS`.
- `CALIBRE_BASE_URL` should point to your Calibre-Web instance, for example `https://books.example.com`.
- `BOOK_API_KEY` is used to protect API endpoints.
- `CALIBRE_WEB_DB` and `CALIBRE_LIBRARY_DB` may be omitted if local fallback database files are present.
- The app will automatically attempt to resolve fallback database files in the project root if the `.env` variables are not set.

### Fallback database filenames

If `CALIBRE_WEB_DB` is unset, the app will look for:

- `app.db`
- `calibre-web.db`
- `db/app.db`
- `database/app.db`

If `CALIBRE_LIBRARY_DB` is unset, the app will look for:

- `metadata.db`
- `library.db`
- `db/metadata.db`
- `database/metadata.db`

## Running the app

```bash
uvicorn main:app --reload
```

The API docs are available at `http://127.0.0.1:8000/docs`.

## Git

Add `.env`, `venv`, and local caches to `.gitignore` before pushing to Git.

## Notes

- The app currently supports automatic fallback discovery for local database files.
- Use `.env` for production configuration and keep sensitive values out of version control.
