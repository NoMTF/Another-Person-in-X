# 致谢与第三方项目

Another Person in X 本身以 MIT License 开源。第三方项目、平台 API、浏览器插件和系统组件继续遵循它们自己的许可证与服务条款。

本文件列出仓库直接使用、集成、推荐或明确依赖的项目。前端构建的传递依赖以 `assets/web-admin/package-lock.json` 为准，Python 运行时依赖以部署时安装的版本为准。

## 直接运行依赖

| 项目 | 用途 | 许可证/性质 |
| --- | --- | --- |
| OpenClaw | Agent runtime、通道、工具执行、记忆层 | MIT |
| twikit | X/Twitter cookie 模式适配器 | MIT |
| FastAPI | 本地 Admin API | MIT |
| Uvicorn | Admin API ASGI server | BSD-3-Clause |
| Pydantic | API 请求模型和校验 | MIT |
| SQLite / FTS5 | 本地状态库、审计、记忆检索 | Public Domain |
| Python | CLI、安装器、蒸馏器、管理 API | PSF License |

## Web 管理台依赖

| 项目 | 用途 | 许可证/性质 |
| --- | --- | --- |
| React | 管理台 UI | MIT |
| React DOM | 管理台渲染 | MIT |
| Vite | 前端开发与构建 | MIT |
| @vitejs/plugin-react | Vite React 插件 | MIT |
| lucide-react | 管理台图标 | ISC |
| Node.js / npm | 前端构建工具链 | MIT / npm 生态 |

<details>
<summary>assets/web-admin/package-lock.json 中记录的 npm 包</summary>

```text
@babel/code-frame
@babel/compat-data
@babel/core
@babel/generator
@babel/helper-compilation-targets
@babel/helper-globals
@babel/helper-module-imports
@babel/helper-module-transforms
@babel/helper-plugin-utils
@babel/helper-string-parser
@babel/helper-validator-identifier
@babel/helper-validator-option
@babel/helpers
@babel/parser
@babel/plugin-transform-react-jsx-self
@babel/plugin-transform-react-jsx-source
@babel/template
@babel/traverse
@babel/types
@esbuild/aix-ppc64
@esbuild/android-arm
@esbuild/android-arm64
@esbuild/android-x64
@esbuild/darwin-arm64
@esbuild/darwin-x64
@esbuild/freebsd-arm64
@esbuild/freebsd-x64
@esbuild/linux-arm
@esbuild/linux-arm64
@esbuild/linux-ia32
@esbuild/linux-loong64
@esbuild/linux-mips64el
@esbuild/linux-ppc64
@esbuild/linux-riscv64
@esbuild/linux-s390x
@esbuild/linux-x64
@esbuild/netbsd-arm64
@esbuild/netbsd-x64
@esbuild/openbsd-arm64
@esbuild/openbsd-x64
@esbuild/openharmony-arm64
@esbuild/sunos-x64
@esbuild/win32-arm64
@esbuild/win32-ia32
@esbuild/win32-x64
@jridgewell/gen-mapping
@jridgewell/remapping
@jridgewell/resolve-uri
@jridgewell/sourcemap-codec
@jridgewell/trace-mapping
@rolldown/pluginutils
@rollup/rollup-android-arm-eabi
@rollup/rollup-android-arm64
@rollup/rollup-darwin-arm64
@rollup/rollup-darwin-x64
@rollup/rollup-freebsd-arm64
@rollup/rollup-freebsd-x64
@rollup/rollup-linux-arm-gnueabihf
@rollup/rollup-linux-arm-musleabihf
@rollup/rollup-linux-arm64-gnu
@rollup/rollup-linux-arm64-musl
@rollup/rollup-linux-loong64-gnu
@rollup/rollup-linux-loong64-musl
@rollup/rollup-linux-ppc64-gnu
@rollup/rollup-linux-ppc64-musl
@rollup/rollup-linux-riscv64-gnu
@rollup/rollup-linux-riscv64-musl
@rollup/rollup-linux-s390x-gnu
@rollup/rollup-linux-x64-gnu
@rollup/rollup-linux-x64-musl
@rollup/rollup-openbsd-x64
@rollup/rollup-openharmony-arm64
@rollup/rollup-win32-arm64-msvc
@rollup/rollup-win32-ia32-msvc
@rollup/rollup-win32-x64-gnu
@rollup/rollup-win32-x64-msvc
@types/babel__core
@types/babel__generator
@types/babel__template
@types/babel__traverse
@types/estree
@vitejs/plugin-react
baseline-browser-mapping
browserslist
caniuse-lite
convert-source-map
debug
electron-to-chromium
esbuild
escalade
fdir
fsevents
gensync
js-tokens
jsesc
json5
lru-cache
lucide-react
ms
nanoid
node-releases
picocolors
picomatch
postcss
react
react-dom
react-refresh
rollup
scheduler
semver
source-map-js
tinyglobby
update-browserslist-db
vite
yallist
```

</details>

## 集成平台与推荐工具

| 项目/平台 | 用途 | 许可证/性质 |
| --- | --- | --- |
| Telegram Bot API | Telegram bot 收发消息 | 平台 API |
| X/Twitter | 社交平台、官方 API adapter 预留 | 平台服务 |
| Cookie-Editor | 推荐的手动 cookie 查看与 JSON 导出工具 | GPL-3.0 |
| Mermaid | README 架构图 | MIT |
| Shields.io | README 徽章 | 服务/开源项目 |
| systemd | Linux 服务管理模板 | LGPL-2.1+ |
| Docker | 可选部署模式 | Apache-2.0 相关组件 |
| Git / GitHub | 版本管理与代码托管 | GPL-2.0 / 平台 |

## 链接

- OpenClaw: https://github.com/openclaw/openclaw
- twikit: https://pypi.org/project/twikit/
- Telegram Bot API: https://core.telegram.org/bots/api
- Cookie-Editor: https://github.com/Moustachauve/cookie-editor
- FastAPI: https://github.com/fastapi/fastapi
- Uvicorn: https://github.com/Kludex/uvicorn
- Pydantic: https://github.com/pydantic/pydantic
- SQLite: https://www.sqlite.org/
- React: https://github.com/facebook/react
- Vite: https://github.com/vitejs/vite
- Lucide: https://github.com/lucide-icons/lucide
- Mermaid: https://mermaid.js.org/
- Shields.io: https://shields.io/
