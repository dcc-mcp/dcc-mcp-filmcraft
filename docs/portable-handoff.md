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
`file.open.missingMedia` and `media.findMissing.missing` must both be empty.
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
