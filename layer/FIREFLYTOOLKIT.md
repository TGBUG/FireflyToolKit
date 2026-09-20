# 这篇博客由 FireflyToolKit 管理

FireflyToolKit 给一份原版的 [Firefly](https://github.com/CuteLeaf/Firefly) 博客加上了浏览器编辑和自动部署。它写入的文件列在本文末尾；仓库里其余部分都是上游主题代码，而 `upstream` 指向主题，方便你合并更新。

## 写作

打开 `https://<你的域名>/admin/`，用 GitHub 细粒度 PAT 登录。本地同样可用——`pnpm dev` 起来后访问 `http://localhost:4321/admin/`，选 **Work with Local Development Workflow** 并选中本仓库根目录，不需要令牌，改动直接写到磁盘。

编辑走一套审核流程：保存会新建一条 `cms/posts/<slug>` 分支和一个**草稿** PR；在你发布之前什么都不会进 `master`，发布就是合并那个 PR。

- **保存草稿不花任何代价。** 草稿永远不会被构建，所以你想存多少次都行。
- **发布才是部署。** 合并进 `master` 才会触发构建和部署。

**令牌需要三项权限：`Contents`、`Pull requests`、`Issues`**，都选 read and write。少给 `Issues` 会出现一个很有迷惑性的症状——草稿能正常保存、PR 也开得出来，但一动状态就报「无法更改状态」。因为保存只用到 `POST /issues/N/labels`，而换状态用的是 `PATCH /issues/N`。

## 会让你意外的地方

**一篇文章是一个文件夹，文件夹名就是它的 URL。** 文章位于 `src/content/posts/<slug>/index.md`，图片放在它旁边。所以 `my-post/index.md` 的访问地址是 `/posts/my-post/`。重命名文件夹或 slug 字段会改变 URL，并让已有链接失效。

**`slug` 这个 front-matter 字段不起任何作用。** 这是主题的怪癖：它从文件路径推导 URL，完全忽略 `slug`。但主题自带的 `new-post` 脚本会写这个字段，所以它看起来很像是有效的。忽略它，以文件夹名为准。

**不是文件夹形态的文章在 CMS 里看不见。** CMS 的 collection 是按 page bundle 配的，所以一个扁平的 `src/content/posts/foo.md` 永远不会出现在编辑器里——包括用 `pnpm new-post foo.md` 创建的任何东西。要么在 CMS 里建文章，要么跑 `pnpm new-post foo/index.md`（主题的脚本认结尾的 `/index`）。

**`.mdx` 文章同样看不见**，因为 collection 声明了 `md` 作为扩展名。

**Firefly 的 demo 内容需要手工删掉。** demo 文章和动态都是扁平文件，CMS 看不到它们。配置时从 `src/content/posts/` 和 `src/content/dynamic/` 里删一次即可。

**顺便删掉 `.github/dependabot.yml`。** 主题把它配成**每天**跑一次，而实测单次计费 **10 分钟**——是部署本身的五倍。删掉它只停止**版本更新**，安全更新是设置项、不受影响。

**主题更新可能把 demo 内容重新加回来。** 新增文件不构成冲突，所以会静默合并进来。合并脚本会把上游新增到 `src/content/` 下的内容列出来，让你自己决定。

**管理界面是英文的。** Sveltia 从国内访问不稳定的 CDN 拉取翻译文件，五秒后放弃；它内置的英文字符串完全不需要联网。在设置 → 语言里显式选英文可以让加载变得确定。出于同样的原因，编辑器预览里的代码块可能没有语法高亮——已发布的站点不受影响，因为主题在构建时自己做高亮。

**编辑器里有一个很难发现的左右互换按钮。** 如果发现预览跑到了左边，多半是这个开关被碰到了，不是 bug。

## 更新主题

```bash
bash scripts/fireflytoolkit-merge-upstream.sh
```

它会拉取上游并合并，同时保住你的内容。两件事被显式处理：`src/content/` 里的冲突以本地为准；而 `.github/dependabot.yml` 如果你删过，删除会被保留。

它**刻意不用 `-X ours`**——那个开关会把 `src/config/` 的冲突也一并吞掉，而那些正是你想看的：主题更新在那里新增配置项，你需要决定是否接受。

## 部署

推送到 `master` 会构建站点，把 `dist/` 打包以时间戳为名传到服务器，然后让 `current` 符号链接指向它。不需要重启任何东西。

回滚就是指定一个更早的 release：

```bash
ls ~/fireflyer/releases
bash ~/fireflyer/release.sh 20260919180000
```

回滚只是一次符号链接切换，瞬时完成，不需要重新构建。最近 5 个 release 会被保留，而**正在生效的那个永远不会被清理掉**——回滚之后不会被后续部署误删。

## 仓库 secrets

部署需要四个 secrets（Settings → Secrets and variables → Actions）：

| Secret | 值 |
| --- | --- |
| `VPS_HOST` | 服务器主机名或 IP |
| `VPS_USER` | 非 root 的部署用户 |
| `VPS_SSH_KEY` | 该用户的私钥，**完整内容，且不能带口令**——Actions 的 runner 没法输口令 |
| `VPS_BASE` | 存放 `releases/`、`current` 和 `release.sh` 的目录 |

## 一条自动检查

部署 workflow 在构建之前会跑 `.github/scripts/check-schema.mjs`，比对 `public/admin/config.json` 与主题的 `src/content.config.ts`。

两者不一致时**部署会失败**，并在 Actions 里给出 `::error::` 标注。这是有意的：这类漂移在 CMS 里完全静默——CMS 声明了 schema 里没有的字段时，Zod 会悄悄丢弃它，编辑器显示「已保存」而值其实没了；反过来，schema 要求必填而 CMS 没声明的字段，编辑器根本给不出来。检查放在构建前，几秒就能报错，不用等完整构建。

修好 `config.json` 之后再跑一次配置脚本即可。

## FireflyToolKit 写入的文件

以下全部是新路径——没有一个是主题自带的文件，这正是主题更新不产生冲突的原因。改动其中任何一个，都意味着以后重新初始化时会被覆盖；要改请改 FireflyToolKit 仓库。

```
public/admin/index.html
public/admin/config.json
public/admin/sveltia-cms.js
public/admin/chunks/react-dom.js
.github/workflows/fireflytoolkit-deploy.yml
.github/scripts/check-schema.mjs
deploy/release.sh
scripts/fireflytoolkit-merge-upstream.sh
.node-version
FIREFLYTOOLKIT.md
```
