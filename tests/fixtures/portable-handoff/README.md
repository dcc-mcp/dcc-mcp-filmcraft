# Original portable-handoff fixture

`source.mp4` is the unchanged 21,911-byte original FFmpeg testsrc2/sine input from the f1e8e010 acceptance, not a vendor binary. SHA-256 and recipe are in manifest.json. The source project is the real schema-15 save; this candidate changes only its single actual media reference to `media/source.mp4`, preserving all other JSON fields. The offline candidate alone proves no portability. A real official CLI must open/save it in A, exit, then a new CLI in another cwd must open/save/export its relocated B copy.

Asset attribution and adapter MIT license apply separately from official FilmCraft MIT/Apache/NOTICE and third-party codec/font/trademark terms. No vendor software is included.
