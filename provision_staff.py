#!/usr/bin/env python3
"""Create or rotate an individual staff login with optional TOTP enrollment."""
import argparse,getpass
import server
import security as sec
p=argparse.ArgumentParser();p.add_argument('staff_id',choices=server.STAFF);p.add_argument('--mfa',action='store_true');args=p.parse_args()
password=getpass.getpass('New staff password (14+ characters): ')
repeat=getpass.getpass('Confirm password: ')
if password!=repeat:raise SystemExit('Passwords do not match')
with server.conn() as c:secret=sec.provision(c,args.staff_id,password,args.mfa)
print('Credential provisioned for',args.staff_id,'and previous sessions revoked.')
if secret:print('TOTP enrollment secret (store securely and do not paste into a submission):',secret)
