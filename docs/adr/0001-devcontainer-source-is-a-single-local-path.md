# Devcontainer source is a single `local_path`, not a generic source descriptor

A Devcontainer's origin is stored as one `local_path` column. We deliberately rejected the generic `source_type` / `source_value` pair, even though Git-URL sources are a plausible future feature — that feature is an explicit MVP non-goal, the API already speaks `local_path`, and the generic shape only added a translation layer with no caller. A future reader who expects the generic descriptor should know its removal was intentional (Simplicity First); re-introducing it is a single additive SQLite migration if Git URLs ever land.

Status: accepted
