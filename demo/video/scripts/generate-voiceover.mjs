import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT_DIR = join(__dirname, "..", "public", "voiceover");

const API_KEY = process.env.ELEVENLABS_API_KEY;
if (!API_KEY) {
  console.error("ELEVENLABS_API_KEY not set");
  process.exit(1);
}

// Adam — deep, neutral, well-suited for tech narration
const VOICE_ID = "pNInz6obpgDQGcFmaJgB";
const MODEL_ID = "eleven_multilingual_v2";

const BEATS = [
  {
    id: "01-hook",
    text: "It's 2 a.m. Production is broken. You have six tools and 30 minutes. Today's AI can usually tell you what's wrong — but can it actually prove it? That's the gap we built an environment to test.",
  },
  {
    id: "02-theme",
    text: "For the OpenEnv hackathon under Theme 3 — professional tasks — we picked the on-call investigation. The capability gap we discovered is specific. Frontier models can name the right cause. What they consistently miss is the senior-engineer move — explicitly ruling out the wrong one. A junior says: it's the database. A senior says: it's the database, and here's why it's not the load balancer. That second sentence is what prevents the wrong fix from going to production.",
  },
  {
    id: "03-environment",
    text: "The agent gets paged with a real-shape alert, six tools across three clouds — logs, metrics, traces, tickets, Slack, runbooks. We hand-authored a real production failure: an OIDC key rotation that silently failed in one cloud due to Terraform state-lock contention. To make it hard, we added a tempting wrong hypothesis — a similar change ticket from the same engineer that produces look-alike warning logs. A shallow agent grabs the first signal. A rigorous one rules out the wrong suspect.",
  },
  {
    id: "04-reward",
    text: "Here's where we put most of our design effort: the reward function. Two genuinely novel ideas. First — trajectory-aware scoring. When the model submits its diagnosis, we cross-check every claim against its actual tool-call history. Hallucinate a correct answer without doing the work — you score zero. Second — falsification reward. The model only gets full credit if it explicitly rules out the alternative hypothesis. To our knowledge no other agentic environment scores either of these. And the rubric is composable: a fast deterministic keyword score as the primary reward — no API key needed, fully reproducible — with an LLM-judge layer for nuance on top. Both run independently. Reproducibility doesn't depend on having a paid API.",
  },
  {
    id: "05-results",
    text: "We harvested 55 high-reward Opus trajectories using the env, fine-tuned Qwen 2.5 7-billion with LoRA — 21 minutes on a single A100. Untuned baseline: 0.05 mean reward, can't even produce valid JSON 70 percent of the time. After SFT: 100 percent submission rate, 0.90 mean terminal reward. That's 95 percent of the way to a frontier model on this task. Same investigation arc, same root cause, same targeted fix. And it's not memorization of the answer — the cumulative reward curve shows the model earning step rewards turn by turn as it actually does the investigation.",
  },
  {
    id: "06-close",
    text: "Why this matters: as AI takes on real diagnostic work — security triage, incident response, debugging — the gap between sounds correct and is provably correct becomes the whole game. Most benchmarks measure outcomes. Ours measures rigor. Trajectory-grounded scoring and falsification rewards aren't specific to cloud security — they transfer to medicine, legal, scientific reasoning, anywhere an agent must justify with evidence. We ship the env, the dataset, the trained adapter, and a reproducible Colab. Cloud Sec Env.",
  },
];

mkdirSync(OUT_DIR, { recursive: true });

for (const beat of BEATS) {
  const out = join(OUT_DIR, `${beat.id}.mp3`);
  if (existsSync(out) && process.env.SKIP_EXISTING === "1") {
    console.log(`skip ${beat.id} (exists)`);
    continue;
  }
  console.log(`generating ${beat.id} (${beat.text.length} chars)...`);

  const res = await fetch(
    `https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`,
    {
      method: "POST",
      headers: {
        "xi-api-key": API_KEY,
        "Content-Type": "application/json",
        Accept: "audio/mpeg",
      },
      body: JSON.stringify({
        text: beat.text,
        model_id: MODEL_ID,
        voice_settings: {
          stability: 0.5,
          similarity_boost: 0.75,
          style: 0.25,
          use_speaker_boost: true,
        },
      }),
    },
  );

  if (!res.ok) {
    const errText = await res.text();
    console.error(`HTTP ${res.status} for ${beat.id}: ${errText}`);
    process.exit(2);
  }

  const buf = Buffer.from(await res.arrayBuffer());
  writeFileSync(out, buf);
  console.log(`  wrote ${out} (${(buf.length / 1024).toFixed(0)} KB)`);
}

console.log("done.");
