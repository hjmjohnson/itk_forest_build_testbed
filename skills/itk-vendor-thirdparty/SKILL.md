---
name: itk-vendor-thirdparty
version: 1.0.0
purpose: Maintain an ITK third-party fork (eigen, DCMTK, vxl/VNL, …) and re-vendor it into ITK without creating the branch/tag ref ambiguity that breaks UpdateFromUpstream.sh. Encodes the fork branch-naming convention, the branches-only (never tags) anchor rule, the release-tracking vs. divergent-fork distinction, and the immutable-anchor + protection workflow.
description: Vendor an ITK ThirdParty dependency from its InsightSoftwareConsortium fork. Names overlay anchor branches per ThirdPartyForkConventions.md, forbids same-named tags (which make git checkout/fetch ambiguous), pins by branch name or full SHA in UpdateFromUpstream.sh, and protects each pinned anchor branch.
triggers:
  - itk-vendor-thirdparty
  - /itk-vendor-thirdparty
  - vendor third party into ITK
  - update ITK ThirdParty fork
  - re-vendor VNL / eigen / DCMTK
  - ITK fork branch naming
  - for/itk- branch convention
user_invocable: true
cmd: false
argument_hint: "<project> [--cleanup-tags] [--revendor <sha7>]"
contract:
  inputs:
    - cwd
    - argument
  outputs:
    - stdout
  side_effects:
    writes_to_repo: true
    writes_to_repo_paths:
      - "Modules/ThirdParty/*/UpdateFromUpstream.sh"
    writes_outside_repo: false
    writes_outside_repo_paths: []
    modifies_working_tree: true
    network_required: true
    git_required: true
    user_confirmation_required: true
  determinism: deterministic
  cache:
    has_cache: false
    cache_root:
    schema_version: 0
    rebuildable: true
  derivation:
    has_ai_derived_layer: false
    derivation_version: 0
dependencies:
  skills: []
  external_tools:
    - git
    - gh
  python_packages: []
  scripts: []
deployment:
  tier: project
  target_projects:
    - ITK
    - vxl
  needs_loader_dir: true
  adapters:
    - claude-code
---

# Vendor a Third-Party Dependency into ITK

## Quick reference

If invoked without arguments, print this and ask what the user wants:

```
itk-vendor-thirdparty — maintain an ITK ThirdParty fork and re-vendor it

Usage:
  /itk-vendor-thirdparty <project>                 Audit fork ref hygiene
  /itk-vendor-thirdparty <project> --cleanup-tags  Remove branch/tag ambiguity
  /itk-vendor-thirdparty <project> --revendor <sha7>  Re-pin + re-vendor into ITK

Projects: eigen, DCMTK, vxl (VNL), KWSys, …
```

## Why this skill exists

ITK third-party deps (eigen, DCMTK, vxl→VNL, …) are vendored from forks under
`InsightSoftwareConsortium`. Each fork carries a small ITK overlay. The canonical
rules live in **`Documentation/Maintenance/ThirdPartyForkConventions.md`** (the
default-branch `welcome` README of each fork restates them). This skill encodes
the procedure and — critically — the **two failure modes that broke a real
update** (flagged by @blowekamp on PR #6431, 2026-06-11):

1. **A same-named branch *and* tag on the fork.** ITK's
   `Utilities/Maintenance/update-third-party.bash` does `git checkout "$tag"`.
   If `for/itk-vxl-master-fd75e8b` exists as **both** a branch and a tag, the
   ref is ambiguous — git emits `warning: refname '…' is ambiguous` and may
   resolve the wrong object. **The convention sanctions branches only; never
   create tags that mirror the overlay branch.**
2. **The `<sha7>` in the branch name not identifying the upstream source.** For
   release-tracking forks the doc requires the upstream release-tag commit. See
   the archetype split below — divergent/pruned forks (VNL) are the documented
   exception, not a license to use arbitrary SHAs.

## Fork layout (ThirdPartyForkConventions.md)

- **Default branch `welcome`** — orphan branch, only a `README.md` describing
  the upstream source, the naming convention, and the update steps. GitHub
  renders it on the landing page.
- **Overlay branches** `for/itk-<project>-<version>-<sha7>`:
  - `<project>` — forked project (`eigen`, `dcmtk`, `vxl`).
  - `<version>` — upstream release the overlay is built on (`5.0.1`, `3.7.0`),
    or `master` for a divergent fork (see archetypes).
  - `<sha7>` — see archetypes; identifies *what the overlay sits on*.
- **ITK pins a specific commit, not a moving branch**, so builds are
  reproducible (`UpdateFromUpstream.sh` `tag=`, or `DCMTK_GIT_TAG`).

## Two fork archetypes — get `<version>` and `<sha7>` right

| Archetype | Examples | `<version>` | `<sha7>` | Overlay size |
|---|---|---|---|---|
| **Release-tracking** | eigen, DCMTK | upstream release (`5.0.1`) | **upstream** release-tag commit (`bc3b39870`) | thin |
| **Divergent / pruned** | **vxl → VNL** | `master` | the **overlay-tip** commit on the fork | heavy, long-lived |

Release-tracking forks rebase a thin overlay onto each new upstream release, so
the meaningful identifier *is* the upstream commit. The VNL fork is a
heavily-pruned, numerics-only divergent fork with no upstream release to track;
its only stable identifier is the **overlay-tip SHA** on the fork. This is the
documented exception — record it in the fork's `welcome` README so the SHA
provenance is unambiguous to the next maintainer.

## Hard rules

1. **Branches anchor overlay commits. Never tags.** A tag whose name mirrors an
   overlay branch creates the `git checkout`/`git fetch` ambiguity that breaks
   `update-third-party.bash`. Audit with:
   ```bash
   git ls-remote --tags <fork-remote> 'refs/tags/for/itk*'   # MUST be empty
   ```
2. **Every ITK-pinned SHA has its own immutable, protected branch anchor.** The
   moving `for/itk-<project>-<version>` branch gets rebased; without a dedicated
   `…-<sha7>` branch, a pinned commit can become unreachable. Before deleting
   any tag, confirm reachability:
   ```bash
   git merge-base --is-ancestor <pinned-sha> <moving-branch-tip> && echo reachable
   ```
   If a SHA is pinned by ITK *only* via a tag (no same-name branch), **mint the
   branch first**, then delete the tag — otherwise the pin name stops resolving.
3. **Pin by branch name or full 40-char SHA in `UpdateFromUpstream.sh`.** Never
   pin a tag name. The full SHA is the most robust (immune to any ref collision).
4. **Protect each anchor branch** (`enforce_admins=true`, `allow_force_pushes=false`,
   `allow_deletions=false`) via the GitHub API — send raw JSON with
   `--input file.json` (the `-f required_status_checks=null` form mis-encodes nulls).
5. **Re-vendoring preserves merge topology** — the import is a two-parent merge
   commit; `ghostflow-check-main` validates it. See `ingest-merge-topology.md`.

## Cleanup recipe — remove branch/tag ambiguity (the PR #6431 fix)

When a fork has accumulated `for/itk-*` tags (some mirroring branches):

```bash
FORK=isc                                   # InsightSoftwareConsortium/<project> remote
MOVING=for/itk-<project>-<version>         # e.g. for/itk-vxl-master
TIP=$(git ls-remote --heads $FORK refs/heads/$MOVING | cut -f1)

# 1. For each tagged SHA that ITK pins but has NO same-name branch, mint the branch:
git push $FORK <sha40>:refs/heads/for/itk-<project>-<version>-<sha7>

# 2. Delete every overlay tag (commits stay reachable via branches — verify first):
git push $FORK :refs/tags/for/itk-<project>-<version>-<sha7> [more tags…]

# 3. Verify: no overlay tags remain, every pinned name resolves to exactly one branch:
git ls-remote --tags  $FORK 'refs/tags/for/itk*'    # empty
git ls-remote --heads $FORK 'refs/heads/for/itk*'   # one ref per anchor

# 4. Protect the new anchor branch(es):
cat > /tmp/prot.json <<'EOF'
{"required_status_checks":null,"enforce_admins":true,"required_pull_request_reviews":null,"restrictions":null,"allow_force_pushes":false,"allow_deletions":false}
EOF
gh api -X PUT "repos/InsightSoftwareConsortium/<project>/branches/<urlencoded-branch>/protection" --input /tmp/prot.json
```

URL-encode the `/` in the branch name as `%2F`.

## Re-vendor procedure (`--revendor <sha7>`)

1. On the fork: ensure the overlay tip is committed and a protected
   `for/itk-<project>-<version>-<sha7>` **branch** anchor exists for it.
2. In ITK, branch off `upstream/main`:
   `git checkout -b update-<project>-<sha7> upstream/main`.
3. Edit `Modules/ThirdParty/<Mod>/UpdateFromUpstream.sh` — set
   `readonly tag="for/itk-<project>-<version>-<sha7>"` (branch name or full SHA),
   refresh the trailing patch-list comment.
4. Run the script (it sources `Utilities/Maintenance/update-third-party.bash`):
   it checks out the pinned ref, subtree-merges into `Modules/ThirdParty/<Mod>/src`,
   producing a **two-parent merge** commit.
5. `pre-commit run --all-files` (mandatory before push — `pre-commit-mandatory.md`).
6. Verify topology: `git rev-list --merges upstream/main..HEAD` ≥ 1 and
   `ghostflow-check-main` passes.
7. Push to a fork and open a **draft** PR — only after explicit human request
   (`pr-no-unsolicited.md`, `pr-always-draft.md`).

## Verification checklist

- [ ] `git ls-remote --tags <fork> 'refs/tags/for/itk*'` is empty.
- [ ] Each ITK-pinned SHA (current `UpdateFromUpstream.sh` + any open PR) resolves
      to exactly one branch via `git ls-remote --heads`.
- [ ] Each anchor branch is protected (enforce_admins, no force-push, no deletion).
- [ ] The fork's `welcome` README documents the archetype and SHA provenance.
- [ ] Re-vendor commit is a two-parent merge; `ghostflow-check-main` green.

## Related

- `Documentation/Maintenance/ThirdPartyForkConventions.md` (ITK) — canonical convention.
- `Documentation/Maintenance/UpdatingThirdParty.md` (ITK) — update mechanics.
- Rules: `ingest-merge-topology.md`, `pre-commit-mandatory.md`,
  `pr-no-unsolicited.md`, `pr-always-draft.md`, `pr-force-with-lease.md`.
- Provenance: @blowekamp review on InsightSoftwareConsortium/ITK PR #6431 (2026-06-11).
