#!/usr/bin/env bash
# Mine merged pytest PRs that close an issue and touch both src/ and testing/.
set -euo pipefail
CURSOR=null; PAGES=${PAGES:-10}; OUT=${OUT:-/tmp/prs.jsonl}
: > "$OUT"
for i in $(seq 1 "$PAGES"); do
  RES=$(gh api graphql -f query="
  {repository(owner:\"pytest-dev\",name:\"pytest\"){
    pullRequests(states:MERGED, first:50, orderBy:{field:CREATED_AT,direction:DESC}, after:${CURSOR}){
      pageInfo{hasNextPage endCursor}
      nodes{
        number title mergedAt bodyText
        mergeCommit{oid}
        closingIssuesReferences(first:10){nodes{number title bodyText}}
        files(first:100){nodes{path}}
      }}}}")
  echo "$RES" | jq -c '.data.repository.pullRequests.nodes[]' >> "$OUT"
  HAS=$(echo "$RES" | jq -r '.data.repository.pullRequests.pageInfo.hasNextPage')
  END=$(echo "$RES" | jq -r '.data.repository.pullRequests.pageInfo.endCursor')
  [ "$HAS" = "true" ] || break
  CURSOR="\"$END\""
done
echo "fetched $(wc -l < "$OUT") merged PRs"
