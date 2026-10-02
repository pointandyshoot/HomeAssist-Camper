"""Bounded private history and fail-closed command policy, independent of HA."""
import base64
import hashlib
import json
import math
from pathlib import Path
import re
import secrets
import sqlite3
import threading


def node_number(value):
    if isinstance(value, str) and re.fullmatch(r"![0-9a-fA-F]{8}", value):
        return node_number(int(value[1:], 16))
    if type(value) is int and 0 < value < 0xFFFFFFFF:
        return value
    raise ValueError("Invalid node number")


def read_config(path):
    if not Path(path).exists():
        return {"enabled": False}
    config = json.loads(Path(path).read_text())
    if config.get("enabled") is not True:
        return {"enabled": False}
    config["gateway_node"] = node_number(config["gateway_node"])
    radios = config.get("authorised_radios", [])
    if not isinstance(radios, list) or len(radios) > 2:
        raise ValueError("At most two command radios")
    config["keys"] = {}
    for radio in radios:
        node = node_number(radio["node"])
        key = base64.b64decode(radio["public_key"], validate=True)
        if len(key) != 32 or key in config["keys"].values() or node in config["keys"] or node == config["gateway_node"]:
            raise ValueError("Invalid authorised radio")
        config["keys"][node] = key
    for name, default, low, high in (
        ("telemetry_max_age_seconds", 180, 30, 600),
        ("gps_max_age_seconds", 300, 30, 900),
        ("history_days", 90, 1, 365),
    ):
        value = config.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError("Invalid retention/freshness limit")
        config[name] = value
    for name, default in (("ac_switch", "switch.camper_bluetti_ac"),
                          ("soc_sensor", "sensor.camper_bluetti_soc")):
        config.setdefault(name, default)
    config.setdefault("input_sensors", ["sensor.camper_bluetti_ac_input", "sensor.camper_bluetti_dc_input"])
    config.setdefault("output_sensors", ["sensor.camper_bluetti_ac_output", "sensor.camper_bluetti_dc_output"])
    for entity in [config["ac_switch"], config["soc_sensor"], *config["input_sensors"], *config["output_sensors"]]:
        if not isinstance(entity, str) or not re.fullmatch(r"(?:sensor|switch)\.[a-z0-9_]+", entity):
            raise ValueError("Invalid entity mapping")
    if not config["ac_switch"].startswith("switch.") or len(config["input_sensors"]) > 8 or len(config["output_sensors"]) > 8:
        raise ValueError("Invalid entity mapping")
    return config


class Policy:
    def __init__(self, config):
        self.config = config
        self.pending = {}
        self.replies = {}

    def authenticate(self, packet, gateway):
        """Firmware's successful PKI decryption metadata, never names/IDs alone."""
        try:
            sender = node_number(packet["from"])
            if (gateway != self.config["gateway_node"] or
                packet.get("to") != gateway or packet.get("pkiEncrypted") is not True or
                packet.get("viaMqtt") is True or sender not in self.config["keys"] or
                packet.get("decoded", {}).get("portnum") != "TEXT_MESSAGE_APP"):
                return None
            key = base64.b64decode(packet["publicKey"], validate=True)
            if not secrets.compare_digest(key, self.config["keys"][sender]):
                return None
            payload = base64.b64decode(packet["decoded"]["payload"], validate=True)
            if len(payload) > 220 or type(packet.get("id")) is not int or not 0 < packet["id"] <= 0xFFFFFFFF:
                return None
            return sender, payload.decode("utf-8").strip().lower()
        except (KeyError, TypeError, ValueError, UnicodeError):
            return None

    def command(self, sender, text, now):
        if text in ("status", "help"):
            if now - self.replies.get(sender, -1000) < 15:
                return "drop", None
            self.replies[sender] = now
            return text, None
        if text not in ("ac on", "ac off") and not text.startswith("confirm "):
            return "drop", None
        if not (self.config.get("ac_control_enabled") is True and
                self.config.get("independent_pi_power_confirmed") is True):
            if now - self.replies.get(sender, -1000) < 15:
                return "drop", None
            self.replies[sender] = now
            return "denied", None
        if text in ("ac on", "ac off"):
            if now - self.replies.get(sender, -1000) < 15:
                return "drop", None
            self.replies[sender] = now
            token = secrets.token_hex(4)
            self.pending[sender] = (text[3:], token, now + 90)
            return "challenge", (text[3:], token)
        if text.startswith("confirm "):
            pending = self.pending.pop(sender, None)
            if pending and now <= pending[2] and secrets.compare_digest(text[8:], pending[1]):
                return "set", pending[0]
            return "drop", None
        return "drop", None


def valid_position(position, now, max_age):
    try:
        latitude, longitude, stamp = position["latitude"], position["longitude"], position["time"]
        if (not all(type(x) in (float, int) and math.isfinite(x) for x in (latitude, longitude, stamp)) or
            not -90 <= latitude <= 90 or not -180 <= longitude <= 180 or
            not 0 <= now - stamp <= max_age):
            return None
        return {"latitude": latitude, "longitude": longitude, "time": stamp,
                "precision_bits": int(position.get("precision_bits", 0))}
    except (KeyError, ValueError, TypeError):
        return None


class History:
    """Aggregate encounters rather than storing every radio packet.

    A new session requires a 30-minute reception gap. This counts encounters
    with a radio identifier, not people. Only fresh positions become map pins.
    """
    def __init__(self, path, days=90):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        path.chmod(0o600)
        self.db.row_factory = sqlite3.Row
        self.days = days
        self.db.executescript("""
        PRAGMA auto_vacuum=INCREMENTAL;
        PRAGMA journal_mode=DELETE;
        CREATE TABLE IF NOT EXISTS nodes (node INTEGER PRIMARY KEY, name TEXT, first REAL, last REAL, sessions INTEGER);
        CREATE TABLE IF NOT EXISTS encounters (id INTEGER PRIMARY KEY, node INTEGER, first REAL, last REAL,
          packets INTEGER, rssi REAL, via TEXT, own_lat REAL, own_lon REAL, own_time REAL,
          remote_lat REAL, remote_lon REAL, remote_time REAL, precision_bits INTEGER);
        CREATE INDEX IF NOT EXISTS encounters_node ON encounters(node,last);
        CREATE TABLE IF NOT EXISTS route (time REAL PRIMARY KEY, latitude REAL, longitude REAL, precision_bits INTEGER);
        CREATE TABLE IF NOT EXISTS consumed (hash TEXT PRIMARY KEY, time REAL);
        """)
        self.db.commit()

    def consume(self, sender, packet_id, payload, now):
        # Persistent replay guard across HA restarts. Longer than normal mesh TTL.
        digest = hashlib.sha256(f"{sender}:{packet_id}:{payload}".encode()).hexdigest()
        with self.lock, self.db:
            cursor = self.db.execute("INSERT OR IGNORE INTO consumed VALUES (?,?)", (digest, now))
            return cursor.rowcount == 1

    def record(self, node, name, now, packet, own=None, remote=None):
        name = str(name or "Unnamed radio")[:80]
        rssi = packet.get("rxRssi")
        if type(rssi) not in (int, float) or not math.isfinite(rssi):
            rssi = None
        hops = packet.get("hopStart"), packet.get("hopLimit")
        via = "direct" if all(type(v) is int for v in hops) and hops[0] > 0 and hops[0] == hops[1] else "relayed or unknown"
        with self.lock, self.db:
            previous = self.db.execute("SELECT * FROM encounters WHERE node=? ORDER BY last DESC LIMIT 1", (node,)).fetchone()
            new = not previous or now - previous["last"] > 1800
            self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,1) ON CONFLICT(node) DO UPDATE SET name=excluded.name,last=excluded.last,sessions=sessions+?",
                            (node, name, now, now, int(new)))
            if new:
                cursor = self.db.execute("INSERT INTO encounters (node,first,last,packets,via) VALUES (?,?,?,0,?)", (node, now, now, via))
                encounter = cursor.lastrowid
            else:
                encounter = previous["id"]
            self.db.execute("UPDATE encounters SET last=?,packets=packets+1,rssi=?,via=? WHERE id=?", (now, rssi, via, encounter))
            for prefix, position in (("own", own), ("remote", remote)):
                if position:
                    self.db.execute(f"UPDATE encounters SET {prefix}_lat=?,{prefix}_lon=?,{prefix}_time=? WHERE id=?",
                                    (position["latitude"], position["longitude"], position["time"], encounter))
            if remote:
                self.db.execute("UPDATE encounters SET precision_bits=? WHERE id=?", (remote["precision_bits"], encounter))

    def route(self, position):
        with self.lock, self.db:
            latest = self.db.execute("SELECT MAX(time) FROM route").fetchone()[0]
            if latest and position["time"] - latest < 60:
                return
            self.db.execute("INSERT OR IGNORE INTO route VALUES (?,?,?,?)", (position["time"], position["latitude"], position["longitude"], position["precision_bits"]))

    def prune(self, now):
        with self.lock, self.db:
            cutoff = now - self.days * 86400
            for table, column, cap in (("encounters", "last", 20000), ("route", "time", 100000), ("consumed", "time", 10000)):
                self.db.execute(f"DELETE FROM {table} WHERE {column}<?", (cutoff,))
                self.db.execute(f"DELETE FROM {table} WHERE rowid NOT IN (SELECT rowid FROM {table} ORDER BY {column} DESC LIMIT ?)", (cap,))
            self.db.execute("DELETE FROM nodes WHERE node NOT IN (SELECT node FROM encounters)")
            self.db.execute("DELETE FROM nodes WHERE node NOT IN (SELECT node FROM nodes ORDER BY last DESC LIMIT 1000)")
            self.db.execute("DELETE FROM encounters WHERE node NOT IN (SELECT node FROM nodes)")
            self.db.execute("UPDATE encounters SET first=MAX(first,?)", (cutoff,))
            for prefix in ("own", "remote"):
                self.db.execute(f"UPDATE encounters SET {prefix}_lat=NULL,{prefix}_lon=NULL,{prefix}_time=NULL WHERE {prefix}_time<?", (cutoff,))
            self.db.execute("UPDATE nodes SET sessions=(SELECT COUNT(*) FROM encounters WHERE encounters.node=nodes.node),first=(SELECT MIN(first) FROM encounters WHERE encounters.node=nodes.node)")
            # Bound allocated disk too; timed hourly, not on every packet.
        with self.lock:
            self.db.execute("PRAGMA incremental_vacuum(256)")

    def snapshot(self, limit=200):
        with self.lock:
            nodes = [dict(r) for r in self.db.execute("SELECT * FROM nodes ORDER BY last DESC LIMIT ?", (limit,))]
            for node in nodes:
                latest = self.db.execute("SELECT * FROM encounters WHERE node=? ORDER BY last DESC LIMIT 1", (node["node"],)).fetchone()
                node.update(dict(latest))
                node["node"] = f'!{node["node"]:08x}'
                node["first_seen"] = self.db.execute("SELECT first FROM nodes WHERE node=?", (int(node["node"][1:], 16),)).fetchone()[0]
            encounters = [dict(r) for r in self.db.execute("SELECT * FROM encounters ORDER BY last DESC LIMIT ?", (limit,))]
            route = [dict(r) for r in self.db.execute("SELECT * FROM route ORDER BY time DESC LIMIT ?", (limit,))]
            count = self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            repeats = self.db.execute("SELECT COUNT(*) FROM nodes WHERE sessions>1").fetchone()[0]
            return {"nodes": nodes, "encounters": encounters, "route": route, "count": count, "repeats": repeats}

    def close(self):
        with self.lock:
            self.db.close()
