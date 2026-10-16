"""Optional individually provisioned staff credentials, TOTP MFA and login protection.
Strict mode requires PROOFLEDGER_STRICT_AUTH=1; not an identity provider or SSO.
"""
import base64
import hashlib
import hmac
import json
import secrets
import struct
import time
from datetime import datetime, timezone, timedelta


def now(): return datetime.now(timezone.utc).isoformat()

def init(db):
    db.execute('CREATE TABLE IF NOT EXISTS staff_credentials(staff_id TEXT PRIMARY KEY, salt TEXT NOT NULL, password_hash TEXT NOT NULL, totp_secret TEXT, updated_at TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS login_attempts(staff_id TEXT PRIMARY KEY, attempts INTEGER NOT NULL, window_started TEXT NOT NULL, locked_until TEXT)')


def password_hash(password, salt):
    return hashlib.scrypt(password.encode('utf-8'), salt=bytes.fromhex(salt),n=2**14,r=8,p=1).hex()


def provision(db, staff_id, password, totp=False):
    if not isinstance(password,str) or len(password)<14 or len(password)>256: raise ValueError('Staff passphrase must be 14–256 characters')
    salt=secrets.token_hex(16)
    secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=') if totp else None
    db.execute('INSERT INTO staff_credentials VALUES (?,?,?,?,?) ON CONFLICT(staff_id) DO UPDATE SET salt=excluded.salt,password_hash=excluded.password_hash,totp_secret=excluded.totp_secret,updated_at=excluded.updated_at',(staff_id,salt,password_hash(password,salt),secret,now()))
    db.execute('DELETE FROM sessions WHERE staff_id=?',(staff_id,))
    db.execute('DELETE FROM login_attempts WHERE staff_id=?',(staff_id,))
    return secret


def otp_code(secret, step):
    raw=base64.b32decode(secret+'='*((-len(secret))%8))
    digest=hmac.new(raw,struct.pack('>Q',step),hashlib.sha1).digest()
    offset=digest[-1]&0x0F
    return str((struct.unpack('>I',digest[offset:offset+4])[0]&0x7FFFFFFF)%1_000_000).zfill(6)


def verify_otp(secret, otp):
    if not isinstance(otp,str) or len(otp)!=6 or not otp.isdecimal():return False
    tick=int(time.time()//30)
    return any(hmac.compare_digest(otp_code(secret,tick+delta),otp) for delta in (-1,0,1))


def verify(db, staff_id,password,otp,strict,demo_password):
    now_dt=datetime.now(timezone.utc)
    row=db.execute('SELECT attempts,window_started,locked_until FROM login_attempts WHERE staff_id=?',(staff_id,)).fetchone()
    if row and row[2] and datetime.fromisoformat(row[2])>now_dt: raise PermissionError('Sign-in temporarily locked after repeated attempts')
    cred=db.execute('SELECT salt,password_hash,totp_secret FROM staff_credentials WHERE staff_id=?',(staff_id,)).fetchone()
    if cred:
        password_ok=hmac.compare_digest(cred[1],password_hash(password,cred[0]))
        mfa_ok=not cred[2] or verify_otp(cred[2],otp)
        accepted=password_ok and mfa_ok
    else:
        accepted=not strict and hmac.compare_digest(password,demo_password)
    if accepted:
        db.execute('DELETE FROM login_attempts WHERE staff_id=?',(staff_id,))
        return True
    count=1
    if row and now_dt-datetime.fromisoformat(row[1])<timedelta(minutes=10):count=row[0]+1
    locked=(now_dt+timedelta(minutes=15)).isoformat() if count>=5 else None
    db.execute('INSERT INTO login_attempts VALUES (?,?,?,?) ON CONFLICT(staff_id) DO UPDATE SET attempts=excluded.attempts,window_started=excluded.window_started,locked_until=excluded.locked_until',(staff_id,count,now_dt.isoformat(),locked))
    return False


def info(db,staff_id,strict):
    row=db.execute('SELECT totp_secret IS NOT NULL FROM staff_credentials WHERE staff_id=?',(staff_id,)).fetchone()
    return {'individual_credentials':bool(row),'mfa_enabled':bool(row[0]) if row else False,'strict_auth':bool(strict)}
