# File portability acceptance: pre-execution plan amendment

This amendment is recorded before any new vendor/native execution. It does not
remove a failed native check or change the original image/audio oracles.

The initial plan expected `media.status` to report `online` in B. Exact official
FilmCraft 0.12 source commit `274c4cf85ba638d4b6f867d97ca3f6478a993c8d`
shows a separate diagnostic path:

- `crates/engine/src/relink.rs:576-603` calls
  `s.services.file_size(stored_path)` at line 586.
- `crates/engine/src/lib.rs:161-190` implements `FsServices::file_size` with
  `std::fs::metadata(path)`, without the document directory. The default session
  uses `FsServices` (lines 515-519).
- `MediaPool::follow` and `doc_path::resolve` instead resolve stored relative
  references from the project document folder. `doc_path.rs:37-62` explicitly
  tests that contract. Official `file.open` and `media.findMissing` use this path.

Therefore a B process whose cwd differs from B's document folder may correctly
read/render relative media while `media.status` reports `missing`. This is a
source-confirmed possibility, not yet a claimed native reproduction. The case
preserves the complete raw result and reports `diagnostic_status_consistent`.
False must never be described as comprehensive API health or “status online”.

The mandatory file-portability gates remain: A exited and its old path is
unavailable; B is a new owned process in a third, alias-free cwd; official
`file.open.missingMedia == []`; official `media.findMissing.missing == []`;
every resource has its exact original hash; all original independent decoded
video/audio oracles pass. Changing B's cwd, creating a relative-path alias,
relaxing an adapter state gate, replaying an unknown mutation or changing an
endpoint after a guard/permission refusal is prohibited.

This qualifies a closed official-MCP file handoff only. Adapter cross-session
bundle import, GUI, other runtimes and comprehensive API health are unqualified.

执行前修订：保留原先 `media.status=online` 期望及其源码差异，不在执行后删除
失败检查。新门槛仍要求 A 退出隔离、B 不同 cwd、新自有进程、官方 open/findMissing
无缺失、逐资产哈希及全部原画音阈值。原始 status 完整记录；若不一致必须明确诊断
限制，不能称 API 全面健康，也不能通过改 cwd／别名绕过。未实际运行厂商程序时，
只保留本地问题草稿，不向官方维护者发帖。
