#!/usr/bin/env bash
# 仓库卫生检查。每次 commit 前跑，必须全部 PASS。
#
# 禁用词列表存在 .forbidden-terms（不提交到仓库），每行一个词。
# 这样公开仓库里既没有禁用词本身，也不会广播"要清理什么"。
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1

FAIL=0

# 检查范围 = 实际会被提交的文件（已跟踪 + 未跟踪但未被 gitignore）。
# 被 gitignore 的本地工作文档不在检查范围内——它们不会进公开仓库。
if git rev-parse --git-dir >/dev/null 2>&1; then
  mapfile -t FILES < <(git ls-files --cached --others --exclude-standard \
                       | grep -vE '^(scripts/check-clean\.sh)$')
else
  echo "不是 git 仓库，退出。" >&2
  exit 1
fi

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "没有待检查的文件。"
  exit 0
fi

scan() {     # scan <regex> [额外的排除正则]
  local pat="$1" skip="${2:-}"
  local hits
  hits=$(grep -rniE "$pat" -- "${FILES[@]}" 2>/dev/null || true)
  [ -n "$skip" ] && hits=$(printf '%s\n' "$hits" | grep -viE "$skip" || true)
  printf '%s' "$hits"
}

report() {   # report <name> <matches>
  if [ -z "$2" ]; then
    printf '  PASS  %s\n' "$1"
  else
    printf '  FAIL  %s\n' "$1"
    printf '%s\n' "$2" | sed 's/^/          /'
    FAIL=1
  fi
}

# 拉丁字母的词按「整词」匹配，其余（中文等）仍按子串匹配。
#
# 起因：某个 4 字母的禁用词是普通英文单词的子串，D7 灌完演示数据后在 arXiv 摘要里
# （capacity 之类）误报 36 次，整词匹配则 0 次。一个天天误报的安全网等于没有安全网。
# 边界用 [^A-Za-z0-9] 而不是 \b，所以 host.internal.example 这类点分名字照样命中；
# 代价是刻意拼接（把禁用词嵌进更长的单词里）会漏，那是可接受的取舍。
# 中文没有词边界，\b 对它无意义，所以按原样保留子串匹配。
build_forbidden_pattern() {
  local term parts=() ascii="" other=""
  while IFS= read -r term; do
    term="${term%"${term##*[![:space:]]}"}"      # 去掉行尾空白
    [ -z "$term" ] && continue
    if printf '%s' "$term" | LC_ALL=C grep -qE '^[A-Za-z0-9 ._-]+$'; then
      ascii="${ascii:+$ascii|}$term"
    else
      other="${other:+$other|}$term"
    fi
  done < <(grep -v '^[[:space:]]*#' .forbidden-terms | grep -v '^[[:space:]]*$')

  [ -n "$ascii" ] && parts+=("(^|[^A-Za-z0-9])($ascii)([^A-Za-z0-9]|\$)")
  [ -n "$other" ] && parts+=("($other)")
  local IFS='|'
  printf '%s' "${parts[*]}"
}

echo "== 仓库卫生检查 =="
printf '  范围：%d 个待提交文件\n\n' "${#FILES[@]}"

# 1. 禁用词（前雇主标识等）
if [ -f .forbidden-terms ]; then
  PATTERN=$(build_forbidden_pattern)
  if [ -n "$PATTERN" ]; then
    report "禁用词" "$(scan "$PATTERN")"
  else
    printf '  SKIP  禁用词（.forbidden-terms 为空）\n'
  fi
else
  printf '  WARN  找不到 .forbidden-terms，跳过禁用词检查\n'
fi

# 2. 残留的多 provider 配置（本项目只用 GLM）
report "多 provider 残留" "$(scan 'LLM_PROVIDER' '^docs/')"

# 3. 明文密钥（形如 KEY=<20+ 位随机串>）
report "明文密钥" \
  "$(scan '(SECRET_KEY|API_KEY|CRON_TOKEN|PASSWORD)\s*[:=]\s*["'"'"']?[A-Za-z0-9_-]{20,}' \
          'replace-me|<[^>]+>|example|secrets\.token|\$\{')"

# 4. .env 是否被 git 跟踪
report ".env 未被跟踪" "$(git ls-files | grep -E '(^|/)\.env$' || true)"

# 5. 旧仓库带过来的垃圾文件
report "垃圾文件" "$(ls backend/1.py 'backend/=1.0' backend/.coverage 2>/dev/null || true)"

echo
if [ "$FAIL" -eq 0 ]; then
  echo "全部通过。"
else
  echo "存在问题，修复后再提交。"
fi
exit "$FAIL"
