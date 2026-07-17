/**
 * AiSOC GitHub Action entrypoint.
 *
 * Fetches the repo's Dependabot / CodeQL / secret-scanning alerts, triages them
 * with the deterministic AiSOC verdict engine (no LLM, nothing leaves CI), and
 * emits a job summary, a PR comment, or a weekly posture-digest issue.
 */

import * as core from "@actions/core";
import * as github from "@actions/github";
import { triageBatch, type Severity } from "./_vendor/verdict/index.js";

import { fetchAlerts } from "./sources.js";
import { COMMENT_MARKER, renderComment, renderDigest, postureGrade, priorityLine } from "./render.js";

const SEVERITY_ORDER: Severity[] = ["info", "low", "medium", "high", "critical"];

function atLeast(sev: Severity, floor: Severity): boolean {
  return SEVERITY_ORDER.indexOf(sev) >= SEVERITY_ORDER.indexOf(floor);
}

async function run(): Promise<void> {
  const token = core.getInput("github-token") || process.env.GITHUB_TOKEN || "";
  const mode = (core.getInput("mode") || "job-summary").trim();
  const minSeverity = (core.getInput("min-severity") || "low").trim() as Severity;
  const failOn = (core.getInput("fail-on") || "none").trim();
  const sources = (core.getInput("sources") || "dependabot,code-scanning,secret-scanning").split(",").map((s) => s.trim());

  if (!token) {
    core.setFailed("github-token is required (grant security-events:read).");
    return;
  }

  const octokit = github.getOctokit(token);
  const { owner, repo } = github.context.repo;

  core.info(`AiSOC: triaging security signals for ${owner}/${repo} (sources: ${sources.join(", ")})`);
  const { alerts, notes } = await fetchAlerts(octokit as any, owner, repo, sources);

  const filtered = alerts.filter((a) => atLeast(a.severity, minSeverity));
  const result = triageBatch(filtered, { deterministic: true });

  core.setOutput("total", String(result.summary.total));
  core.setOutput("escalate", String(result.summary.truePositive));
  core.setOutput("review", String(result.summary.needsReview));
  core.setOutput("suppress", String(result.summary.suppressed));
  core.setOutput("headline", result.summary.headline);
  core.info(result.summary.headline);

  // Always write a job summary.
  const { grade, score } = postureGrade(result);
  core.summary
    .addHeading("🛡️ AiSOC security triage", 2)
    .addRaw(`\n> ${result.summary.headline}\n\n`)
    .addRaw(`Posture grade: **${grade}** (${score}/100). ${priorityLine(result)}\n\n`);
  if (notes.length) core.summary.addRaw("Notes:\n" + notes.map((n) => `- ${n}`).join("\n") + "\n");
  await core.summary.write();

  if (mode === "pr-comment") {
    await upsertPrComment(octokit, owner, repo, renderComment(result, notes));
  } else if (mode === "digest") {
    await upsertDigestIssue(octokit, owner, repo, renderDigest(result, null, notes));
  }

  if (failOn !== "none") {
    const escalate = result.summary.truePositive;
    const review = result.summary.needsReview;
    const shouldFail = failOn === "true_positive" ? escalate > 0 : failOn === "needs_review" ? escalate + review > 0 : false;
    if (shouldFail) core.setFailed(`AiSOC: ${escalate} act-now + ${review} review findings meet fail-on=${failOn}.`);
  }
}

async function upsertPrComment(octokit: ReturnType<typeof github.getOctokit>, owner: string, repo: string, body: string): Promise<void> {
  const pr = github.context.payload.pull_request?.number;
  if (!pr) {
    core.info("Not a pull_request event; skipping PR comment (job summary written instead).");
    return;
  }
  try {
    const { data: comments } = await octokit.rest.issues.listComments({ owner, repo, issue_number: pr, per_page: 100 });
    const existing = comments.find((c) => c.body?.includes(COMMENT_MARKER));
    if (existing) {
      await octokit.rest.issues.updateComment({ owner, repo, comment_id: existing.id, body });
    } else {
      await octokit.rest.issues.createComment({ owner, repo, issue_number: pr, body });
    }
  } catch (err: any) {
    core.warning(`Could not post PR comment (${err?.message ?? "error"}); the job summary still has the results.`);
  }
}

async function upsertDigestIssue(octokit: ReturnType<typeof github.getOctokit>, owner: string, repo: string, body: string): Promise<void> {
  const title = "🛡️ AiSOC weekly security posture";
  try {
    const { data: issues } = await octokit.rest.issues.listForRepo({ owner, repo, state: "open", labels: "aisoc-digest", per_page: 10 });
    if (issues[0]) {
      await octokit.rest.issues.update({ owner, repo, issue_number: issues[0].number, body });
    } else {
      await octokit.rest.issues.create({ owner, repo, title, body, labels: ["aisoc-digest"] });
    }
  } catch (err: any) {
    core.warning(`Could not create/update the digest issue (${err?.message ?? "error"}).`);
  }
}

run().catch((err) => core.setFailed(err instanceof Error ? err.message : String(err)));
