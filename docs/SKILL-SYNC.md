# 技能多机同步（可移植说明）

所有技能的**唯一权威源是本仓 `skills/`**：在仓里改，提交后单向推送到各技能运行目录与发布 zip，避免旧副本反向覆盖新版本。

## 用法

```bash
# 1) 首次：复制配置模板，填入本机的技能运行目录、zip 目录、备份目录
cp tools/sync.example.json tools/sync.local.json

# 2) 预览差异（不写入）
python3 tools/sync_skills.py

# 3) 确认无 ALERT 后写入
python3 tools/sync_skills.py --apply
```

- `tools/sync.local.json` 已被 git 忽略，不同机器各填各的，不进入公开仓。
- 白名单在 `tools/skills-manifest.json`：只同步其中的自有技能；运行目录里的公司内部/第三方技能一律不碰。
- 同步会排除 `.git .deps __pycache__ .pytest_cache *.pyc .DS_Store` 和悬空符号链接。
- 若某目标存在权威源里没有的文件（可能在该目录直接改过没回灌），会标 `ALERT`；`--apply` 时先整体备份到 `backup_root/<时间戳>/` 再覆盖，不会静默丢东西。
- 新增技能后：放进 `skills/<name>/`，在 manifest 加一行，跑一次同步即可。

## 手动安装到任意宿主

不想用同步脚本时，直接把技能目录复制到目标宿主的技能文件夹即可，例如：

```bash
mkdir -p ~/.trae/skills
cp -R skills/outside-view ~/.trae/skills/outside-view
```

其他宿主使用各自的技能目录（如 `~/.claude/skills/`）。技能不依赖任何特定运行时，复制后即可按需加载。
