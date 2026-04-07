# ttpkgUnpacker

用于解包抖音小程序和抖音小游戏的 `TPKG` / `ttpkg.js` / `pkg` 文件。

当前版本已经覆盖两类包：

1. 明文索引的小程序包。
2. 带 `JSON{"__ttks":...}` 头部的小游戏包索引变体。

## 这次优化了什么

- 修复入口脚本无输出的问题，支持直接执行和模块方式执行。
- 修复明文 `TPKG` 索引的错误偏移兼容问题。
- 新增 `__ttks` 加密索引小游戏包解码，可恢复文件名、偏移和大小。
- 自动生成解包报告，包含树状结构、文件统计、入口文件和可提取信息。
- 对普通小程序包增加 `app.json` 与页面 `*.json` 的自动恢复。
- 目录模式下支持同名包安全输出，避免覆盖。

## 使用方法

### 解单个包

```bash
python3 ttpkgUnpacker/main.py ttpkgUnpacker/js/038d897.ttpkg.js
```

或：

```bash
python3 -m ttpkgUnpacker ttpkgUnpacker/js/038d897.ttpkg.js
```

默认输出到：

```text
原始包路径_unpack
```

### 解整个目录

```bash
python3 -m ttpkgUnpacker ttpkgUnpacker/js
```

程序会递归扫描目录中的 `.ttpkg.js`、`.ttpkg`、`.pkg` 文件并逐个解包。

### 指定输出目录

```bash
python3 -m ttpkgUnpacker ttpkgUnpacker/js -o /tmp/ttpkg_out
```

输出目录格式：

```text
/tmp/ttpkg_out/<包文件名>_unpack
```

如果目录里存在同名包，会自动追加父目录名和短哈希，避免互相覆盖。

## 解包产物

每次解包完成后，输出目录中会自动生成：

```text
unpack-report.json
unpack-report.md
```

报告包含：

- 包类型和头部信息
- 文件数量与扩展名分布
- 入口文件与可提取的应用信息
- 恢复出的 `app.json` / 页面 `json` 统计
- 完整树状结构图

对于普通小程序包，如果 `app-config.json` 可解析，还会自动恢复：

- `app.json`
- `pages/**.json`

## 内置样本

仓库 `ttpkgUnpacker/js` 目录现在包含三个已验证样本：

- `038d897.ttpkg.js`
  明文小程序样本
- `e2670a8.pkg`
  来自公开仓库的明文 `.pkg` 样本
- `8862e65.pkg`
  已验证可解的小游戏 `__ttks` 索引样本

## 稳定性说明

- 自动校验 `TPKG` 包头和索引边界，损坏包会给出明确错误。
- 禁止路径逃逸写出，避免包内恶意路径写到输出目录外。
- 对 `__ttks` 变体，当前已经能完整恢复索引并写出全部文件。
- 但部分小游戏 payload 仍可能带业务侧混淆，解包不等于完全反混淆。

## 参考与对照

这次优化时主要参考了以下社区资料和公开实现：

- bignius 的公开实现与样本包：<https://gitee.com/bignius/ttpkUnpacker>
- 52pojie 原理帖：<https://www.52pojie.cn/thread-1684583-1-1.html>

实际对照后，当前版本吸收了其中“样本验证”和“配置恢复”这类稳定能力；`ttss/ttml` 的规则恢复逻辑仍偏启发式，暂未直接并入主流程。

## 回归验证

仓库内已附带 `unittest` 用例，可直接执行：

```bash
python3 -m unittest discover -s tests
```

我本地已验证，但用的都是老版本的ttpkg，如果有无法解包的新版可以联系我我再进行更新。

## Stargazers over time

[![Stargazers over time](https://starchart.cc/XueDugu/ttpkgUnpacker.svg)](https://starchart.cc/XueDugu/ttpkgUnpacker)
