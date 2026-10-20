# Original Studio API contract

Base URL: `http://127.0.0.1:8090`. All objects use snake_case. Date fields are UTC ISO strings. IDs are integers unless specified. Errors are `{ "error": { "code": "...", "message": "中文说明" } }`. Validation errors use HTTP 422. Missing optional engines use HTTP 503. The UI uses same-origin requests.

## Session and status

- `GET /api/session` -> `{token, version, name}`. Keep token in memory and send `X-Studio-Token` for POST/PATCH/DELETE. This response is not cacheable.
- `GET /api/status` -> `{version, roots:[], stats:{total,image,video,document,favorites}, active_jobs:[], capabilities:{visual:{installed,loaded,model,message},transcripts:{installed,loaded,model,message},video:{installed,message},pdf:{installed,message},export:{installed,message}}, data_dir}`.
- `GET /api/roots` -> `{items:[{id,name,path,available,asset_count}],total}`.
- `POST /api/roots` body `{path,name?}` -> root object. Path must be an existing absolute directory. Nested/duplicate roots are rejected.
- `DELETE /api/roots/{id}` -> `{ok:true}` removes registration and its index only.
- `POST /api/folders/list` body `{path?:string}` -> `{path:string|null,parent:string|null,items:[{name,path}],truncated:boolean}`. Empty path lists local drives; an absolute directory lists its subfolders (maximum 1000). The UI browses in the connection dialog and copies the chosen directory into the path field. `parent:""` returns to the drive list; `parent:null` means already at the virtual drive list. Requires the session token, like other POST requests.
- `POST /api/folders/pick` is retired and returns 409 `picker_updated`, asking a cached older page to reload. It no longer launches a desktop process.

## Assets and search

- `GET /api/assets` parameters `root_id?`, `kind?` (`image|video|document`), `q?`, `favorite?` (boolean), `collection_id?`, `tag?`, `folder?`, `date_from?`, `date_to?`, `sort?` (`recent|name|oldest`), `page=1`, `page_size=36` -> `{items:[Asset],total,page,page_size}`.
- `POST /api/search` JSON `{mode:'filename'|'semantic'|'reference'|'document'|'dialogue',query:'',reference_id?:string,root_id?:int,kind?:string,negative_query?:string,min_score?:number,folder?:string,date_from?:'YYYY-MM-DD',date_to?:'YYYY-MM-DD',tag?:string,favorite?:bool,collection_id?:int,page?:int,page_size?:int}` -> same paged response plus `{elapsed_ms,mode}`. Scores are cosine similarity times 100, not a probability. File mode may use an empty query to browse. Other text modes require a query; reference mode requires reference_id.
- `POST /api/references` multipart field `file` -> `{id,url,name}`. Maximum 16 MiB, decode and reencode raster; `id` is a UUID string.
- `GET /api/references/{id}` -> processed reference image.
- `GET /api/assets/{id}` -> Asset with metadata and text/transcript segments `segments:[{id,kind,text,page,start,end}]`.
- `GET /api/assets/{id}/thumbnail` -> JPEG/PNG. Videos have a representative thumbnail; documents use UI icons.
- `GET /api/assets/{id}/media?download=false` -> source content with HTTP range support. Source must still resolve inside its root. Documents always download to avoid active content execution.
- `PATCH /api/assets/{id}` body partial `{favorite?:bool,tags?:string[],notes?:string,collection_ids?:int[]}` -> updated Asset.
- `POST /api/assets/batch` body `{ids:int[],favorite?:bool,add_tags?:string[],remove_tags?:string[],collection_id?:int,remove_collection?:bool}` -> `{updated:int}`. Maximum 300 assets. Atomic validation.
- `POST /api/assets/{id}/reveal` body `{}` -> `{ok:true}` opens the OS file location.
- `POST /api/assets/{id}/clip` body `{start:number,end:number}` -> `{url,name}`; uses FFmpeg with argument arrays, max 1 hour; output is in application exports directory.

Asset fields: `{id,root_id,name,path,kind,extension,bytes,width,height,duration,modified_at,available,favorite,tags:[],notes,collection_ids:[],thumbnail_url,media_url,visual_state,text_state,transcript_state,error,score?:number,excerpt?:string,location?:{page?:int,start?:number,end?:number}}`. A state is `pending|ready|failed|skipped`; unavailable assets remain editable.

## Collections

- `GET /api/collections` -> `{items:[{id,name,color,item_count,created_at}],total}`.
- `POST /api/collections` body `{name,color?:'#RRGGBB'}` -> collection.
- `PATCH /api/collections/{id}` body `{name?,color?}` -> collection.
- `DELETE /api/collections/{id}` -> `{ok:true}`.
- `GET /api/collections/{id}/export.csv` -> UTF-8 BOM CSV containing filename, kind, path, available, tags, notes, collected_at. Neutralize spreadsheet formula prefixes in cells.

## Jobs

- `GET /api/jobs?limit=20` -> `{items:[Job],total}`.
- `POST /api/jobs` body `{root_id:int,operation:'scan'|'visual'|'documents'|'transcripts'|'cleanup',retry_failed?:bool}` -> Job (202).
- `GET /api/jobs/{id}` -> Job with `failures:[{path,code,message}]` (latest 100).
- `POST /api/jobs/{id}/stop` body `{}` -> Job.
- `POST /api/jobs/{id}/resume` body `{}` -> Job. May continue stopped/interrupted/failed jobs; completed jobs can retry failures through retry_failed.

Job fields: `{id,root_id,root_name,operation,status,stage,total,done,skipped,failed,current_path,error,created_at,updated_at,finished_at,progress}`. Status: `queued|running|stopping|stopped|completed|failed|interrupted`. Discovering has total=0 and progress=null. The queue executes one job at a time and persists per-file outcomes.

- `POST /api/backups` body `{}` -> `{name,url,created_at}` creates a consistent SQLite backup.
- `GET /api/backups/{name}` -> generated backup file; names are server-generated and path-checked.
- `GET /api/exports/{name}` -> generated clip file; names are server-generated and path-checked.
