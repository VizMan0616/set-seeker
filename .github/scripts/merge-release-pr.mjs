# Shared logic for release-gate-*.yml workflows.
# Usage: node .github/scripts/merge-release-pr.mjs <weekly|monthly|hotfix>

const mode = process.argv[2];
if (!["weekly", "monthly", "hotfix"].includes(mode)) {
  console.error("Usage: merge-release-pr.mjs <weekly|monthly|hotfix>");
  process.exit(1);
}

const token = process.env.GITHUB_TOKEN;
const repoFull = process.env.GITHUB_REPOSITORY;
if (!token || !repoFull) {
  console.error("GITHUB_TOKEN and GITHUB_REPOSITORY are required");
  process.exit(1);
}

const [owner, repo] = repoFull.split("/");
const releaseBranchPrefix = "release-please--branches--main";

async function gh(path, options = {}) {
  const res = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      ...(options.headers || {}),
    },
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`GitHub API ${path} failed (${res.status}): ${body}`);
  }
  return res.status === 204 ? null : res.json();
}

function parseVersion(text) {
  const match = text.match(/(\d+\.\d+\.\d+)/);
  return match ? match[1] : null;
}

function bumpType(oldVersion, newVersion) {
  const [oMaj, oMin, oPat] = oldVersion.split(".").map(Number);
  const [nMaj, nMin, nPat] = newVersion.split(".").map(Number);
  if (nMaj > oMaj) return "major";
  if (nMin > oMin) return "minor";
  if (nPat > oPat) return "patch";
  return "none";
}

async function main() {
  const prs = await gh(
    `/repos/${owner}/${repo}/pulls?state=open&base=main&per_page=100`,
  );
  const releasePr = prs.find((pr) => pr.head.ref.startsWith(releaseBranchPrefix));
  if (!releasePr) {
    console.log("No open release-please PR — nothing to merge.");
    return;
  }

  const newVersion = parseVersion(releasePr.title);
  if (!newVersion) {
    console.error(`Cannot parse version from PR title: ${releasePr.title}`);
    process.exit(1);
  }

  const tags = await gh(`/repos/${owner}/${repo}/tags?per_page=1`);
  const oldVersion =
    tags.length > 0 ? parseVersion(tags[0].name) || "0.0.0" : "0.0.0";
  const bump = bumpType(oldVersion, newVersion);

  console.log(
    `Release PR #${releasePr.number}: ${oldVersion} -> ${newVersion} (${bump})`,
  );

  let shouldMerge = false;
  if (mode === "hotfix") {
    shouldMerge = true;
  } else if (mode === "weekly") {
    shouldMerge = bump === "patch";
  } else if (mode === "monthly") {
    shouldMerge = bump !== "none";
  }

  if (!shouldMerge) {
    console.log(`Skipping merge (${mode} gate, bump is ${bump}).`);
    return;
  }

  await gh(`/repos/${owner}/${repo}/pulls/${releasePr.number}/merge`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      merge_method: "merge",
      commit_title: releasePr.title,
    }),
  });
  console.log(`Merged release PR #${releasePr.number}.`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
