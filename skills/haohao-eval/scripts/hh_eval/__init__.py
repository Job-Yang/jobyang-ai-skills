"""haohao-eval 每日召回的确定性部分（从 scripts/loop.py 拆出的包）。

布局：
- const     常量、Stop 异常
- fs        路径与文件读写、配置/状态读写、Lock、pkg 数据定位
- judge     文本工具、机械检查、裁判答案核对（引用逐字核对）
- seed      种子池、抽样、作者说明、判例、问题池与病灶
- fp        haohao-shuohua 底线指纹与技能指纹
- rules     细则（每日细则 markdown）解析与候选校验
- gates     门禁、指标、争议队列、发布/回滚/监控、压缩清理
- statedoc  飞书状态文档的生成、解析、恢复
- docdoc    飞书召回文档的解析与每日记录生成
- pipeline  各个子命令的编排
- preflight 开跑前自诊断（结构化停下，机器可读 JSON）
- cli       argparse 入口

scripts/loop.py 是薄兼容入口：python3 loop.py <旧命令> 一切照旧。
"""
