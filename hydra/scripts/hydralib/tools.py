"""Hydra-OS's own small tools, in its folder:

  <root>/hydra/bin/python3   Hydra-OS's python3: it runs config.json's Python, so a hook or a command that says python3
                             gets the same one
  <root>/hydra/tmp           TMPDIR for every Hydra-OS process, so its temporary files stay in the Hydra-OS folder

Hydra-OS runs on its own Python, which hydra-setup fetches and checks and setup keeps in <root>/hydra/python/, so
nothing here stands in for one of Apple's tools, and no Hydra-OS process is given a DEVELOPER_DIR. A folder an older build set up
loses the stand-ins that build wrote (OLD_NAMES and its devtools folder). Python 3.9 standard library only.
"""
import os
import shlex
import shutil

from . import files

# the names an older build wrote stand-ins under, in <root>/hydra/bin: each goes when it's one of that build's own
OLD_NAMES = (
    "DeRez", "GetFileInfo", "ResMerger", "Rez", "SetFile", "SplitForks", "ar", "as", "asa", "bison", "bm4", "c++",
    "c++filt", "c89", "c99", "cc", "clang", "clang++", "clangd", "cmpdylib", "codesign_allocate", "cpp", "ctags",
    "ctf_insert", "dsymutil", "dwarfdump", "dyld_info", "flex", "flex++", "g++", "gatherheaderdoc", "gcc", "gcov", "git",
    "git-receive-pack", "git-shell", "git-upload-archive", "git-upload-pack", "gm4", "gnumake", "gperf", "hdxml2manxml",
    "headerdoc2html", "indent", "install_name_tool", "ld", "lex", "libtool", "lipo", "lldb", "llvm-g++", "llvm-gcc",
    "lorder", "m4", "make", "mig", "nm", "nmedit", "objdump", "otool", "pagestuff", "pip3", "ranlib", "resolveLinks",
    "rpcgen", "segedit", "size", "sourcekit-lsp", "strings", "strip", "swift", "swiftc", "unifdef", "unifdefall", "vtool",
    "xml2man", "yacc")
OLD_MARKS = ("t part of Hydra-OS.", "fatal: not a git repository", "-m pip \"$@\"")  # what those stand-ins said, as
# they were written, shell-quoted


def bin_dir(root):
    return os.path.join(root, "hydra", "bin")


def tmp_dir(root):
    return os.path.join(root, "hydra", "tmp")


def write(root, python):
    """Write <root>/hydra/bin/python3 and <root>/hydra/tmp, and take away an older build's stand-ins. python: Hydra-OS's
    Python. The hydra command and the jobs' Hydra-OS link, also in <root>/hydra/bin, aren't touched."""
    path = os.path.join(bin_dir(root), "python3")
    files.write_text(path, '#!/bin/sh\nexec %s "$@"\n' % shlex.quote(python))
    os.chmod(path, 0o700)
    files.folder(tmp_dir(root))
    shutil.rmtree(os.path.join(root, "hydra", "devtools"), ignore_errors=True)
    for name in OLD_NAMES:
        old = os.path.join(bin_dir(root), name)
        try:
            if os.path.isfile(old) and not os.path.islink(old) and os.path.getsize(old) < 512:
                with open(old, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                if text.startswith("#!/bin/sh\n") and any(mark in text for mark in OLD_MARKS):
                    os.unlink(old)
        except OSError:
            continue
    return ["python3"]


def ready(root):
    """Whether <root>'s tools are written, so a process may be given its TMPDIR."""
    return os.path.isdir(tmp_dir(root))
