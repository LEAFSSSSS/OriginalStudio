# Original Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Independently implement the approved local asset search and organization workspace in `G:/Material/OriginalStudio`.

**Architecture:** FastAPI serves a native ES module interface and coordinates separate storage, indexing, search, and model adapters. SQLite persists assets, annotations, text segments, vectors, and recoverable jobs. Heavy inference libraries are imported only when requested.

**Tech Stack:** Python 3.11+, FastAPI, Uvicorn, SQLite FTS5, Pillow, pypdf; optional Torch/Transformers/OpenCV/faster-whisper; native HTML/CSS/JavaScript.

## Task 1: Contract, persistence and local API

Files: `originalstudio/settings.py`, `originalstudio/storage.py`, `originalstudio/schemas.py`, `originalstudio/api.py`, `tests/test_workspace.py`, `docs/api.md`.

- [x] Define request and response shapes in `docs/api.md`, including roots, assets, searches, collections, persistent jobs and capability status.
- [x] Write behavior tests for source directory registration, Chinese filename search, metadata persistence, scope isolation and mutation validation. Run `python -m unittest discover -s tests -v` and observe failures before implementing these routes.
- [x] Create settings with `data_dir: Path`, `host: str = '127.0.0.1'`, `port: int = 8090`; initialize SQLite using `PRAGMA foreign_keys=ON`, `PRAGMA journal_mode=WAL`, `PRAGMA user_version=2`.
- [x] Implement `create_app(settings: Settings | None = None) -> FastAPI`; expose JSON errors as `{"error": {"code": "...", "message": "..."}}`. Reject invalid scopes and return 404 for unknown asset IDs.
- [x] Serve files only after `Path(asset['path']).resolve().is_relative_to(Path(root['path']).resolve())`; require same-origin requests and a per-process session token for mutations.

## Task 2: Extraction and recoverable indexing

Files: `originalstudio/documents.py`, `originalstudio/media.py`, `originalstudio/jobs.py`, `originalstudio/engines.py`, `tests/test_recovery.py`.

- [x] Create temporary TXT, subtitle, DOCX, PNG and MP4 fixtures; assert extracted text positions, video frame times, incremental behavior and cancellation.
- [x] Implement text decoding and safe XML/ZIP extraction, optional PDF page extraction, EXIF-aware thumbnails, and video probing/sampling using lazy OpenCV imports.
- [x] Persist `jobs` and `job_items`, check cancellation between files/frames, convert unfinished running jobs to interrupted at startup, and allow explicit resume and retry.
- [x] Implement `VisionEngine.encode_text(text)` and `VisionEngine.encode_image(image)` with normalized vectors and a stored model signature. Implement lazy local Whisper transcription to timestamped segments. Do not load models during application startup.

## Task 3: Search and organization

Files: `originalstudio/search.py`, `originalstudio/repository.py`, `originalstudio/api.py`, `tests/test_workspace.py`, `tests/test_recovery.py`.

- [x] Test Chinese substring and multi-term text matches, combined type/date/folder/tag filters, reference upload validation, collection membership and UTF-8 BOM CSV export.
- [x] Implement trigram MATCH for longer terms and escaped LIKE for short terms; rank document/transcript matches and include context with page/time positions.
- [x] Compute semantic scores from matching model vectors, group neighboring video frame hits into clips, and return total/pagination independently of result slicing.
- [x] Persist favorites, normalized tags, notes and collection membership by stable asset ID. Export only explicitly selected collection metadata. Back up SQLite with its backup API.

## Task 4: Original interface

Files: `static/index.html`, `static/styles.css`, `static/app.js`, `static/api.js`, `static/render.js`, `static/icons.js`, `static/favicon.svg`.

- [x] Implement the `docs/api.md` contract in a new interface using dark navigation, warm light work area and emerald accents. Use no legacy frontend assets or external CDN.
- [x] Complete directory setup, five search modes, grid/list results, preview drawer, bulk actions, editable collection navigation, job progress/failures/resume and capability guidance.
- [x] Add form validation, text-safe rendering, request cancellation/stale-result guards, modal focus behavior, keyboard shortcuts and responsive layout.
- [x] Check JavaScript syntax with `node --check`, then verify real browser flows against the new server with isolated fixtures.

## Task 5: Delivery and verification

Files: `README.md`, `requirements.txt`, `requirements-ai.txt`, `requirements-dev.txt`, `install.bat`, `install-ai.bat`, `run.bat`, `run.py`, `build_windows.ps1`, `OriginalStudio.spec`, `THIRD_PARTY_NOTICES.md`, `.gitignore`, `.env.example`.

- [x] Provide isolated virtual environment installation, optional CPU AI installation, browser launch, loopback server and an optional Windows packaging path.
- [x] Document exact commands for indexing, model selection, offline operation, restoring data and video export dependencies.
- [x] Run isolated API/indexing tests, frontend syntax checks and browser flows. Verify a real image/text model on synthetic files if locally available.
- [x] Perform independent spec review followed by code quality review, resolve findings, and record actual verification results and limitations in `docs/verification.md`.

The directory is new and its parent has no Git metadata. The approved source directory itself provides isolation; no worktree or source commit is required for this delivery.
