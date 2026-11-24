"""Fewer git processes in tests: answer repeated read-only git commands from a cache.

`herd.fingerprint`, `herd.verify`, `herd.gate` and others ask git the same questions about an unchanged repository
many times per test, and starting a process costs far more than the question. The answer to a read-only git command
depends only on the repository state and the working tree, so the cache is keyed by a hash of exactly that: every
file under the working tree (path, mode, content, link target) and every file under the git directory except the
object store. Any edit, add, commit or branch change gives a new key and a real git call. Commands that write
(add, commit, stash push, switch, worktree and so on) are never cached."""
import hashlib
import os
from pathlib import Path

READ_ONLY = {"rev-parse", "diff", "ls-files", "status", "stash"}  # stash: only `stash list`
GIT_DIR_ONLY = {"rev-parse", "stash"}  # answered from refs and HEAD, never from the working tree
_cache = {}
_MAX = 20000


def _hash_tree(h, base, skip):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if os.path.join(dirpath, d) not in skip)
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            if path in skip:
                continue
            h.update(os.path.relpath(path, base).encode(errors="surrogateescape") + b"\0")
            try:
                st = os.lstat(path)
                h.update(str(st.st_mode).encode())
                if os.path.islink(path):
                    h.update(os.readlink(path).encode(errors="surrogateescape"))
                else:
                    with open(path, "rb") as f:
                        h.update(f.read())
            except OSError:
                h.update(b"?")
        for d in dirnames:  # an empty folder is not in git, but a link to one is read as a link
            if os.path.islink(os.path.join(dirpath, d)):
                h.update(b"L" + d.encode() + os.readlink(os.path.join(dirpath, d)).encode())


def state(root, tree=True, skip=()):
    """A hash of the repository state around `root` (the git directory, and the working tree when `tree`, minus the
    top-level folders in `skip`), or None when `root` is not inside a plain git working tree."""
    top = os.path.realpath(root)
    while not os.path.exists(os.path.join(top, ".git")):
        parent = os.path.dirname(top)
        if parent == top:
            return None
        top = parent
    dot = os.path.join(top, ".git")
    dirs = []
    if os.path.isdir(dot):
        dirs.append(dot)
    else:
        try:
            line = Path(dot).read_text().strip()
            gitdir = os.path.normpath(os.path.join(top, line.split(":", 1)[1].strip()))
            dirs.append(gitdir)
            common = os.path.join(gitdir, "commondir")
            if os.path.exists(common):
                dirs.append(os.path.normpath(os.path.join(gitdir, Path(common).read_text().strip())))
        except (OSError, IndexError):
            return None
    h = hashlib.sha1(top.encode())
    for d in dirs:
        _hash_tree(h, d, {os.path.join(d, "objects")})
    if tree:
        _hash_tree(h, top, {dot, *(os.path.join(top, n) for n in skip)})
    return h.hexdigest()


def install(herd):
    real = herd._git

    def cached(root, *args):
        if not args or args[0] not in READ_ONLY or (args[0] == "stash" and args[1:2] != ("list",)) \
                or not os.path.isdir(root):
            return real(root, *args)
        tree = args[0] not in GIT_DIR_ONLY
        skip = (".herd",) if ":!.herd" in args else ()  # the pathspec leaves Herd's own state out of the answer
        before = state(root, tree, skip)
        if before is None:
            return real(root, *args)
        key = (os.path.realpath(root), args)
        hit = _cache.get((key, before))
        if hit is not None:
            return hit
        out = real(root, *args)
        if len(_cache) > _MAX:
            _cache.clear()
        _cache[(key, before)] = out
        after = state(root, tree, skip)  # git refreshes the index on diff and status; the answer is the same either way
        if after is not None:
            _cache[(key, after)] = out
        return out

    herd._git = cached
