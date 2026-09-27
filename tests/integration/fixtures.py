"""Expected contract state fixtures for integration tests."""

agent_coordination_contract_schema = {
    "id": 1,
    "jsonrpc": "2.0",
    "result": {
        "ctor": {"kwparams": {}, "params": []},
        "methods": {
            "registerAgent": {
                "kwparams": {},
                "params": [
                    ["capabilities", "string"],
                    ["did_hash", "string"],
                ],
                "readonly": False,
                "ret": "null",
            },
            "postTask": {
                "kwparams": {},
                "params": [
                    ["description", "string"],
                    ["technocore_room", "string"],
                ],
                "readonly": False,
                "ret": "string",
            },
            "claimTask": {
                "kwparams": {},
                "params": [["task_id", "string"]],
                "readonly": False,
                "ret": "null",
            },
            "submitDelivery": {
                "kwparams": {},
                "params": [
                    ["task_id", "string"],
                    ["delivery_url", "string"],
                ],
                "readonly": False,
                "ret": "null",
            },
            "verifyDelivery": {
                "kwparams": {},
                "params": [["task_id", "string"]],
                "readonly": False,
                "ret": "null",
            },
            "resolveDispute": {
                "kwparams": {},
                "params": [["task_id", "string"]],
                "readonly": False,
                "ret": "null",
            },
            "cancelTask": {
                "kwparams": {},
                "params": [["task_id", "string"]],
                "readonly": False,
                "ret": "null",
            },
            "getClaimCount": {
                "kwparams": {},
                "params": [],
                "readonly": True,
                "ret": "string",
            },
            "getTask": {
                "kwparams": {},
                "params": [["task_id", "string"]],
                "readonly": True,
                "ret": "string",
            },
            "getAgent": {
                "kwparams": {},
                "params": [["addr", "string"]],
                "readonly": True,
                "ret": "string",
            },
            "getEmittedTransfers": {
                "kwparams": {},
                "params": [],
                "readonly": True,
                "ret": "string",
            },
            "getExternalTransferLog": {
                "kwparams": {},
                "params": [],
                "readonly": True,
                "ret": "string",
            },
        },
    },
}
