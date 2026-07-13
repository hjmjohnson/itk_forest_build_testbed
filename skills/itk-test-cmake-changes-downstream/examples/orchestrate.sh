#!/usr/bin/env bash
# Validation orchestrator for PR #6489: sweep the fake-consumer family across
# SYSTEM_ZLIB={OFF,ON} x ZLIB-export-variant{C=baseline,A=PR,B=both-empty}
# x {build tree, install tree}.
set -u
ITKSRC=/home/johnsonhj/src/ITK/.claude/worktrees/6489-retain-zlib
M=$ITKSRC/.devlocal/zlib-matrix
Z=$ITKSRC/Modules/ThirdParty/ZLIB/CMakeLists.txt
DRIVER=/home/johnsonhj/src/itk_forest_build_testbed/skills/itk-test-cmake-changes-downstream/bin/run-downstream-matrix.sh
ALL=$M/results.all.tsv
: > "$ALL"
cd "$ITKSRC"

sweep(){ # label build_dir install_prefix
  bash "$DRIVER" --build "$2" --install "$3" --label "$1" --out "$M/res.$1.tsv" \
    > "$M/sweep.$1.log" 2>&1
  tail -n +2 "$M/res.$1.tsv" >> "$ALL"
  echo "  swept $1 (exit via artifact-scoring; see $M/sweep.$1.log)"
}

# Unrelated to the zlib change: the vendored OpenJPEG target exports a stale
# include path (include/itkopenjpeg-2.5) while ITK installs headers under
# include/ITK-6.0. Create the empty dir so this orthogonal install-layout quirk
# does not mask the zlib signal for whole-${ITK_LIBRARIES} consumers.
deopenjpeg(){ mkdir -p "$1/include/itkopenjpeg-2.5"; }

echo "### OFF leg (variant-independent: changed code is in the ON branch) ###"
rm -rf "$M/inst-off"
pixi run cmake --install "$M/build-off" --prefix "$M/inst-off" > "$M/install-off.log" 2>&1
echo "install-off exit=$?"
deopenjpeg "$M/inst-off"
sweep "off" "$M/build-off" "$M/inst-off"

echo "### ON legs: variants C (baseline/main), A (PR/HEAD), B (both-empty) ###"
for V in C A B; do
  cp "$M/ZLIB.variant$V.cmake" "$Z"
  pixi run cmake "$M/build-on" > "$M/reconfigure-on-$V.log" 2>&1   # regen config text only
  echo "reconfigure on-$V exit=$?"
  rm -rf "$M/inst-on-$V"
  pixi run cmake --install "$M/build-on" --prefix "$M/inst-on-$V" > "$M/install-on-$V.log" 2>&1
  echo "install on-$V exit=$?"
  deopenjpeg "$M/inst-on-$V"
  sweep "on-$V" "$M/build-on" "$M/inst-on-$V"
done

# restore source to PR/HEAD
git checkout -- "$Z" 2>/dev/null

echo ""
echo "################# AGGREGATE RESULTS #################"
{ printf 'label\ttree\tconsumer\tresult\n'; cat "$ALL"; } | column -t -s "$(printf '\t')"
