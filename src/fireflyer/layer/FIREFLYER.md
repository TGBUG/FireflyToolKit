# 这篇博客由 Fireflyer 管理

Fireflyer 给一份原版的 [Firefly](https://github.com/CuteLeaf/Firefly) 博客加上了浏览器编辑和自动部署。它新增的文件列在本文末尾；仓库里其余部分都是上游主题代码，而 `upstream` 指向主题，方便你合并更新。

## 写作

打开 `https://<你的域名>/admin/`，用 GitHub 细粒度 PAT 登录。同一个页面在本地也有效——`pnpm dev` 跑起来后访问 `http://localhost:4321/admin/`，选 **Work with Local Development Workflow** 并选中本仓库根目录，不需要令牌，改动直接写到磁盘。

编辑走一套审核流程：保存一个条目会新建一条 `cms/posts/<slug>` 分支和一个**草稿** PR；在你发布之前什么都不会进 `master`，发布就是合并那个 PR。由此有两个后果值得知道：

- **保存草稿不花任何代价。** 草稿永远不会被构建，所以你想存多少次都行。
- **发布才是部署。** 合并进 `master` 才会触发构建和部署。

修改一篇已发布的文章同样会走 PR。这是有意的：它让「做出改动」和「发布改动」保持分离。

## 会让你意外的地方

**一篇文章是一个文件夹，文件夹名就是它的 URL。** 文章位于 `src/content/posts/<slug>/index.md`，图片放在它旁边。所以 `my-post/index.md` 的访问地址是 `/posts/my-post/`。重命名文件夹或 slug 字段会改变 URL，并让已有链接失效。

**`slug` 这个 front-matter 字段不起任何作用。** 这是主题的怪癖，不是 Fireflyer 的：主题从文件路径推导 URL，完全忽略 `slug`。但主题自带的 `new-post` 脚本会写这个字段，所以它看起来很像是有效的。忽略它，以文件夹名为准。

**不是文件夹形态的文章在 CMS 里看不见。** CMS 的 collection 是按 page bundle 配的，所以一个扁平的 `src/content/posts/foo.md` 永远不会出现在编辑器里——包括用 `pnpm new-post foo.md` 创建的任何东西。要么在 CMS 里建文章，要么跑 `pnpm new-post foo/index.md`（主题的脚本认结尾的 `/index`）。

**`.mdx` 文章同样看不见**，因为 collection 声明了 `md` 作为扩展名。

**Firefly 的 demo 内容需要手工删掉。** demo 文章和动态都是扁平文件，CMS 看不到它们。配置时从 `src/content/posts/` 和 `src/content/dynamic/` 里删一次即可。

**每次全新克隆之后，合并驱动都要重新建立。** `src/content/.gitattributes` 把你的内容标记为 `merge=ours`，这样主题更新就无法覆盖它；但那个名字定义在 `.git/config` 里，而 git 从不提交这个文件。在新机器上克隆本仓库之后，从 Fireflyer 检出里跑 `fireflyer inject .`，或手工执行 `git config merge.ours.driver true`。

**主题更新可能把 demo 内容重新加回来。** 新增文件不构成冲突，所以会静默合并进来。`scripts/fireflyer-merge-upstream.sh` 会列出上游新增到 `src/content/` 下的所有内容，让你自己决定。

**管理界面是英文的。** Sveltia 从国内访问不稳定的 CDN 拉取翻译文件，五秒后放弃；它内置的英文字符串完全不需要联网，所以英文是最快的路径。在设置 → 语言里显式选英文可以让加载变得确定。出于同样的原因，编辑器预览里的代码块可能没有语法高亮——已发布的站点不受影响，因为主题在构建时自己做高亮。

**编辑器里有一个很难发现的左右互换按钮。** Sveltia 的编辑器设有切换两栏左右的开关，但位置不显眼、官方文档也没写。如果发现预览跑到了左边，多半是这个开关被碰到了——找到它切回来即可，这不是 bug。

**如果切换状态时报「无法更改状态」，检查 token 的 Issues 权限。** Sveltia 改状态的方式是去 patch PR 背后的那个 issue，所以细粒度 PAT 还需要 **Issues: read and write**；只有 Contents 和 Pull requests 是不够的。补齐之后写作、存草稿、切换状态、发布全都在 CMS 里完成，不需要离开。

（保存草稿只用到 `POST /issues/N/labels`，所以那一步在缺 Issues 权限时也能成功——于是症状会表现为「草稿能存，但状态改不动」，很容易被误判成上游 bug。）

## 更新主题

```bash
bash scripts/fireflyer-merge-upstream.sh
```

它会拉取上游并合并，同时保住你的内容。`src/config/` 里的冲突是正常的——主题更新会新增配置键，你应该接受它们。`src/content/` 里的冲突则不该出现：你的内容优先，删除也会被保留。

它不用 `-X ours`，因为那个开关解决不了真正要紧的情况：当一次更新修改了你已删除的 demo 文章时，git 报 `modify/delete` 冲突、忽略合并驱动，并把上游那份留在工作区。脚本显式处理这些情况。

## 部署

推送到 `master` 会构建站点，把 `dist/` 打包以时间戳为名传到服务器，然后让 `current` 符号链接指向它。不需要重启任何东西——Web 服务器每次请求都从磁盘读。

回滚就是指定一个更早的 release：

```bash
ls ~/fireflyer/releases
bash ~/fireflyer/release.sh 20260919180000
```

回滚只是一次符号链接切换，所以是瞬时的，也不需要重新构建。最近 5 个 release 会被保留。

## 仓库 secrets

部署需要四个 secrets，在 Settings → Secrets and variables → Actions 下配置：

| Secret | 值 |
| --- | --- |
| `VPS_HOST` | 服务器主机名或 IP |
| `VPS_USER` | 非 root 的部署用户 |
| `VPS_SSH_KEY` | 该用户的私钥，完整内容 |
| `VPS_BASE` | 存放 `releases/`、`current` 和 `release.sh` 的目录 |

## Fireflyer 添加的文件

以下全部是新路径——没有一个是主题自带的文件，这正是主题更新不产生冲突的原因。在本仓库里改动它们中的任何一个，都意味着下一次 `fireflyer inject` 会把它覆盖掉；要改请改 Fireflyer 仓库。

```
public/admin/index.html
public/admin/config.yml
public/admin/sveltia-cms.js
public/admin/chunks/react-dom.js
.github/workflows/fireflyer-deploy.yml
deploy/release.sh
scripts/fireflyer-merge-upstream.sh
src/content/.gitattributes
.node-version
```
