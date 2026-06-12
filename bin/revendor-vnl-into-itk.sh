#!/usr/bin/env bash
# revendor-vnl-into-itk.sh — regenerate the ITK PR #6421 branch
# (hjmjohnson:update-vnl-stripped-vxl) that re-vendors the numerics-only stripped
# vxl into ITK's Modules/ThirdParty/VNL, on top of the latest upstream/main.
#
# Usage:
#   ./revendor-vnl-into-itk.sh <isc-vxl-tag>      # build the branch locally
#   PUSH=1 ./revendor-vnl-into-itk.sh <isc-vxl-tag>   # also force-push to the PR
#
# Prerequisite: the vxl snapshot must already be pushed to
#   InsightSoftwareConsortium/vxl as a tag (e.g. for/itk-vxl-master-272c3f1).
#   (cd ~/src/vxl && git push isc for/itk-vxl-master && git push isc <tag>)
#
# The recipe = latest main + three cherry-picks + an ISC "bridge" + the import:
#   Point      de25652298  ENH: Point VNL UpdateFromUpstream … (ISC ownership)
#   Simplify   6c24b58a5f  ENH: Simplify VNL module config …
#   Wrapper    tag itk-vnl-stripped-wrapper-cleanup
#                          ENH: Stop forcing VXL options removed from stripped vxl
#   Bridge     empty ISC-authored "VXL <date> (<hash>)" so UpdateFromUpstream
#              chains (no ghostflow root-commit error); see the memory note
#              itk-thirdparty-ownership-bridge.
# Once a stripped ISC import lands on main, the bridge becomes unnecessary
# (basehash will find that import); the script skips it automatically then.
set -euo pipefail

ITK_TAG="${1:?usage: revendor-vnl-into-itk.sh <isc-vxl-tag>}"
ITK_REPO="${ITK_REPO:-${HOME}/src/ITK}"
WT="${WT:-/tmp/revendor-vnl}"
UPSTREAM="${UPSTREAM:-upstream}"          # InsightSoftwareConsortium/ITK
FORK="${FORK:-origin}"                    # hjmjohnson/ITK (PR head)
PR_BRANCH="update-vnl-stripped-vxl"
ISC='Insight Software Consortium Maintainers <https://discourse.itk.org/>'
POINT=de256522987189968f0b8b9405e8920e42ef8ee8
SIMPLIFY=6c24b58a5f92d396192a5185e987df6916bb117c
WRAPPER=itk-vnl-stripped-wrapper-cleanup

cd "${ITK_REPO}"
git fetch "${UPSTREAM}" --quiet
git worktree remove "${WT}" --force 2>/dev/null || true; rm -rf "${WT}"
git branch -D revendor-vnl-tmp 2>/dev/null || true
git worktree add -b revendor-vnl-tmp "${WT}" "${UPSTREAM}/main" >/dev/null
cd "${WT}"

# 1. Point — set repo=isc + ISC ownership, bump the tag to this snapshot.
git cherry-pick "${POINT}" >/dev/null
perl -0pi -e "s|^readonly tag=.*|readonly tag=\"${ITK_TAG}\" # $(date +%Y-%m-%d)|m" Modules/ThirdParty/VNL/UpdateFromUpstream.sh
git commit -q --no-verify -a --amend --no-edit

# 2. Bridge — only if main has no ISC-authored "VXL …" import to chain onto.
if ! git rev-list --author="${ISC}" --grep='^VXL 20[0-9][0-9]' -n1 HEAD | grep -q .; then
  bridge_subject="$(git log -1 --format='%s' "${UPSTREAM}/main" --grep='^VXL ')"
  GIT_AUTHOR_NAME='Insight Software Consortium Maintainers' \
  GIT_AUTHOR_EMAIL='https://discourse.itk.org/' \
  git commit -q --no-verify --allow-empty -m "${bridge_subject}" \
    -m "Bridge commit (no content change): re-attribute the vendored VNL import
lineage to the ISC maintainers so UpdateFromUpstream chains onto it instead of a
root-commit initial import."
fi

# 3. Simplify the VNL wrapper, 4. drop the now-dead forced VXL options.
git cherry-pick "${SIMPLIFY}" >/dev/null
git cherry-pick "${WRAPPER}" >/dev/null

# 5. Run the subtree import (basehash = the ISC marker -> chained, no root commit).
( cd Modules/ThirdParty/VNL && bash ./UpdateFromUpstream.sh ) || true   # final commit may trip pre-commit
# Resolve any vendored-subtree conflicts in favor of the stripped upstream.
for f in $(git diff --name-only --diff-filter=U | grep '^Modules/ThirdParty/VNL/src/vxl/' || true); do
  if git show ":3:$f" >/dev/null 2>&1; then git checkout --theirs -- "$f" && git add "$f"
  else git rm -q "$f"; fi
done
[ -f "$(git rev-parse --git-dir)/MERGE_HEAD" ] && git commit --no-verify --no-edit >/dev/null
git commit --amend --no-verify -m "Merge branch 'upstream-VXL' into ${PR_BRANCH}" >/dev/null

# Sanity: no root commit may exist in the PR range.
if git rev-list --max-parents=0 "${UPSTREAM}/main"..HEAD | grep -q .; then
  echo "ERROR: a root commit exists in the PR range (ghostflow would reject it)"; exit 1
fi
PATH="/usr/bin:${PATH}" pre-commit run --all-files

echo
echo "Built ${PR_BRANCH} at $(git rev-parse --short HEAD) (vxl ${ITK_TAG}):"
git log --oneline "${UPSTREAM}/main"..HEAD | cat
if [ "${PUSH:-0}" = 1 ]; then
  lease="$(git ls-remote "${FORK}" "refs/heads/${PR_BRANCH}" | cut -f1)"
  git push --force-with-lease="${PR_BRANCH}:${lease}" "${FORK}" "HEAD:${PR_BRANCH}"
else
  echo
  echo "Review, then push with:"
  echo "  PUSH=1 $0 ${ITK_TAG}    # or push manually with --force-with-lease"
fi
