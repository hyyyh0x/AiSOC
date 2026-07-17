/**
 * `--share` report-card renderer: turns a triage run into a redacted,
 * postable artifact (Markdown + a self-contained SVG card).
 *
 * Privacy: the card contains only aggregate counts and verdict-band metadata —
 * never alert titles, IOCs, hostnames, or usernames. Nothing here can leak
 * environment specifics, so it's safe to post without a redaction review.
 *
 * The SVG format is intentionally identical in spirit to the W3
 * `packages/report-card` web renderer so a CLI card and a dashboard "share
 * results" card look the same. Kept dependency-free so `npx aisoc` stays tiny.
 */

import { writeFile } from "node:fs/promises";
import type { TriageResult } from "./verdict/types.js";

export interface ShareArtifacts {
  markdown: string;
  svg: string;
}

export function renderMarkdownCard(result: TriageResult): string {
  const s = result.summary;
  const seconds = (s.elapsedMs / 1000).toFixed(2);
  return [
    "## AiSOC triage report card",
    "",
    `> ${s.headline}`,
    "",
    "| Metric | Value |",
    "|---|---|",
    `| Alerts triaged | **${s.total}** |`,
    `| Escalated (TP / likely-TP) | **${s.truePositive}** |`,
    `| Needs review | **${s.needsReview}** |`,
    `| Suppressed as noise | **${s.suppressed}** |`,
    `| Noise suppressed | **${s.noisePercent}%** |`,
    `| Wall-clock | **${seconds}s** |`,
    `| Mode | ${result.deterministic ? "deterministic (no LLM key)" : "LLM-assisted"} |`,
    "",
    "Aggregate counts only — no alert content, IOCs, or identities are included.",
    "",
    "Reproduce: `npx aisoc triage --demo`  ·  Open source: https://github.com/beenuar/AiSOC",
    "",
  ].join("\n");
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

/** A 1200×630 share card (X/LinkedIn/Slack unfurl aspect ratio) as standalone SVG. */
export function renderSvgCard(result: TriageResult): string {
  const s = result.summary;
  const seconds = (s.elapsedMs / 1000).toFixed(1);
  const bigNoise = `${s.noisePercent}%`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630" role="img" aria-label="AiSOC triage report card">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#0b1020"/>
      <stop offset="1" stop-color="#131a33"/>
    </linearGradient>
  </defs>
  <rect width="1200" height="630" fill="url(#bg)"/>
  <rect x="0" y="0" width="1200" height="8" fill="#7b2bbe"/>
  <text x="64" y="96" fill="#e6e9f5" font-family="ui-sans-serif,system-ui,Segoe UI,Roboto,Arial" font-size="34" font-weight="700">AiSOC · alert triage</text>
  <text x="64" y="150" fill="#8b93b7" font-family="ui-sans-serif,system-ui,Segoe UI,Roboto,Arial" font-size="24">${esc(result.deterministic ? "deterministic verdict engine · no LLM key" : "LLM-assisted verdict engine")}</text>

  <text x="64" y="300" fill="#22c55e" font-family="ui-sans-serif,system-ui,Segoe UI,Roboto,Arial" font-size="150" font-weight="800">${bigNoise}</text>
  <text x="64" y="356" fill="#8b93b7" font-family="ui-sans-serif,system-ui,Segoe UI,Roboto,Arial" font-size="28">of alert noise suppressed</text>

  <g font-family="ui-sans-serif,system-ui,Segoe UI,Roboto,Arial">
    <text x="64" y="470" fill="#e6e9f5" font-size="30" font-weight="700">${s.total}</text>
    <text x="64" y="506" fill="#8b93b7" font-size="22">triaged</text>
    <text x="320" y="470" fill="#f87171" font-size="30" font-weight="700">${s.truePositive}</text>
    <text x="320" y="506" fill="#8b93b7" font-size="22">escalate</text>
    <text x="560" y="470" fill="#fbbf24" font-size="30" font-weight="700">${s.needsReview}</text>
    <text x="560" y="506" fill="#8b93b7" font-size="22">review</text>
    <text x="800" y="470" fill="#94a3b8" font-size="30" font-weight="700">${s.suppressed}</text>
    <text x="800" y="506" fill="#8b93b7" font-size="22">suppressed</text>
    <text x="1040" y="470" fill="#e6e9f5" font-size="30" font-weight="700">${seconds}s</text>
    <text x="1040" y="506" fill="#8b93b7" font-size="22">elapsed</text>
  </g>

  <text x="64" y="590" fill="#6b7394" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-size="22">npx aisoc triage --demo   ·   github.com/beenuar/AiSOC</text>
</svg>
`;
}

export function renderShareArtifacts(result: TriageResult): ShareArtifacts {
  return { markdown: renderMarkdownCard(result), svg: renderSvgCard(result) };
}

/** Write the share artifacts to disk, returning the paths written. */
export async function writeShareArtifacts(result: TriageResult, basePath: string): Promise<string[]> {
  const { markdown, svg } = renderShareArtifacts(result);
  const mdPath = basePath.endsWith(".md") ? basePath : `${basePath}.md`;
  const svgPath = mdPath.replace(/\.md$/, ".svg");
  await Promise.all([writeFile(mdPath, markdown, "utf8"), writeFile(svgPath, svg, "utf8")]);
  return [mdPath, svgPath];
}
