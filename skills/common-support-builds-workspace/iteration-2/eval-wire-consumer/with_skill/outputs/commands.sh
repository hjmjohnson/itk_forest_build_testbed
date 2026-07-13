#!/usr/bin/env bash
# commands.sh — Wire pre-built ITK v5.4.2 and VTK v9.4.0 from
# common_support_versions into BRAINSTools CMakeUserPresets.json.
#
# Prerequisites:
#   - ~/src/common_support_versions/ITK/installed_v5.4.2/lib/cmake/ITK-5.4/ exists
#   - ~/src/common_support_versions/VTK/installed_v9.4.0/lib/cmake/vtk-9.4/ exists
#   - ~/src/BRAINSTools/CMakeUserPresets.json exists with a "base_language" preset
#
# Per the skill (SKILL.md step 6), ALWAYS use csv_update_consumer.py —
# do NOT manually edit the consumer's CMakeUserPresets.json.

SKILL_SCRIPTS=~/src/claude-skills/global/skills/common-support-builds/scripts

# -------------------------------------------------------------------
# Step 0: If CMakeUserPresets.json doesn't exist yet, create a minimal
# one with the "base_language" preset that the script expects.
# (Only needed if starting from scratch; skip if the file already exists.)
# -------------------------------------------------------------------
if [ ! -f ~/src/BRAINSTools/CMakeUserPresets.json ]; then
  cat > ~/src/BRAINSTools/CMakeUserPresets.json << 'SEED'
{
  "version": 3,
  "configurePresets": [
    {
      "name": "base_language",
      "displayName": "BRAINSTools with pre-built dependencies",
      "description": "Uses common_support_versions ITK and VTK instead of SuperBuild",
      "inherits": "brainstools_base",
      "generator": "Ninja",
      "binaryDir": "${sourceDir}/cmake-csv-build",
      "cacheVariables": {
        "CMAKE_BUILD_TYPE": {"type": "STRING", "value": "Release"},
        "BRAINSTools_SUPERBUILD": {"type": "BOOL", "value": "OFF"},
        "BRAINSTools_PKGBUILD": {"type": "BOOL", "value": "ON"}
      }
    }
  ]
}
SEED
  echo "Created seed CMakeUserPresets.json with base_language preset"
fi

# -------------------------------------------------------------------
# Step 1: Wire ITK v5.4.2 into the base_language preset
# -------------------------------------------------------------------
python3 "$SKILL_SCRIPTS/csv_update_consumer.py" \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg ITK --tag v5.4.2 \
  --use-system

# -------------------------------------------------------------------
# Step 2: Wire VTK v9.4.0 into the base_language preset
# -------------------------------------------------------------------
python3 "$SKILL_SCRIPTS/csv_update_consumer.py" \
  --consumer-source ~/src/BRAINSTools \
  --preset-name base_language \
  --pkg VTK --tag v9.4.0 \
  --use-system

# -------------------------------------------------------------------
# Step 3: Verify the result
# -------------------------------------------------------------------
echo ""
echo "=== Resulting CMakeUserPresets.json ==="
cat ~/src/BRAINSTools/CMakeUserPresets.json

echo ""
echo "=== Validation: check JSON is well-formed ==="
python3 -m json.tool ~/src/BRAINSTools/CMakeUserPresets.json > /dev/null && echo "JSON OK" || echo "JSON INVALID"

# -------------------------------------------------------------------
# Step 4: Configure BRAINSTools using the new preset
# -------------------------------------------------------------------
echo ""
echo "To configure BRAINSTools with the pre-built dependencies, run:"
echo "  cmake --preset base_language"
echo ""
echo "To build:"
echo "  cmake --build --preset base_language -j\$(sysctl -n hw.logicalcpu)"
