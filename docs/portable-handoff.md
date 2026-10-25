# Dedicated native file-portability case

This case is separate from the f1 Core adapter 36-tool-call/4-discovery result.
The production adapter, saved-handle registry and original CI workflow are
unchanged. It adds no generic command endpoint or cross-session adapter import.

The fixed original procedural source is 21,911 bytes with SHA-256
`00ea011f98e63f9ecd325da87c4ad8de567bbd58539db0924edcef6b4129f5a5`.
The template is the real f1 schema-15 save with exactly one JSON field replaced:
`/project/items/1/kind/Media/media/File/path` becomes `media/source.mp4`.
Every other JSON field and the media bytes are retained; a semantic fingerprint
also binds the entire project graph after normalizing only that resource field.
The template alone is unqualified. Its manifest and attribution are next to it.

The opt-in Linux x86_64 workflow verifies the already qualified official 0.12
archive/CLI pin. An exclusive owned Process A opens the relative template using
official MCP and saves a new project. It must be clean with no outstanding jobs.
After confirming A exited, the exact saved bytes and media are copied to B and
the old A root is renamed to a direct owned isolation sibling. A new owned
Process B runs with a third, empty cwd. It opens B using the absolute document
path; neither A nor the process cwd can supply `media/source.mp4`. Official
`file.open.missingMedia` must be strict integer zero; `media.findMissing.missing`
must be an empty array.
B then officially saves a new file and exports H264/AAC and WAV. Every resource
hash and the original independent 12-to-24-frame, MAE<18, 1.95–2.1-second,
200–240 Hz and RMS>0.02 oracles must pass. No unknown operation is replayed.

`docs/source-guided-plan-amendment.md` records an upstream 0.12 status diagnostic
limitation before execution. Full raw `media.status` is retained separately;
`diagnostic_status_consistent=false` must never be called comprehensive API
health or “status online”. Neither cwd nor aliases are changed to make it pass.
The local draft issue is not submitted to upstream without native evidence.

Public SDK initialize/list/tool attempts, each engine-command dispatch, actual
retained Process PIDs/exit states, runtime identity and verified CLI hash are
recorded. SDK notifications and vendor-private RPC are not inferred. Core adapter
calls are zero in this operator-owned official-MCP case.

Only successful relative project/media, exports, attribution/component licenses
and a whitelisted path-free summary enter `user-facing/` and its ZIP. Raw CI
paths, stderr, ffprobe input filenames, process config and native diagnostics stay
under `internal/`. No vendor executable/model/font or old Library snapshot enters
the user bundle. The test does not demonstrate GUI/full installation, another
runtime, generic arbitrary project import or a promotional film.

Local verification is restricted to ordinary policy tests and explicit Python
fixture children. Run the vendor case only in its dedicated qualified Linux job:

```sh
python tests/native_portability.py --native-cli runtime/filmcraft-cli \
  --output evidence/portable-handoff --adapter-source-commit "$EXACT_HEAD"
```

## 中文范围

本case只验证官方MCP文件便携，不是adapter跨session导入。模板仅替换真实f1工程的
唯一素材路径，其他字段与原素材哈希不变；离线模板不算通过。必须A官方打开保存、
退出并隔离旧目录，B使用不同空cwd的新自有进程，官方open/findMissing无缺失，再
保存和导出，原画音阈值全部保留。完整status诊断单列，若相对路径误报missing，
不能称API全健康，也不能改cwd/创建别名绕过。逐资产哈希和无实际执行根路径扫描
通过后，才生成新的user-facing副本；原f1证据/旧Library不改。GUI、完整安装、
通用工程导入、未知结果恢复、其他运行时均未由此验证。

## Executed harness schema correction (first e399 qualification)

The first native run, commit `e3990ab41a19ad9472f8f06bf9ca3bd6f9125191`,
completed official `file.open` successfully with `missingMedia: 0` and
`isError: false`. The harness incorrectly expected an empty array and stopped
before B. A's owned child PID 3442 exited with code 0 and no cleanup error. Its
original failed check, full response and log are retained; no uncertain
mutation is replayed.

Exact 0.12 `relink.rs:740-752` defines `on_open -> usize` and returns `list.len()`;
`commands.rs:4417-4418` serializes that count. The corrected gate is therefore
strict integer zero, rejecting booleans, floats, arrays, nonzero and absent
values. The earlier plan's `missingMedia == []` was a wire-shape error, not an
acceptable alternative. `media.findMissing` still requires `{missing: []}`
(`relink.rs:615-617`). This correction is explicitly after execution and does
not rewrite the earlier pre-execution status-diagnostic amendment.

The remaining wire shapes were checked against exact source: `media.status` is
an array; `jobs.list` is an array, `Job::to_json.finished` means a result exists
and successful results are objects (`engine/lib.rs:497-510`); export dispatch
returns an integer job (`export_tools.rs:535-548`) and its terminal record has an
`offlineMedia` array (`export_tools.rs:479-500,621-632`). Terminal export now
also explicitly requires that array to be empty. All source/template/asset
hashes, A isolation, B's unrelated cwd, status separation and original decoded
video/audio thresholds remain unchanged.

首轮执行后的窄修：官方 open 返回的是缺失数量 int0，原 harness 错按空数组判断。
原失败证据及旧期望保留；仅改为严格整数0，findMissing仍要求空数组，并显式要求
terminal export 的 offlineMedia=[]。这不是厂商权限/资源拒绝，也不是执行后删除
画音检查。第二轮必须全新自有A→B，不重放已关闭的原进程操作。

## Executed delivery-copy protocol correction (6db4 qualification)

The next run, head `6db4d091de13b081756378ff58ef8b547b684b57`, passed A's
official zero-missing open, findMissing, raw-status shape and clean readback.
`file.saveAs` completed a 5,612-byte write, then the full-project semantic hash
failed. A PID 3656 exited 0 with no cleanup error; B never started. The actual
saved bytes were not retained in that artifact. The size difference matches the
known rename behavior, but it is not evidence that only two fields changed.

Exact `commands.rs:4334-4345` intentionally renames `project.name` and the root
bin name from the new file stem when `adopt=true`, before encoding. The reviewed
fixture names are `mcp-project`; the A/B target basenames differ. Official
`file.saveCopy` (`commands.rs:1501-1503`) calls the same writer with `adopt=false`
and bypasses that rename. Delivery now uses this copy command while retaining
the exact same target paths, entire project hash, fixture/source bytes,
isolation/cwd/status gates and original decoded thresholds. No label field is
excluded or normalized to make the semantic hash pass. The mutation is a fresh
owned A/B run, not replay of the closed prior process.

Each new owned saved project is read with the existing bounded/no-follow
descriptor guard and its exact bytes retained as internal
`A.saved-project.unadmitted.bin` / `B.saved-project.unadmitted.bin` before model
admission. Collection errors are secondary and never hide the model's primary
failure. A failed model never returns bytes for B or user publication; these
diagnostic files never enter the user-facing bundle. Successfully admitted B
bytes are retained in memory for the final user copy.

第二轮执行后的协议修正：SaveAs 本来就会按新文件名重命名工程及根bin，故与本任务
保留全图字段冲突。改用官方 SaveCopy(adopt=false)，目录/文件名和全图hash不变，
不放松画音门槛。原saved bytes未留，不能断言只有两字段变化；原失败完整保留。
新输出先保留有界FD快照到internal-only，未admitted绝不送入B或用户包。
