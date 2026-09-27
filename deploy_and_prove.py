#!/usr/bin/env python3
"""Deploy AgentSLA Registry and run two StudioNet proofs."""
import json, time, sys
from datetime import datetime, timezone, timedelta
from eth_account import Account
from genlayer_py import create_client
from genlayer_py.chains import studionet
import pyaes
from hashlib import pbkdf2_hmac

# === Config ===
KEYSTORE = "/home/administrator/.genlayer/keystores/user_wallet.json"
PASSWORD = "test1234"
RPC = "https://studio.genlayer.com/api/"
CONTRACT_FILE = "contracts/agent_sla_registry.py"

# === Load wallet ===
# The genlayer CLI successfully decrypts this wallet with password "test1234".
# Python decryption gives different address. Use CLI-deployed contract.
# For the genlayer_py client, we need a valid account. 
# The CLI uses user_wallet (0x61fd...). We'll use create_account with the 
# known working private key from the CLI context.
# Since we can't extract the PK from CLI, use the deployer account which
# we can decrypt, or use a placeholder that works for reads.
# Actually, for reads we don't need a signed account. For writes, use CLI.
# Let's create a client without an account for reads, and use CLI for writes.

# === Approach: Use genlayer CLI for ALL operations ===
# The CLI correctly decrypts the keystore. We'll use subprocess for everything.
import subprocess, json

def cli_call(contract, method, args=()):
    """Read via genlayer CLI call command."""
    args_str = json.dumps(list(args)) if args else "[]"
    cmd = ["genlayer", "call", contract, method, "--args", args_str]
    proc = subprocess.run(cmd, input="test1234\n", capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        print(f"  CLI call error: {proc.stderr[:200]}")
        return None
    # Parse JSON result from output
    for line in proc.stdout.split('\n'):
        line = line.strip()
        if line.startswith('{') or line.startswith('['):
            try:
                return json.loads(line)
            except:
                pass
    return proc.stdout.strip()

def cli_write(contract, method, args=(), value=0):
    """Write via genlayer CLI write command. Returns TX hash or None."""
    args_str = json.dumps(list(args)) if args else "[]"
    cmd = ["genlayer", "write", contract, method, "--args", args_str]
    if value > 0:
        cmd += ["--value", str(value)]
    proc = subprocess.run(cmd, input="test1234\n", capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        print(f"  CLI write error: {proc.stderr[:300]}")
        return None
    # Extract TX hash
    for line in proc.stdout.split('\n'):
        if 'Transaction Hash:' in line:
            parts = line.split(':')
            tx_hash = parts[-1].strip()
            if tx_hash.startswith('0x') and len(tx_hash) == 66:
                return tx_hash
    return proc.stdout.strip()

def wait_for_tx(tx_hash, timeout=300):
    """Wait for transaction to be finalized on Studio Net."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            # Check transaction status
            status_res = client.read_contract(CONTRACT, "getTransactionStatus",
                args=[tx_hash], raw_return=True, transaction_hash_variant="latest-finalized")
            if status_res and status_res != "0x00":
                break
        except:
            pass
        time.sleep(3)
    return True

# === Deploy ===
print("\n=== DEPLOYING CONTRACT ===")
with open(CONTRACT_FILE) as f:
    source = f.read()

deploy_tx = client.deploy_contract(
    code=source,
    args=(),
    account=account
)
contract_addr = deploy_tx.get("contractAddress") if isinstance(deploy_tx, dict) else None
deploy_hash = deploy_tx.get("transactionHash", deploy_tx.get("hash", "")) if isinstance(deploy_tx, dict) else deploy_tx
print(f"Deploy result: {deploy_tx}")
print(f"Deploy TX: {deploy_hash}")
print(f"Contract: {contract_addr}")
time.sleep(5)

CONTRACT = contract_addr

# === Proof 1: SLA MET → reputation up ===
print("\n" + "="*60)
print("PROOF 1: SLA MET → reputation up")
print("="*60)

# Step 1: Register agent
print("\n[1] Registering agent with 2 GEN stake + capabilities")
reg_tx = write("registerAgent", args=["writing,research,coding"], value=2000000000000000000)
print(f"    TX: {reg_tx}")
time.sleep(2)

agent_before = read("getAgent", args=[account.address])
print(f"    Agent: exists={agent_before.get('exists')}, staked={agent_before.get('staked')}, reputation={agent_before.get('reputation')}")

# Step 2: Declare SLA with future deadline
deadline = int((datetime.now(timezone.utc) + timedelta(minutes=3)).timestamp())
print(f"\n[2] Declaring SLA (deadline={deadline})")
print(f"    Evidence: https://en.wikipedia.org/wiki/Artificial_intelligence")
decl_tx = write("declareSLA", args=[
    "proof-1-met",
    "Write a comprehensive technical article about AI",
    "https://en.wikipedia.org/wiki/Artificial_intelligence",
    str(deadline)
])
print(f"    TX: {decl_tx}")
time.sleep(2)

sla_before = read("getSLACheck", args=["proof-1-met"])
print(f"    SLA: exists={sla_before.get('exists')}, window_end={sla_before.get('window_end')}")

# Step 3: Wait for deadline
print(f"\n[3] Waiting for deadline ({datetime.fromtimestamp(deadline)})...")
while int(datetime.now(timezone.utc).timestamp()) < deadline:
    time.sleep(2)
print("    Deadline passed!")

# Step 4: Resolve SLA (triggers AI consensus)
print("\n[4] resolveSLA — AI consensus verifies evidence")
print("    (This triggers GenLayer consensus with AI validators)")
resolve_tx = write("resolveSLA", args=["proof-1-met"])
print(f"    TX: {resolve_tx}")
time.sleep(30)  # Give consensus time to process

# Step 5: Check results
print("\n[5] Verifying results...")
agent_after = read("getAgent", args=[account.address])
sla_after = read("getSLACheck", args=["proof-1-met"])
print(f"    Agent reputation: {agent_after.get('reputation')} (was 0)")
print(f"    SLA verdict: {sla_after.get('verdict')}")
print(f"    SLA recorded: {sla_after.get('recorded')}")

p1_rep = agent_after.get('reputation') == 1
p1_verdict = sla_after.get('verdict') == 'MET'
print(f"\n    RESULT: {'✓ PASS' if p1_rep and p1_verdict else '✗ FAIL'}")

# === Proof 2: SLA BREACHED → stake slashed ===
print("\n" + "="*60)
print("PROOF 2: SLA BREACHED → stake slashed")
print("="*60)

# Use a second agent (different address) or same agent with new SLA
# For simplicity, use same agent with new SLA
# Step 1: Declare SLA with evidence that will be judged as BREACHED
deadline2 = int((datetime.now(timezone.utc) + timedelta(minutes=3)).timestamp())
print(f"\n[1] Declaring SLA-2 (deadline={deadline2})")
print(f"    Evidence: https://example.com (placeholder - insufficient for SLA)")
decl2_tx = write("declareSLA", args=[
    "proof-2-breached",
    "Deliver a complete working software application with source code",
    "https://example.com",
    str(deadline2)
])
print(f"    TX: {decl2_tx}")
time.sleep(2)

sla2_before = read("getSLACheck", args=["proof-2-breached"])
print(f"    SLA: exists={sla2_before.get('exists')}")

# Step 2: Wait for deadline
print(f"\n[2] Waiting for deadline ({datetime.fromtimestamp(deadline2)})...")
while int(datetime.now(timezone.utc).timestamp()) < deadline2:
    time.sleep(2)
print("    Deadline passed!")

# Step 3: Resolve SLA
print("\n[3] resolveSLA — AI consensus evaluates evidence")
resolve2_tx = write("resolveSLA", args=["proof-2-breached"])
print(f"    TX: {resolve2_tx}")
time.sleep(30)

# Step 4: Check results
print("\n[4] Verifying results...")
agent_after2 = read("getAgent", args=[account.address])
sla_after2 = read("getSLACheck", args=["proof-2-breached"])
print(f"    Agent stake: {agent_after2.get('staked')}")
print(f"    Agent reputation: {agent_after2.get('reputation')}")
print(f"    Agent breached: {agent_after2.get('breached')}")
print(f"    SLA verdict: {sla_after2.get('verdict')}")
print(f"    SLA recorded: {sla_after2.get('recorded')}")

p2_verdict = sla_after2.get('verdict') == 'BREACHED'
p2_stake_slashed = agent_after2.get('staked', 0) < agent_after.get('staked', 0)
print(f"\n    RESULT: {'✓ PASS' if p2_verdict and p2_stake_slashed else '✗ FAIL'}")

# === Summary ===
print("\n" + "="*60)
print("SUMMARY")
print("="*60)
print(f"Contract: {CONTRACT}")
print(f"Proof 1 (SLA MET → reputation up): {'✓ PASS' if p1_rep and p1_verdict else '✗ FAIL'}")
print(f"  - Reputation: {agent_after.get('reputation')} (expected 1)")
print(f"  - Verdict: {sla_after.get('verdict')} (expected MET)")
print(f"Proof 2 (SLA BREACHED → stake slashed): {'✓ PASS' if p2_verdict and p2_stake_slashed else '✗ FAIL'}")
print(f"  - Verdict: {sla_after2.get('verdict')} (expected BREACHED)")
print(f"  - Stake: {agent_after2.get('staked')} (was {agent_after.get('staked')})")

# Save proof data
proof_data = {
    "contract": CONTRACT,
    "deploy_tx": deploy_hash,
    "proofs": [
        {
            "type": "SLA_MET_reputation_up",
            "register_tx": reg_tx,
            "declare_tx": decl_tx,
            "resolve_tx": resolve_tx,
            "result": {
                "reputation_before": agent_before.get('reputation'),
                "reputation_after": agent_after.get('reputation'),
                "verdict": sla_after.get('verdict'),
                "passed": p1_rep and p1_verdict
            }
        },
        {
            "type": "SLA_BREACHED_stake_slashed",
            "declare_tx": decl2_tx,
            "resolve_tx": resolve2_tx,
            "result": {
                "stake_before": agent_after.get('staked'),
                "stake_after": agent_after2.get('staked'),
                "verdict": sla_after2.get('verdict'),
                "passed": p2_verdict and p2_stake_slashed
            }
        }
    ]
}
with open("proof_data.json", "w") as f:
    json.dump(proof_data, f, indent=2)
print(f"\nProof data saved to proof_data.json")
