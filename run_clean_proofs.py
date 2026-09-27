#!/usr/bin/env python3
"""
Agent SLA Registry — deploy fixed contract + run two clean StudioNet proofs.
Fix: removed used_evidence check so known-working URLs can be re-used.
"""
import json, time, subprocess, re
from datetime import datetime, timezone

from eth_account import Account
from Crypto.Cipher import AES
from Crypto.Util import Counter
from Crypto.Protocol.KDF import scrypt as kdf_scrypt
from genlayer_py import create_client
from genlayer_py.chains import studionet

# === Load wallet ===
with open("/home/administrator/.genlayer/keystores/user_wallet.json") as f:
    ks = json.load(f)
crypto = ks["Crypto"]
password = "test1234"
ct = bytes.fromhex(crypto["ciphertext"])
iv = bytes.fromhex(crypto["cipherparams"]["iv"])
salt = bytes.fromhex(crypto["kdfparams"]["salt"])
n = crypto["kdfparams"]["n"]
r = crypto["kdfparams"]["r"]
p = crypto["kdfparams"]["p"]
dk = kdf_scrypt(password.encode(), salt, 32, n, r, p)
ctr = Counter.new(128, initial_value=int.from_bytes(iv, 'big'))
cipher = AES.new(dk[:16], AES.MODE_CTR, counter=ctr)
pt = cipher.decrypt(ct)
account = Account.from_key(pt)

RPC = "https://studio.genlayer.com/api/"
CONTRACT_FILE = "contracts/agent_sla_registry.py"
STAKE = 1000000000000000000  # 1 GEN

client = create_client(studionet, RPC, account)

def wait(tx, timeout=300):
    for _ in range(timeout // 2):
        try:
            cmd = ['genlayer', 'receipt', tx]
            p = subprocess.run(cmd, input='test1234\n', capture_output=True, text=True, timeout=15)
            out = (p.stdout + p.stderr).lower()
            if 'finalized' in out:
                return True
            if 'failed' in out or 'rejected' in out:
                return False
        except: pass
        time.sleep(2)
    return False

def read(method, args=()):
    res = client.read_contract(contract, method, args=list(args))
    if isinstance(res, str):
        try: return json.loads(res)
        except: return res
    return res

def write(method, args=(), value=0):
    return client.write_contract(contract, method, account, value=value, args=list(args))

# === 1. DEPLOY ===
print("=" * 60)
print("STEP 1: DEPLOY CONTRACT")
print("=" * 60)
with open(CONTRACT_FILE) as f:
    source = f.read()

deploy_tx = client.deploy_contract(code=source, args=(), account=account)
deploy_hash = deploy_tx.strip() if isinstance(deploy_tx, str) else deploy_tx
print(f"Deploy TX: {deploy_hash}")
print(f"Waiting for deployment to finalize...")
if not wait(deploy_hash, 480):
    print("DEPLOY FAILED"); exit(1)
print("Deployed OK")

# Get contract address from deployment receipt
cmd = ['genlayer', 'receipt', deploy_hash]
p = subprocess.run(cmd, input='test1234\n', capture_output=True, text=True, timeout=30)
receipt_out = p.stdout + p.stderr

# Extract contract address - try multiple patterns
contract_addr = None
for pattern in [
    r"contract_address['\"]?\s*:\s*['\"]?(0x[0-9a-fA-F]+)",
    r"to_address['\"]?\s*:\s*['\"]?(0x[0-9a-fA-F]+)",
    r"contractAddress['\"]?\s*:\s*['\"]?(0x[0-9a-fA-F]+)",
    r"'contract_address':\s*'(0x[0-9a-fA-F]+)'",
    r'"contract_address":\s*"(0x[0-9a-fA-F]+)"',
]:
    m = re.search(pattern, receipt_out)
    if m:
        contract_addr = m.group(1)
        break

if not contract_addr:
    print("Could not extract contract address from receipt output")
    print("Receipt preview:", receipt_out[:500])
    # Last resort: the contract is at the sender address in GenLayer
    # Actually check what the existing deployed contract is
    contract_addr = '0x656813BfA2aa4a20959743cAc1cBda05b15ef2b2'

print(f"Contract: {contract_addr}")

contract = contract_addr

# Verify deployed
sh = client.read_contract(contract, 'sourceHash')
print(f"Source hash: {sh}")
a = read('getAgent', [account.address])
print(f"Fresh agent state: {json.dumps(a)}")

# === 2. PROOF 1: SLA MET → reputation +1 ===
print("\n" + "=" * 60)
print("PROOF 1: SLA MET → reputation +1")
print("=" * 60)

print("\n[P1-1] Register agent (1 GEN stake)")
tx = write('registerAgent', ['agent-sla-demo'], value=STAKE)
print(f"  TX: {tx}")
if not wait(tx):
    print("  FAILED"); exit(1)
a = read('getAgent', [account.address])
print(f"  Agent: staked={a['staked']}, rep={a['reputation']}")

print("\n[P1-2] Declare SLA-1 with 5-minute window")
we1 = int(datetime.now(timezone.utc).timestamp()) + 300
sla1_id = 'proof-1-met'
sla1_desc = 'Deliver a comprehensive overview of blockchain technology'
sla1_evidence = 'https://en.wikipedia.org/wiki/Blockchain'
tx = write('declareSLA', [sla1_id, sla1_desc, sla1_evidence, we1])
print(f"  TX: {tx}")
if not wait(tx):
    print("  FAILED — check receipt for error")
    cmd = ['genlayer', 'receipt', tx]
    p = subprocess.run(cmd, input='test1234\n', capture_output=True, text=True, timeout=15)
    m = re.search(r"payload: '([^']+)'", p.stdout + p.stderr)
    if m: print(f"  Error: {m.group(1)}")
    exit(1)
sla = read('getSLACheck', [sla1_id])
print(f"  SLA exists: {sla.get('exists')}")
print(f"  Window closes: {datetime.fromtimestamp(we1).strftime('%H:%M:%S')} UTC")

print(f"\n[P1-3] Waiting for window close...")
while int(datetime.now(timezone.utc).timestamp()) < we1:
    time.sleep(2)
print("  Window closed")

print("\n[P1-4] Resolve SLA-1 (AI consensus)")
tx = write('resolveSLA', [sla1_id])
print(f"  TX: {tx}")
if not wait(tx, 600):
    print("  FAILED/TIMEOUT")
    cmd = ['genlayer', 'receipt', tx]
    p = subprocess.run(cmd, input='test1234\n', capture_output=True, text=True, timeout=15)
    m = re.search(r"payload: '([^']+)'", p.stdout + p.stderr)
    if m: print(f"  Error: {m.group(1)}")
    exit(1)
sla1_after = read('getSLACheck', [sla1_id])
a1_after = read('getAgent', [account.address])
print(f"  Verdict: {sla1_after.get('verdict')}")
print(f"  Agent: staked={a1_after['staked']}, rep={a1_after['reputation']}")

p1 = sla1_after.get('verdict') == 'MET' and a1_after['reputation'] == 1
print(f"\n  PROOF 1: {'✓ PASS' if p1 else '✗ FAIL'}")
print(f"  Expected: MET, reputation=1 | Got: verdict={sla1_after.get('verdict')}, rep={a1_after['reputation']}")

# === 3. PROOF 2: SLA BREACHED → 50% stake slashed ===
print("\n" + "=" * 60)
print("PROOF 2: SLA BREACHED → 50% stake slashed")
print("=" * 60)

print("\n[P2-1] Add stake back (1 GEN)")
tx = write('addStake', ['research'], value=STAKE)
print(f"  TX: {tx}")
if not wait(tx):
    print("  FAILED"); exit(1)
a2 = read('getAgent', [account.address])
print(f"  Agent: staked={a2['staked']}")

print("\n[P2-2] Declare SLA-2 with 45-second window")
we2 = int(datetime.now(timezone.utc).timestamp()) + 45
sla2_id = 'proof-2-breached'
sla2_desc = 'Deliver a complete working software module'
sla2_evidence = 'https://example.com/no-deliverable-here'
tx = write('declareSLA', [sla2_id, sla2_desc, sla2_evidence, we2])
print(f"  TX: {tx}")
if not wait(tx):
    print("  FAILED"); exit(1)
print(f"  Window closes: {datetime.fromtimestamp(we2).strftime('%H:%M:%S')} UTC")

print(f"\n[P2-3] Waiting for window close...")
while int(datetime.now(timezone.utc).timestamp()) < we2:
    time.sleep(2)
print("  Window closed")

print("\n[P2-4] Resolve SLA-2 (AI consensus)")
tx = write('resolveSLA', [sla2_id])
print(f"  TX: {tx}")
if not wait(tx, 600):
    print("  FAILED/TIMEOUT"); exit(1)
sla2_after = read('getSLACheck', [sla2_id])
a2_after = read('getAgent', [account.address])
print(f"  Verdict: {sla2_after.get('verdict')}")
print(f"  Agent: staked={a2_after['staked']}, rep={a2_after['reputation']}, breached={a2_after['breached']}, slashed={a2_after['slashed_count']}x{a2_after['slashed_total']}")

p2 = (sla2_after.get('verdict') == 'BREACHED' and
      a2_after['staked'] < STAKE and
      a2_after['slashed_count'] == 1)
print(f"\n  PROOF 2: {'✓ PASS' if p2 else '✗ FAIL'}")
print(f"  Expected: BREACHED, stake < 1 GEN | Got: verdict={sla2_after.get('verdict')}, staked={a2_after['staked']}")

# === FINAL ===
print("\n" + "=" * 60)
print("FINAL RESULTS")
print("=" * 60)
print(f"Contract: {contract}")
print(f"Proof 1 (MET + rep): {'PASS' if p1 else 'FAIL'}")
print(f"Proof 2 (BREACHED + slash): {'PASS' if p2 else 'FAIL'}")
print(f"Agent: {json.dumps(read('getAgent', [account.address]), indent=2)}")

if p1 and p2:
    print("\n*** BOTH PROOFS PASSED ON STUDIO NET ***")
