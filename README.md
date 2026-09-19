# Fireflyer

把一份原版的 [Firefly](https://github.com/CuteLeaf/Firefly) Astro 博客，变成自托管、可在浏览器里编辑的站点，并在主题更新后继续保持这一点。

Fireflyer 是一套脚手架加自动化，不是一个应用。它保存要复制进博客仓库的那些配置，以及把配置放进去的四条命令。它自身不承载任何流量，也没有运行时。

English documentation: [README.en.md](README.en.md).

## 两个仓库

| | |
| --- | --- |
| **本仓库**（公开） | 所有注入内容的唯一真源，不存放博客内容。 |
| **你的博客仓库**（私有） | Firefly 源码、你的内容，以及被注入的文件。 |

博客仓库是通过**镜像**建立、而不是 fork——GitHub 不允许把公开仓库的 fork 转为私有，而 Firefly 是公开的。完整历史是**必需**的：以后合并主题更新需要一个共同祖先。

主题更新通过 `upstream` remote 以普通 merge 进入，这正是 Firefly 官方推荐的做法。Fireflyer 添加的每一个文件都是主题本身没有的，所以这些合并不会冲突。

## 安装

需要 Python 3.13 或更高。博客本身需要 Node 22 和 pnpm，Fireflyer 不需要。

```bash
uv tool install git+https://github.com/TGBUG/Fireflyer
```

## 配置流程

### 1. 手工建一个**空的**私有仓库

只有这一步是手工的。自动化它需要 `Administration: write` 权限，而那个权限不该常驻在操作者机器上。仓库必须为空——`init` 会拒绝有分支的仓库，以免覆盖已有内容。

### 2. 一条命令完成其余

```bash
export GH_TOKEN=...            # 需要 Contents: write 和 Actions: write
fireflyer init <你>/<博客仓>
```

`GH_TOKEN` 必须**能访问这个仓库**。细粒度 PAT 是按仓库逐个授权的——**删除并重建一个仓库之后，即使名字一模一样，它也是新仓库、新的 ID，原 token 里的授权会失效**。症状是访问该仓库一律返回 404：细粒度 token 有意不区分「不存在」和「无权限」。这时去 token 设置里把新仓库重新加进授权范围即可。

它会依次：

1. **镜像** Firefly 的完整历史。先**单独**推 `master`，再推其余分支和 tag——空仓库里第一个被推上去的分支会成为默认分支，而一次性推全部分支会让 GitHub 自己挑，实测它挑中的不是 `master`
2. 本地克隆出工作树，并把 `upstream` 指向 Firefly
3. 写入注入文件，提交并推送
4. **禁用主题自带的 `build.yml` 和 `deploy.yml`**——它们会在每次 push 时触发，烧掉的额度远超我们自己的部署

第 4 步必须在推送**之后**：GitHub 是在工作内容第一次落到分支上时才注册 workflow 的，所以刚镜像完时列表是空的，没有东西可禁用。

用 `--dir` 指定工作树位置，默认是 `./<仓库名>`。

### 3. 准备服务器

```bash
fireflyer bootstrap-vps <user>@<host> --base /home/deploy/fireflyer
```

它会建好 release 目录、让 `current` 符号链接一开始就指向有效内容、并安装发布脚本。

它**刻意不碰** nginx、TLS 和用户账户——这些归你的主机面板管，Fireflyer 写的任何东西都会在你下次从面板改设置时被覆盖。见 `docs/adr/0006`。

`--base` 必须是 POSIX 路径，因为这个值是用在服务器上的。在 Windows 的 Git Bash 里，MSYS 会改写看起来像 POSIX 路径的参数，在命令前加 `MSYS_NO_PATHCONV=1` 可以阻止它。

### 4. 需要手工完成的部分

- 建一个非 root 的部署用户，把它的公钥放进 `authorized_keys`。它只需要对 `--base` 有写权限，别的不需要。
- 在主机面板里为你的域名建站，网站根目录指向 `<base>/current`，并从面板申请 TLS 证书。（其实也可以不搞，但是本项目没有自带SSL处理）
- 在博客仓库里添加四个 secrets：`VPS_HOST`、`VPS_USER`、`VPS_SSH_KEY`、`VPS_BASE`。
- 删掉 Firefly 自带的 demo 内容（`src/content/posts/` 和 `src/content/dynamic/`），并把 `src/config/siteConfig.ts` 里的 `siteConfig.site_url` 改成你的域名。

### 5. 开始写

打开 `https://<你的域名>/admin/`，用 GitHub **细粒度** PAT 登录。令牌需要三项仓库权限：

| 权限 | 用途 |
| --- | --- |
| `Contents: read and write` | 读写文章与图片 |
| `Pull requests: read and write` | 开、合并、删除工作流分支的 PR |
| `Issues: read and write` | 切换状态 —— Sveltia 是通过 patch PR 背后的那个 issue 来换标签的 |

三项齐了之后，写作、存草稿、切换状态、发布**全都在 CMS 里完成**，不需要去 GitHub 网页。

少给 `Issues` 会出现一个很有迷惑性的症状：草稿能正常保存并开出 PR，但一动状态就报「无法更改状态」。因为保存只用到 `POST /issues/N/labels`，而换标签用的是 `PATCH /issues/N`。

## 命令

| 命令 | 作用 |
| --- | --- |
| `fireflyer init <owner/name>` | 从空仓库一路做到可写作：镜像、注入、推送、禁用主题 CI。 |
| `fireflyer inject <仓库路径>` | 写入附加层。幂等；`--check` 会报告差异并以非零码退出，但不写入。每次全新克隆之后都要重跑。 |
| `fireflyer drift-check <仓库路径>` | 比对 CMS 配置与主题的 Zod schema，并检查仓库状态。 |
| `fireflyer bootstrap-vps <user@host> --base <目录>` | 让服务器具备接收部署的条件。`--print-only` 只打印远端脚本不执行。 |

## 为什么 inject 需要重跑

`src/content/.gitattributes` 把你的内容标记为 `merge=ours`，但那个名字定义在 `.git/config` 里，而 git 从不提交它。所以一个全新的克隆有那个属性、却没有可用的驱动。`fireflyer inject .` 会把它重新建起来；缺失时 `drift-check` 会警告。

另外要注意，合并驱动只处理**两边都存在**的文件。当主题更新修改了一篇你已删除的 demo 文章时，git 报的是 `modify/delete` 冲突，**根本不会调用驱动**，并把上游那份留在工作区。`scripts/fireflyer-merge-upstream.sh`（同样注入进博客仓库）专门处理这种情况，并额外报告上游**新增**到 `src/content/` 的内容。

## 博客仓库自己的文档

写作流程、写作者会踩到的各种限制、以及如何部署与回滚，都写在博客仓库自己的 `FIREFLYER.md` 里。那个文件也是注入的，所以要改请在本仓库改。

## 设计

每个决策的理由都记在 `docs/adr/`。`CONTEXT.md` 是词汇表——注意它把 *publish*（推送到 `master`）和 *deploy*（放置构建产物并重新指向 `current`）区分开来，而本项目早期的设计稿把这两件事混为了一个词。
