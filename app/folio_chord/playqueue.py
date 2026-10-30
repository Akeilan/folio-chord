"""What plays next (C3-02): the songs of the list you started from, Up Next (Play Next / Add to
Up Next), shuffle (by song or, as iTunes offered, by album) and repeat (off, all, one).

  q = PlayQueue()
  q.start(track_ids, index)      play the list from that song
  q.play_next(ids) / q.add(ids)  Up Next
  q.advance() -> id or None      the song after the current one (moves on)
  q.back() -> id or None
"""
import random


class PlayQueue:
    def __init__(self, rng=None):
        self.source = []          # the list playback started from (track ids)
        self.order = []           # indexes into source, in play order
        self.pos = -1             # where in order we are
        self.up_next = []         # ids queued by the person; played before the rest
        self.current = None       # id now playing
        self.shuffle = False
        self.shuffle_by = "songs"   # or "albums"
        self.repeat = "off"         # off | all | one
        self.history = []
        self.rng = rng or random.Random()
        self.album_of = None        # fn(id) -> album key, for shuffle by album
        self.skip_shuffle = None    # fn(id) -> bool: left out when shuffling

    def start(self, ids, index=0):
        self.source = list(ids)
        self._make_order(first=index)
        self.pos = self.order.index(index) if self.source and index in self.order else (0 if self.source else -1)
        self.current = self.source[self.order[self.pos]] if self.source else None
        if self.current is not None:
            self.history.append(self.current)
        return self.current

    def _make_order(self, first=None):
        n = len(self.source)
        idx = list(range(n))
        if self.shuffle and n:
            if self.skip_shuffle:
                idx = [i for i in idx if not self.skip_shuffle(self.source[i]) or i == first]
            if self.shuffle_by == "albums" and self.album_of:
                albums = {}
                for i in idx:
                    albums.setdefault(self.album_of(self.source[i]), []).append(i)
                keys = list(albums)
                self.rng.shuffle(keys)
                if first is not None:
                    k0 = self.album_of(self.source[first])
                    keys.remove(k0)
                    keys.insert(0, k0)
                    albums[k0] = [first] + [i for i in albums[k0] if i != first]
                idx = [i for k in keys for i in albums[k]]
            else:
                self.rng.shuffle(idx)
                if first is not None and first in idx:
                    idx.remove(first)
                    idx.insert(0, first)
        self.order = idx

    def set_shuffle(self, on, by=None):
        self.shuffle = bool(on)
        if by:
            self.shuffle_by = by
        cur = self.source.index(self.current) if self.current in self.source else None
        self._make_order(first=cur)
        self.pos = self.order.index(cur) if cur is not None and cur in self.order else -1

    def set_repeat(self, mode):
        self.repeat = mode
        if not self.shuffle and self.current in self.source:
            cur = self.source.index(self.current)
            self.order = list(range(len(self.source)))
            self.pos = cur

    def play_next(self, ids):
        self.up_next[0:0] = list(ids)

    def add(self, ids):
        self.up_next.extend(ids)

    def clear_up_next(self):
        self.up_next = []

    def upcoming(self, n=50):
        """The next songs, Up Next first, without moving on."""
        out = list(self.up_next)
        if self.repeat == "one" and self.current is not None:
            return out[:n]
        p = self.pos + 1
        while len(out) < n and self.order:
            if p >= len(self.order):
                if self.repeat != "all":
                    break
                p = 0
            out.append(self.source[self.order[p]])
            p += 1
            if len(out) > len(self.order) + len(self.up_next):
                break
        return out[:n]

    def advance(self, user=False):
        """Move to the next song and return it (None at the end). user: the person pressed Next,
        so repeat one moves on."""
        if self.repeat == "one" and not user and self.current is not None:
            return self.current
        if self.up_next:
            self.current = self.up_next.pop(0)
            self.history.append(self.current)
            return self.current
        if not self.order:
            self.current = None
            return None
        self.pos += 1
        if self.pos >= len(self.order):
            if self.repeat in ("all", "one") and self.source:
                if self.shuffle:
                    self._make_order()
                else:
                    self.order = list(range(len(self.source)))
                self.pos = 0
            else:
                self.pos = len(self.order)
                self.current = None
                return None
        self.current = self.source[self.order[self.pos]]
        self.history.append(self.current)
        return self.current

    def back(self):
        if not self.order:
            return self.current
        if self.pos > 0:
            self.pos -= 1
        elif self.repeat == "all":
            self.pos = len(self.order) - 1
        self.current = self.source[self.order[self.pos]]
        return self.current
