#!/usr/bin/env sh
set -eu

no_sample=0
prepare_only=0
for argument in "$@"; do
  case "$argument" in
    --no-sample) no_sample=1 ;;
    --prepare-only) prepare_only=1 ;;
    -h|--help)
      echo '用法：sh scripts/start-avatar3d.sh [--no-sample] [--prepare-only]'
      echo '--no-sample：跳过内置人物下载，在页面导入自己的 GLB。'
      echo '--prepare-only：只准备资源和前端依赖，不启动浏览器。'
      exit 0 ;;
    *) echo "不支持的参数：$argument" >&2; exit 2 ;;
  esac
done

project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$project_dir"
command -v node >/dev/null 2>&1 || { echo '请先安装 Node.js（建议使用 Node.js 24）。' >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo '请先安装可运行的 Python 3.10 或更新版本。' >&2; exit 1; }
node -e 'const [m,n]=process.versions.node.match(/[0-9]+/g).map(Number); if (!((m===20&&n>=19)||(m===22&&n>=12)||m>=24)) process.exit(1)' || {
  echo 'Node.js 版本不符合前端依赖要求，请使用 Node.js 24，或 20.19+/22.12+。' >&2
  exit 1
}
if command -v npm >/dev/null 2>&1; then
  package_manager=npm
elif command -v pnpm >/dev/null 2>&1; then
  package_manager=pnpm
else
  echo '未找到 npm 或 pnpm，请检查 Node.js 包管理器安装。' >&2
  exit 1
fi
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' || {
  echo 'Python 3 无法运行或版本低于 3.10。' >&2
  exit 1
}

if [ "$no_sample" -eq 1 ]; then
  python3 scripts/avatar3d_setup.py --no-sample
else
  python3 scripts/avatar3d_setup.py
fi
cd "$project_dir/web"
echo '安装锁定的前端依赖（首次准备需要联网）。'
if [ "$package_manager" = npm ]; then
  npm ci
else
  pnpm install --frozen-lockfile
fi
if [ "$prepare_only" -eq 1 ]; then
  echo "准备完成。需要启动时，在 web 目录运行 $package_manager run avatar3d。"
  exit 0
fi
echo '启动本地 3D 页：http://127.0.0.1:5173/avatar3d'
echo '关闭本终端或按 Ctrl+C 停止。此命令不会开直播或调用付费接口。'
exec "$package_manager" run avatar3d
