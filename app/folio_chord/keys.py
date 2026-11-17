"""Passcodes kept out of settings.json (C8-37): in the desktop's keyring (the Secret Service that
GNOME Keyring and KWallet provide) when there is one, otherwise in a file only you can read.

  load(name, default)   the value stored under name
  save(name, value)     store it ("" or {} removes it)
"""
import json
import os
import threading

from gi.repository import GLib

_SCHEMA = None
_OK = None


def _secret():
    """The Secret module and schema, or None when there is no keyring to use."""
    global _SCHEMA, _OK
    if _OK is False or os.environ.get("FOLIO_CHORD_NO_KEYRING"):
        return None
    try:
        import gi
        gi.require_version("Secret", "1")
        from gi.repository import Secret
    except (ImportError, ValueError):
        _OK = False
        return None
    if _SCHEMA is None:
        _SCHEMA = Secret.Schema.new("org.folio.Chord", Secret.SchemaFlags.NONE,
                                    {"name": Secret.SchemaAttributeType.STRING})
    if _OK is None:
        # a keyring that can't be reached, or that would sit waiting on a prompt, isn't used
        done = {}

        def probe():
            try:
                Secret.password_lookup_sync(_SCHEMA, {"name": "probe"}, None)
                done["ok"] = True
            except GLib.Error:
                done["ok"] = False
        t = threading.Thread(target=probe, daemon=True)
        t.start()
        t.join(3)
        _OK = bool(done.get("ok"))
        if not _OK:
            return None
    from gi.repository import Secret
    return Secret


def _file():
    return os.path.join(GLib.get_user_config_dir(), "folio-chord", "passcodes.json")


def _read_file():
    try:
        with open(_file()) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_file(d):
    p = _file()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    tmp = p + ".tmp"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(d, f)
    os.replace(tmp, p)


def where():
    return "keyring" if _secret() is not None else "file"


def load(name, default=None):
    S = _secret()
    if S is not None:
        try:
            v = S.password_lookup_sync(_SCHEMA, {"name": name}, None)
        except GLib.Error:
            v = None
        if v is None:
            return default
        try:
            return json.loads(v)
        except ValueError:
            return default
    return _read_file().get(name, default)


def save(name, value):
    empty = value in ("", None) or value == {}
    S = _secret()
    if S is not None:
        try:
            if empty:
                S.password_clear_sync(_SCHEMA, {"name": name}, None)
            else:
                S.password_store_sync(_SCHEMA, {"name": name}, S.COLLECTION_DEFAULT,
                                      "Folio Chord: %s" % name.replace("_", " "), json.dumps(value), None)
            return
        except GLib.Error:
            pass
    d = _read_file()
    if empty:
        d.pop(name, None)
    else:
        d[name] = value
    _write_file(d)
