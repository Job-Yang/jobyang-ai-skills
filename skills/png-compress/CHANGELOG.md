# CHANGELOG

## 0.2.0 — 2026-10-16

Agent 场景防呆改造:原地覆盖护栏、退出码语义、坏图持久化、排除规则修正。

### 修复
- **P1-1 原地覆盖护栏**:非 git 工作树内默认拒绝原地有损覆盖(exit 1),先 dry-run 预估改动文件数,提示三选一(先提交/备份、`--allow-non-git`、`--output-dir DIR`);git 工作树内维持原原地覆盖流程。
- **P1-2 坏缓存兜底**:`.png_compress_cache.json` 非法 JSON 不再 traceback,警告后改名 `.bak` 并按空缓存重建。
- **P1-3 退出码语义**:有图真失败 exit 2;参数/路径/缺依赖/护栏拒绝 exit 1;全成功(含门禁回退、已知坏图跳过)exit 0。
- **P2-1 坏图持久化**:解码失败的图 hash 写入缓存 `errors` 字段,下次默认跳过并单列"已知坏图",不再每次刷 stderr;`--retry-errors` 可重检。
- **P2-2 文档对齐**:说明 Linux 无 Pillow 时硬门禁同样失效,需 `--no-hard-gate --no-quality-gate`;缺 Pillow 的报错信息同步修正。
- **P2-3 排除规则**:构建产物目录名只在工程顶层直接子目录命中时排除,不再静默误杀 `Resources/build_icons/` 等嵌套同名资源;新增 `--exclude NAME` 可在任意层级追加排除。

### 新增
- `--output-dir DIR`:压缩产物按相对路径写到副本目录,原图零改动;缓存写在输出目录里,key 为原图内容 hash。
- `tests/test_compress_images.py`:10 项回归测试(护栏拒绝/放行、md5 不变、坏缓存不崩、exit 2/0/1、坏图二次跳过、嵌套排除、APNG 保护)。

### 重构
- 主流程抽为 `run_pass()`,护栏拒绝前可复用 dry-run 流水线预估改动数量;`compress_one` 增加 `rel`/`outdir` 参数支持副本模式。
