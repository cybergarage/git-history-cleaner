"""Conservative byte budgets for checkpoint publication; never rewrite commits."""
from . import core

DEFAULT_MAX_BYTES = 1536 * 1024 * 1024


def checkpoints(repo, chunk_size, max_bytes, available=()):
    if chunk_size < 0 or max_bytes <= 0:
        raise ValueError("push chunk size must be nonnegative and max push bytes positive")
    commits = core.text(repo, "rev-list", "--topo-order", "--reverse", "HEAD").splitlines()
    ids = core.git(repo, "rev-list", "--objects", "--no-object-names", "HEAD")
    sizes = {}
    for line in core.git(repo, "cat-file", "--batch-check=%(objectname) %(objectsize)", data=ids).splitlines():
        oid, size = line.split()
        size = int(size)
        # Raw object size plus zlib/object framing overhead, without relying on
        # existing pack deltas whose bases may not be available at the receiver.
        sizes[oid.decode()] = size + size // 1000 + 128
    known = list(available)
    result = []

    def split(start, stop):
        oid = commits[stop - 1]
        revisions = ("\n".join([oid] + ["^" + tip for tip in known]) + "\n").encode()
        objects = core.git(repo, "rev-list", "--objects", "--no-object-names", "--stdin", data=revisions).decode().splitlines()
        if not objects:
            return
        bound = 1024 * 1024 + sum(sizes[obj] for obj in objects)
        if bound > max_bytes:
            if stop - start == 1:
                raise ValueError(f"commit {oid} needs a conservative {bound} byte budget; "
                                 "cannot split it without changing history; no push was attempted")
            middle = (start + stop) // 2
            split(start, middle)
            split(middle, stop)
        else:
            result.append((oid, bound))
            known.append(oid)

    step = chunk_size or len(commits)
    for start in range(0, len(commits), step):
        split(start, min(start + step, len(commits)))
    return result
