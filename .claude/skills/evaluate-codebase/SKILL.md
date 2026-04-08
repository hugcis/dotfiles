---
name: evaluate-codebase
description: Use when asked to evaluate, audit, or assess codebase health — runs git-based analyses for churn, contributors, bug hotspots, velocity, and firefighting, then synthesizes a structured report
---

# Evaluate Codebase

Run 5 git-based analyses in parallel, then synthesize into a structured report.

## Step 0: Detect Commit Convention

Before running analyses, sample recent commits to detect the commit message format. This determines how to identify fix commits and filter noise.

```bash
git log --oneline -50
```

**Detection rules:**
- **Conventional Commits** (`type(scope): description`): If >60% of sampled messages match `^(feat|fix|chore|refactor|build|test|ci|perf|style|docs?|revert)\b`, the repo uses conventional commits.
- **Freeform**: Otherwise, no structured format is assumed.

Based on the result, set two strategies used in analyses below:

| | Conventional Commits | Freeform |
|---|---|---|
| **Fix grep** | `--grep="^fix"` (precise — targets only fix-type commits) | `--grep="fix\|bug\|broken"` with `-i -E` (broad — necessary when messages are unstructured) |
| **Release noise filter** | `--invert-grep --grep="^chore.*release"` | `--invert-grep --grep="release\|bump version"` (adapt to observed patterns) |
| **Firefighting regex** | `'^[a-f0-9]+ (revert\|hotfix\|emergency\|rollback)\|^[a-f0-9]+ \w+\(\w+\): revert'` | `'revert\|hotfix\|emergency\|rollback'` |

Run ALL 5 analyses in parallel using Bash, applying the detected strategy.

### 1. File Churn (last 12 months, filtered)

Most frequently modified files, excluding noise (bots, lock files, changelogs, generated files). Use the release noise filter from Step 0:

```bash
git log --format=format: --name-only --since="1 year ago" \
  ${RELEASE_NOISE_FILTER} \
  | grep -vE '(^$|\.lock$|CHANGELOG|package-lock|\.min\.)' \
  | sort | uniq -c | sort -nr | head -20
```

### 2. Contributor Distribution (humans only)

All-time and last 6 months, excluding bots:

```bash
echo "=== ALL TIME ===" && \
git log --format='%aN' | grep -vE '\[bot\]$' | sort | uniq -c | sort -nr && \
echo "=== LAST 6 MONTHS ===" && \
git log --format='%aN' --since="6 months ago" | grep -vE '\[bot\]$' | sort | uniq -c | sort -nr
```

### 3. Fix-Ratio Hotspots (last 12 months)

Files with highest ratio of fix-commits to total commits (minimum 5 changes). Use the fix grep from Step 0. Fix-ratio is more accurate than raw counts because it filters out registry files that are "along for the ride" in every commit.

```bash
join -t$'\t' \
  <(git log ${FIX_GREP} --name-only --format='' --since="1 year ago" \
    | grep -vE '(^$|\.lock$|CHANGELOG)' | sort | uniq -c \
    | awk '{print $2"\t"$1}' | sort) \
  <(git log --name-only --format='' --since="1 year ago" \
    | grep -vE '(^$|\.lock$|CHANGELOG)' | sort | uniq -c \
    | awk '{print $2"\t"$1}' | sort) \
  | awk -F'\t' '$2 >= 5 {printf "%.0f%%\t%s/%s\t%s\n", ($2/$3)*100, $2, $3, $1}' \
  | sort -nr | head -20
```

**Why fix-ratio matters:** A file with 5 fix commits out of 6 total (83%) is genuinely problematic. A file with 20 fix mentions out of 40 total (50%) in a freeform repo may just be a registry touched by many commits — note this caveat in the report when using the broad grep.

### 4. Commit Velocity (monthly)

```bash
git log --format='%ad' --date=format:'%Y-%m' \
  --invert-grep --grep='\[bot\]' \
  | sort | uniq -c
```

### 5. Firefighting Frequency (last 12 months)

Reverts, hotfixes, and emergency commits. Use the firefighting regex from Step 0:

```bash
git log --oneline --since="1 year ago" | grep -iE ${FIREFIGHTING_REGEX}
```

## Report Format

After collecting results, produce a report with these sections:

### Overview
- Repository age, total commits, number of human contributors
- Get with: `echo "First commit: $(git log --reverse --format='%ai' | head -1)" && echo "Total commits: $(git rev-list --count HEAD)" && echo "Contributors: $(git log --format='%aN' | grep -vE '\[bot\]$' | sort -u | wc -l)" && echo "Files tracked: $(git ls-files | wc -l)"`

### High-Risk Files
- Cross-reference churn list with fix-ratio list
- Files appearing in BOTH are highest risk — high change frequency AND high fix ratio
- **Distinguish genuine hotspots from registry files**: if a file is an `__init__.py`, `sources.yml`, or other registry that gets touched by every feature, note it as "high churn / low intrinsic risk" rather than flagging it as a bug hotspot
- Fix-ratio > 70% with 5+ changes = genuinely problematic file

### Bus Factor
- Identify concentration risk: are 1-2 people responsible for >60% of commits?
- Compare all-time vs recent 6 months — has the team grown, shrunk, or shifted?
- Note contributors who were significant historically but have dropped off

### Project Health Signals
- Group velocity by year, compute average monthly rate per year
- Trend: accelerating / stable / declining
- Firefighting count as percentage of total commits — >2% = concern

### Recommendations
- Prioritized list based on data, not speculation
- Focus on actionable items: what to refactor, test, or document
