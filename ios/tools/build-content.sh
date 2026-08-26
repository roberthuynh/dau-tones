#!/bin/bash
# Regenerates every bundled content artifact from the repo's authoring source.
# Run after changing api/data/inventory.json or anything under targets/.
#
#   ios/tools/build-content.sh
#
# Order matters: references are built first because build-content marks a word as having
# a reference for an accent only when a usable contour actually exists for it.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ios="$repo_root/ios"
content="$ios/Resources/Content"
fixtures="$ios/DauCore/Tests/DauCoreTests/Fixtures/dau-golden-contours-v1.json"

echo "==> reference contours (Swift analyzer)"
swift run --package-path "$ios/DauCore" dau-tool build-references "$repo_root" "$content" "$fixtures"

echo
echo "==> word inventory"
swift run --package-path "$ios/DauCore" dau-tool build-content "$repo_root" "$content"

echo
echo "==> reference audio -> m4a"
converted=0
skipped=0
for accent in north south; do
    src_dir="$repo_root/targets/$accent"
    out_dir="$content/targets/$accent"
    mkdir -p "$out_dir"
    [ -d "$src_dir" ] || continue
    while IFS= read -r -d '' wav; do
        name="$(basename "$wav" .wav)"
        out="$out_dir/$name.m4a"
        if [ -f "$out" ] && [ "$out" -nt "$wav" ]; then
            skipped=$((skipped + 1))
            continue
        fi
        afconvert -f m4af -d aac -b 64000 "$wav" "$out" >/dev/null
        converted=$((converted + 1))
    done < <(find "$src_dir" -name '*.wav' -print0)
done
echo "converted $converted, up to date $skipped"
du -sh "$content"
