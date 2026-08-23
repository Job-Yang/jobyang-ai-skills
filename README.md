# Job Yang AI Skills

Job Yang 的 AI Agent Skills 技能表。

我把这里当成一个长期的技能仓库：把真实工作里反复用到的判断、流程、脚本和边界，一点点沉淀成 Agent 能复用的 Skill。

AI 时代最容易被低估的东西，不是一次回答写得多漂亮，而是那些能反复起作用的工作方式。一次写作里的取舍，一次视频排查里的观察顺序，一次复杂任务里的证据意识，如果只停留在某次对话里，很快就会散掉。Skill 的价值，就是把这些经验压缩成可安装、可调用、可继续演化的工作单元。

这个仓库收的不是 prompt 小抄，也不是一次性技巧。每个 Skill 都应该是一段已经被真实任务磨过的能力：知道什么时候触发，知道该看什么材料，知道边界在哪里，也知道什么时候该停下来让人判断。

[English](./README.en.md)

## 技能列表

| Skill | 用来做什么 |
| --- | --- |
| [vdd](./skills/vdd/) | 面向验证的开发：在说“做完了/没问题”之前先走一遍验证，不乱报喜、不硬挤问题、敢说没问题。 |
| [haohao-shuohua](./skills/haohao-shuohua/) | 把中文写得更像人说的：保事实、去 AI 味、加中文味、不许造词充深刻。 |
| [cuihuo](./skills/cuihuo/) | 观点淬硬引擎：把一个技术观点写成平实克制、一节一观点的对外硬文，或提炼成短思考手记。 |
| [tangshan-style](./skills/tangshan-style/) | 汤山体：把面向未来的想象与推演写成有历史纵深、每句耐嚼的畅想文。 |
| [feynman-explainer](./skills/feynman-explainer/) | 用费曼技巧把复杂的东西讲透：一条逻辑链层层推导，让外行也能真正理解。 |
| [sansi-erhouxing](./skills/sansi-erhouxing/) | 三思而后行：改任何成形文档前先通读全文骨架，别只盯一段、别补丁摞补丁。 |
| [video-reader](./skills/video-reader/) | 把视频转成带时间戳的关键帧和运动时间线，让只能看图的大模型也能判断第几秒发生了什么。 |

## 为什么要有这个仓库

很多 AI 能力看起来像一次性的对话技巧，其实背后都有可以沉淀的结构。

写作不是“润色一下”，而是一组关于事实、语气、节奏和删改边界的判断。看视频不是“让模型看一眼”，而是先把动态过程拆成关键帧、时间线和可复核的观察。类似的东西积累多了，就应该从聊天记录里拿出来，变成独立的 Skill。

我希望这里的技能都满足几个要求：

- **足够具体**：解决一个真实问题，不做泛泛的“提升效率”。
- **有边界感**：知道自己该做什么，也知道哪些判断不能替人做。
- **能被复用**：不是一段灵感，而是下次还能装上、还能跑起来的能力。
- **允许带工具**：纯文字规则不够时，就把脚本、资料和流程一起放进来。
- **持续变厚**：新的经验会继续沉淀进去，Skill 应该越用越像一套手艺。

## 安装

克隆仓库后，把需要的技能目录复制到你的 Agent Skills 目录。

```bash
git clone https://github.com/Job-Yang/jobbyang-ai-skills.git
cp -R jobbyang-ai-skills/skills/haohao-shuohua ~/.claude/skills/haohao-shuohua
cp -R jobbyang-ai-skills/skills/video-reader ~/.claude/skills/video-reader
```

Claude Code 的默认用户级目录：

```text
~/.claude/skills/
```

安装时要保留完整技能目录，不要只复制 `SKILL.md`。有些技能会读取 `references/`、`scripts/` 或 `assets/`。

## 目录结构

```text
.
├── README.md
├── README.en.md
└── skills/
    ├── vdd/
    ├── haohao-shuohua/
    ├── cuihuo/
    ├── tangshan-style/
    ├── feynman-explainer/
    ├── sansi-erhouxing/
    └── video-reader/
```

每个技能目录都以 `SKILL.md` 为入口，部分带 `references/`、`scripts/` 或 `assets/`。

## License

MIT
