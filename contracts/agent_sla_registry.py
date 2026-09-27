# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from genlayer import *

# Agent SLA Registry — agent capability registration with stake-backed
# SLA promises, AI-consensus adjudication, and stake-weighted slashing.
#
# Unlike TruthOracle (which verifies factual claims), this verifies agent
# BEHAVIOR: did the agent deliver what it promised? The consensus judges
# evidence against a behavioral obligation — a fundamentally different
# question from "is this claim true?"
#
# Time handling follows docs.genlayer.com "Transaction Context": the GenVM
# clock is pinned to the transaction datetime and is identical across
# validators, so int(datetime.now(timezone.utc).timestamp()) is deterministic.
#
# GENLAYER-CENTRAL MECHANISM: the _verify_sla method uses gl.nondet.web.render
# to fetch evidence and gl.nondet.exec_prompt to run AI judgment, then applies
# the comparative consensus pattern (leader_fn + validator_fn) from the
# GenLayer docs — this is what makes GenLayer essential here. A rule engine
# can check a deadline timestamp; only AI consensus can judge whether the
# evidence proves the SLA was fulfilled.

@allow_storage
@dataclass
class SLA:
    agent: str
    description: str
    evidence_url: str
    window_end: u256          # Unix seconds — deadline
    recorded: bool
    verdict: str
    triggered_at: u256


@allow_storage
@dataclass
class AgentRecord:
    capabilities: str
    staked: u256              # live stake; only value slashing debits
    reputation: u256          # completed SLAs count
    breached: u256            # breached SLAs count
    slashed_count: u256
    slashed_total: u256       # cumulative record; never re-subtracted


MIN_STAKE = 1000000000000000000        # 1 GEN
SLASH_PCT = 50                          # 50% slash on breach
ALLOWED = ("MET", "BREACHED", "INSUFFICIENT-EVIDENCE")


def _now() -> int:
    return int(datetime.now(timezone.utc).timestamp())


class AgentSLARegistry(gl.Contract):
    """Agent capability + SLA registry with AI-consensus adjudication."""

    agents: TreeMap[str, AgentRecord]
    slas: TreeMap[str, SLA]
    used_evidence: TreeMap[str, str]

    def __init__(self):
        pass

    # ---------- time (deterministic per Transaction Context docs) ----------
    # _now() is module-level (lines 55-56); tests expose it as now() via view

    # ---------- agent registration ----------

    @gl.public.write
    def registerAgent(self, capabilities: str) -> None:
        """Register as an agent with declared capabilities. Requires 1 GEN stake."""
        sender = gl.message.sender_address.as_hex
        if int(gl.message.value) < MIN_STAKE:
            raise gl.vm.UserError("Stake below minimum (1 GEN)")
        rec = self.agents.get(sender, None)
        if rec is None:
            rec = AgentRecord(
                capabilities=capabilities,
                staked=u256(0),
                reputation=u256(0),
                breached=u256(0),
                slashed_count=u256(0),
                slashed_total=u256(0),
            )
        rec.staked = u256(int(rec.staked) + int(gl.message.value))
        rec.capabilities = capabilities
        self.agents[sender] = rec

    @gl.public.write
    def addStake(self, capabilities: str) -> None:
        """Add more stake to an existing registration (also updates capabilities)."""
        sender = gl.message.sender_address.as_hex
        if int(gl.message.value) < MIN_STAKE:
            raise gl.vm.UserError("Stake below minimum (1 GEN)")
        rec = self.agents.get(sender, None)
        if rec is None:
            raise gl.vm.UserError("Agent not registered")
        rec.staked = u256(int(rec.staked) + int(gl.message.value))
        rec.capabilities = capabilities
        self.agents[sender] = rec

    @gl.public.write
    def unregisterAgent(self) -> None:
        """Remove registration. Stake remains locked until all SLAs are settled."""
        sender = gl.message.sender_address.as_hex
        rec = self.agents.get(sender, None)
        if rec is None:
            raise gl.vm.UserError("Agent not registered")
        # Check no open SLAs
        for sla in self.slas.values():
            if sla.agent == sender and not sla.recorded:
                raise gl.vm.UserError("Agent has unrecorded SLAs")
        del self.agents[sender]

    # ---------- SLA declaration ----------

    @gl.public.write
    def declareSLA(self, sla_id: str, description: str,
                   evidence_url: str, window_end: int) -> None:
        """Declare an SLA promise with an evidence URL and a deadline (Unix seconds)."""
        sender = gl.message.sender_address.as_hex
        if self.agents.get(sender, None) is None:
            raise gl.vm.UserError("Agent not registered")
        if self.slas.get(sla_id, None) is not None:
            raise gl.vm.UserError(f"SLA {sla_id} already exists")
        if not evidence_url.startswith("http"):
            raise gl.vm.UserError("evidence_url must be http(s)")
        if self.used_evidence.get(evidence_url, "") == "1":
            raise gl.vm.UserError(f"Evidence URL {evidence_url} already used")
        if int(window_end) <= _now():
            raise gl.vm.UserError("window_end must be in the future")
        self.slas[sla_id] = SLA(
            agent=sender,
            description=description,
            evidence_url=evidence_url,
            window_end=u256(int(window_end)),
            recorded=False,
            verdict="",
            triggered_at=u256(0),
        )
        self.used_evidence[evidence_url] = "1"

    # ---------- consensus verification ----------

    def _verify_sla(self, sla: SLA) -> str:
        """AI-consensus verification of whether the SLA was met.

        Uses the comparative consensus pattern (leader_fn + validator_fn) from
        GenLayer docs: the leader fetches evidence and runs AI judgment, then
        each validator reproduces the same deterministic outcome and agrees only
        when it matches.
        """
        def work() -> dict:
            try:
                evidence = gl.nondet.web.render(sla.evidence_url, mode="text")
            except Exception:
                raise gl.vm.UserError("EVIDENCE_UNREACHABLE")
            if not evidence:
                return {"verdict": "INSUFFICIENT-EVIDENCE",
                        "reason": "Evidence fetch returned empty content"}
            prompt = (
                f"SLA Description: {sla.description}\n"
                f"Evidence from {sla.evidence_url}:\n\n{evidence[:6000]}\n\n"
                f"Was the agent's SLA obligation fulfilled? "
                f"Respond as JSON: "
                f'{{"verdict": "MET"|"BREACHED"|"INSUFFICIENT-EVIDENCE", '
                f'"reason": "..."}}.'
            )
            res = gl.nondet.exec_prompt(prompt, response_format="json")
            verdict = (res.get("verdict") or "").strip().upper()
            if verdict not in ALLOWED:
                raise gl.vm.UserError("MALFORMED_VERDICT")
            return {"verdict": verdict, "reason": res.get("reason", "")}

        def validator(leaders_res) -> bool:
            if not isinstance(leaders_res, gl.vm.Return):
                leader_msg = getattr(leaders_res, "message", "")
                try:
                    work()
                    return False            # leader errored, validator succeeded
                except gl.vm.UserError as e:
                    return str(e.message) == str(leader_msg)
                except Exception:
                    return False
            try:
                mine = work()
            except Exception:
                return False
            return mine.get("verdict", "") == leaders_res.calldata.get("verdict", "")

        try:
            verified = gl.vm.run_nondet_unsafe(work, validator)
        except gl.vm.UserError as e:
            raise gl.vm.UserError(f"SLA verification failed: {e.message}")
        return verified.get("verdict", "INSUFFICIENT-EVIDENCE")

    # ---------- SLA resolution ----------

    @gl.public.write
    def resolveSLA(self, sla_id: str) -> str:
        """Verify the SLA evidence and update reputation/stake.

        Agent before the deadline; ANYONE once it has passed.
        """
        sender = gl.message.sender_address.as_hex
        sla = self.slas.get(sla_id, None)
        if sla is None:
            raise gl.vm.UserError(f"SLA {sla_id} not found")
        if sla.recorded:
            raise gl.vm.UserError(f"SLA {sla_id} already recorded")
        expired = _now() >= int(sla.window_end)
        if not expired and sender != sla.agent:
            raise gl.vm.UserError(
                "Before the deadline only the agent may resolve")
        rec = self.agents.get(sla.agent, None)
        if rec is None:
            raise gl.vm.UserError("Agent not registered")
        verdict = self._verify_sla(sla)
        if verdict == "MET":
            rec.reputation = u256(int(rec.reputation) + 1)
        elif verdict == "BREACHED":
            rec.breached = u256(int(rec.breached) + 1)
            slashed = (int(rec.staked) * SLASH_PCT) // 100
            if slashed > int(rec.staked):
                slashed = int(rec.staked)
            rec.staked = u256(int(rec.staked) - slashed)
            rec.slashed_count = u256(int(rec.slashed_count) + 1)
            rec.slashed_total = u256(int(rec.slashed_total) + slashed)
        # INSUFFICIENT-EVIDENCE: no slash, just record
        sla.recorded = True
        sla.verdict = verdict
        sla.triggered_at = u256(_now())
        self.slas[sla_id] = sla
        self.agents[sla.agent] = rec
        return verdict

    @gl.public.write
    def resolveExpired(self, sla_id: str) -> str:
        """Permissionlessly settle an abandoned SLA as BREACHED after its deadline,
        so silence is not an escape from an unfavourable verdict."""
        sla = self.slas.get(sla_id, None)
        if sla is None:
            raise gl.vm.UserError(f"SLA {sla_id} not found")
        if sla.recorded:
            raise gl.vm.UserError(f"SLA {sla_id} already recorded")
        if _now() < int(sla.window_end):
            raise gl.vm.UserError("Deadline has not passed yet")
        rec = self.agents.get(sla.agent, None)
        if rec is None:
            raise gl.vm.UserError("Agent not registered")
        rec.breached = u256(int(rec.breached) + 1)
        slashed = (int(rec.staked) * SLASH_PCT) // 100
        if slashed > int(rec.staked):
            slashed = int(rec.staked)
        rec.staked = u256(int(rec.staked) - slashed)
        rec.slashed_count = u256(int(rec.slashed_count) + 1)
        rec.slashed_total = u256(int(rec.slashed_total) + slashed)
        sla.recorded = True
        sla.verdict = "BREACHED"
        sla.triggered_at = u256(_now())
        self.slas[sla_id] = sla
        self.agents[sla.agent] = rec
        return "BREACHED"

    # ---------- views ----------

    @gl.public.view
    def now(self) -> str:
        return str(_now())

    @gl.public.view
    def getAgent(self, addr) -> str:
        if isinstance(addr, Address):
            agent_hex = addr.as_hex
        else:
            agent_hex = Address(addr).as_hex
        rec = self.agents.get(agent_hex, None)
        if rec is None:
            return json.dumps({
                "exists": False, "capabilities": "", "staked": 0,
                "reputation": 0, "breached": 0, "slashed_count": 0,
                "slashed_total": 0,
            })
        return json.dumps({
            "exists": True,
            "capabilities": rec.capabilities,
            "staked": int(rec.staked),
            "reputation": int(rec.reputation),
            "breached": int(rec.breached),
            "slashed_count": int(rec.slashed_count),
            "slashed_total": int(rec.slashed_total),
        })

    @gl.public.view
    def getAgentReputation(self, addr) -> str:
        if isinstance(addr, Address):
            agent_hex = addr.as_hex
        else:
            agent_hex = Address(addr).as_hex
        rec = self.agents.get(agent_hex, None)
        if rec is None:
            return json.dumps({"exists": False, "reputation": 0})
        return json.dumps({
            "exists": True,
            "reputation": int(rec.reputation),
            "breached": int(rec.breached),
            "score": int(rec.reputation) * 100 // (
                int(rec.reputation) + int(rec.breached) + 1
            ),
        })

    @gl.public.view
    def getSLACheck(self, sla_id: str) -> str:
        sla = self.slas.get(sla_id, None)
        if sla is None:
            return json.dumps({"exists": False})
        return json.dumps({
            "exists": True,
            "sla_id": sla_id,
            "agent": sla.agent,
            "description": sla.description,
            "evidence_url": sla.evidence_url,
            "window_end": int(sla.window_end),
            "recorded": sla.recorded,
            "verdict": sla.verdict,
            "triggered_at": int(sla.triggered_at) if sla.triggered_at > 0 else 0,
            "expired": _now() >= int(sla.window_end),
        })

    @gl.public.view
    def getSLAs(self, agent) -> str:
        if isinstance(agent, Address):
            agent_hex = agent.as_hex
        else:
            agent_hex = Address(agent).as_hex
        result = []
        for sla_id, sla in self.slas.items():
            if sla.agent == agent_hex:
                result.append({
                    "sla_id": sla_id,
                    "description": sla.description,
                    "evidence_url": sla.evidence_url,
                    "window_end": int(sla.window_end),
                    "recorded": sla.recorded,
                    "verdict": sla.verdict,
                })
        return json.dumps(result)
