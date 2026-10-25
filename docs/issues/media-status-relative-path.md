# Draft only: media.status and document-relative media in FilmCraft 0.12

Status: local source-guided draft, not submitted upstream. Native reproduction
is pending the dedicated file-portability CI case.

For a saved `B/project.fcproj` containing `media/source.mp4`, with B's process cwd
at a third empty directory, `doc_path::resolve` takes the media from B. However,
`relink.rs:586` checks the stored relative string directly through
`FsServices::file_size` (`engine/lib.rs:187-190`), which uses process cwd. This
can report `missing` despite `file.open`/`media.findMissing` and rendering
resolving the document-relative resource. Proxy status uses a similar raw check.

Exact source: `274c4cf85ba638d4b6f867d97ca3f6478a993c8d`.
Expected diagnostics: status agrees with the same resource resolution used by
open/render. Proposed upstream design for later discussion: resolve the stored
reference through the media pool/document boundary before file-size diagnostics;
preserve refusal/missing/offline/unreadable distinctions and add an unrelated-cwd
regression. No vendor code is patched here.

Retain raw native evidence before converting this draft into a confirmed issue.
