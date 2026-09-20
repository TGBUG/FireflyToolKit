# FireflyToolKit

*Powered by Deepseek*

一个用于把一份原版的 [Firefly](https://github.com/CuteLeaf/Firefly) Astro 博客，变成自托管、可在浏览器里编辑的站点的工具包。

## 开始之前

|                  |                                                                                |
|------------------|--------------------------------------------------------------------------------|
| 一个私有 GitHub 仓库   | 新建的空仓库，或者被上一次中断的运行留下的那个——脚本只拒绝**已经装好 FireflyToolKit** 的仓库                      |
| 一个 PAT        | 至少需要 `Contents`、`Actions`、`Workflows`、`Pull request`、`Issue`，都选 read and write |
| 服务器上的一个非 root 账户 | 只需要对 release 目录有写权限                                                            |
| 仓库设置好secrets     | 设置好下面的的4个secrets                                                               |

| Secret | 值 |
| --- | --- |
| `VPS_HOST` | 服务器主机名或 IP |
| `VPS_USER` | 那个非 root 账户 |
| `VPS_SSH_KEY` | 该账户的私钥，**完整内容，且不能带口令**——Actions 的 runner 没法输口令 |
| `VPS_BASE` | 传给脚本的 release 目录 |

## 用法

```bash
curl -fsSL https://raw.githubusercontent.com/TGBUG/FireflyToolKit/master/ftk.sh -o ftk.sh
bash ftk.sh
```

根据询问提供：仓库名、token、release 目录放哪。然后：

1. **镜像** Firefly 的完整历史。先**单独**推 `master`，再推其余分支和 tag——空仓库里第一个被推上去的分支会成为默认分支，而一次性推全部分支会让 GitHub 自己挑，实测它挑中的不是 `master`
2. 写入工具文件并推送
3. 禁用主题自带的 `build.yml` 和 `deploy.yml`，并**取消它自己那次推送触发的运行**。禁用不会中止已经排队的运行，而那些正是最贵的
4. 建好 release 目录、`current` 符号链接和 `release.sh`

工具**不提供**三个东西：

- nginx配置
- TLS
- 用户账户

## 跑完之后，还剩这些（都是手工的）

1. **建站**，根目录设为 `<base>/current`
2. **删掉主题的 demo 内容**：`src/content/`。另外删掉 `.github/dependabot.yml`（可选，不删可能占用action运行时间。
3. 修改Firefly配置

之后写作在 `https://<你的域名>/admin/index,html`，你的 PAT 登录。

## 仓库结构

```
ftk.sh      唯一的脚本
layer/      写进博客仓库的文件，目录结构镜像博客仓库的根
docs/adr/   每个决策的理由，以及被否决的方案
CONTEXT.md  词汇表
```

`layer/` 里**每一个文件名都是主题不自带的**，这就是主题更新不产生冲突的原因。改这些文件请改这里，不要改博客仓库里的副本。
