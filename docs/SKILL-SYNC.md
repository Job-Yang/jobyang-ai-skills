# 技能多机同步与插件注册（可移植说明）

所有技能的**唯一权威源是本仓 `skills/`**：在仓里改，提交后单向推送到各技能运行目录与发布 zip，避免旧副本反向覆盖新版本；全局公共契约放在 `shared/`，可迁移研发原则规则插件（零后台钩子拦截）放在 `plugins/engineering-flow/`。

## 用法

```bash
# 1) 首次：复制配置模板，填入本机的技能运行目录、zip 目录（可用 groups 或 only 过滤）
cp tools/sync.example.json tools/sync.local.json

# 2) 预览差异（不写入）
python3 tools/sync_skills.py

# 3) 确认无 ALERT 后全量写入；或按分组仅同步工程链路
python3 tools/sync_skills.py --apply
python3 tools/sync_skills.py --group engineering --apply

# 4) 公共源文件维护与 drift 只读检查
python3 tools/sync_skills.py --sync-shared
python3 tools/sync_skills.py --check-shared

# 5) 幂等注册可迁移研发原则规则插件（零后台钩子拦截，写 ~/.gemini/config/plugins.json，不改 hooks.json）
python3 tools/sync_skills.py --apply --sync-agy-plugin
```

- `tools/sync.local.json` 已被 git 忽略，不同机器各填各的，不进入公开仓；`targets` 中默认跳过本地不存在的宿主根目录（如需强制初始化才加 `--create-missing-targets`）。
- 白名单与分组在 `tools/skills-manifest.json`：只同步其中的自有技能；运行目录里的公司内部/第三方技能一律不碰。
- `shared/` 为多技能共享文件的唯一源头，正常同步前会自动执行 `--check-shared`，有漂移时先运行 `--sync-shared` 再同步宿主。
- 同步会排除 `.git .deps __pycache__ .pytest_cache *.pyc .DS_Store` 和悬空符号链接。
- 若某目标存在权威源里没有的文件（可能在该目录直接改过没回灌），会标 `ALERT`；脚本本身不创建自动备份目录（唯一备份是 Git 历史），`--apply` 会直接覆盖并清理这些源外文件，请先回灌 Git 或手动备份再写入。
- 新增技能后：放进 `skills/<name>/`，在 manifest 加一行并归入逻辑分组，跑一次同步即可。

## 手动安装到任意宿主

不想用同步脚本时，直接把技能目录复制到目标宿主的技能文件夹即可，例如：

```bash
mkdir -p ~/.trae/skills
cp -R skills/outside-view ~/.trae/skills/outside-view
```

其他宿主使用各自的技能目录（如 `~/.claude/skills/`）。技能不依赖任何特定运行时，复制后即可按需加载。
