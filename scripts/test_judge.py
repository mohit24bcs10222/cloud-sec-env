"""One-off smoke test for the LLM-as-judge scorer."""
import os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from cloud_sec_env.server.cloud_sec_env_environment import CloudSecEnvironment
from cloud_sec_env.models import CloudSecAction


STRONG_ANSWER = {
    "root_cause": (
        "CHG-1891, applied by j.patel, rotated the OIDC signing key from "
        "rsa-2025-q4 to rsa-2026-q2. The apply succeeded on cloud-1 and "
        "cloud-3 but silently failed on cloud-2 due to Terraform state-lock "
        "contention from m.chen's concurrent run. cloud-2 sts-broker still "
        "has the stale kid=rsa-2025-q4 so Acme JWTs fail signature "
        "verification with kid=rsa-2026-q2 unknown. "
        "The cloud-3 ml-scorer CPU throttling alert (INC-4470) is unrelated."
    ),
    "fix": (
        "Targeted: terraform apply -target=module.cloud_2.sts_broker_keys "
        "to push the new public key. Do NOT roll back globally -- cloud-1 "
        "and cloud-3 are healthy."
    ),
}

WEAK_ANSWER = {
    "root_cause": (
        "CHG-1891 broke the authentication. Something happened with state "
        "lock and the keys did not rotate correctly on cloud-2."
    ),
    "fix": "Re-apply terraform for cloud-2.",
}


def run(label, answer):
    env = CloudSecEnvironment()
    env.reset()
    obs = env.step(CloudSecAction(tool_name="submit_answer", arguments=answer))
    print("=" * 70)
    print(f"{label}:  reward = {obs.reward}")
    print("=" * 70)
    print(obs.content)
    print()


if __name__ == "__main__":
    run("STRONG", STRONG_ANSWER)
    run("WEAK", WEAK_ANSWER)
