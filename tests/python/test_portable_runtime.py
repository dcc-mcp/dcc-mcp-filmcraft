"""Synthetic-only TAR regression; no real vendor archive or binary is written."""

import hashlib
import importlib.util
import io
import os
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("portable_runtime_extractor", ROOT / "tests/portable_runtime.py")
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
SYNTHETIC = b"clearly synthetic offline fixture; never a vendor executable\n"


def bundle(*, name=runtime.MEMBER, kind=tarfile.REGTYPE, duplicate=False, payload=SYNTHETIC):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for _ in range(2 if duplicate else 1):
            item = tarfile.TarInfo(name)
            item.type = kind
            item.linkname = "outside" if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE) else ""
            item.size = len(payload) if kind == tarfile.REGTYPE else 0
            archive.addfile(item, io.BytesIO(payload) if item.size else None)
    return buffer.getvalue()


def verify(raw, **kwargs):
    return runtime.verify_tar(
        raw, archive_sha=hashlib.sha256(raw).hexdigest(), cli_sha=hashlib.sha256(SYNTHETIC).hexdigest(), **kwargs
    )


def test_synthetic_exact_member_and_two_hashes():
    raw = bundle()
    assert verify(raw) == SYNTHETIC
    with pytest.raises(ValueError, match="archive SHA"):
        runtime.verify_tar(raw)
    with pytest.raises(ValueError, match="extracted CLI SHA"):
        runtime.verify_tar(raw, archive_sha=hashlib.sha256(raw).hexdigest(), cli_sha="0" * 64)


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.DIRTYPE, tarfile.FIFOTYPE])
def test_selected_member_refuses_links_and_nonregular_types(kind):
    with pytest.raises(ValueError, match="ordinary CLI archive member"):
        verify(bundle(kind=kind))


@pytest.mark.parametrize("name", ["other/filmcraft-cli", "../" + runtime.MEMBER, "/" + runtime.MEMBER])
def test_only_exact_release_member_is_accepted(name):
    with pytest.raises(ValueError, match="occur once"):
        verify(bundle(name=name))


def test_duplicate_and_size_budgets_are_rejected():
    with pytest.raises(ValueError, match="occur once"):
        verify(bundle(duplicate=True))
    with pytest.raises(ValueError, match="archive SHA"):
        verify(bundle(), max_bytes=1)
    # An easily compressed synthetic payload can exceed the member budget even
    # when its archive does not; this probes the extracted-size gate separately.
    raw = bundle(payload=b"a" * 20000)
    with pytest.raises(ValueError, match="ordinary CLI archive member"):
        verify(raw, max_bytes=len(raw) + 10)


def test_descriptor_read_and_create_new_synthetic_output(tmp_path):
    archive = tmp_path / "synthetic.tar.gz"
    archive.write_bytes(bundle())
    assert runtime.read_archive(archive) == archive.read_bytes()
    output = tmp_path / "synthetic-output.txt"
    runtime.write_new(output, SYNTHETIC)
    assert output.read_bytes() == SYNTHETIC
    with pytest.raises(FileExistsError):
        runtime.write_new(output, SYNTHETIC)
    with pytest.raises(ValueError):
        runtime.read_archive(tmp_path)


@pytest.mark.skipif(os.name == "nt", reason="POSIX symlink archive fixture")
def test_archive_file_itself_refuses_symlink(tmp_path):
    source = tmp_path / "synthetic.tar.gz"
    source.write_bytes(bundle())
    link = tmp_path / "link"
    link.symlink_to(source)
    with pytest.raises(ValueError):
        runtime.read_archive(link)


def test_cli_cannot_override_release_pins():
    import ast

    tree = ast.parse((ROOT / "tests/portable_runtime.py").read_text())
    main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
    calls = [
        node
        for node in ast.walk(main)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "verify_tar"
    ]
    assert len(calls) == 1 and not calls[0].keywords
    assert runtime.CLI_SHA256 == "05982fe44214f6174ffb54166d100e2362cf90811f2480235f3ecbaa0a3a75c2"
    assert runtime.ARCHIVE_SHA256 == "ddff0a2ec0d89e5e9e65644ed724b5b79959600b1602fd4ea6653b5a54bf88fd"
