# Automation Ops Skill

## 描述

自动化编排 skill。用于定时触发、进程轮询、Git 检查提交推送与任务收尾（如关机）。

## 适用场景

- 按提示词执行“先检查条件，再执行动作”的自动化流程
- 需要同时调用 shell 与 git 工具完成端到端任务
- 需要在 Windows 下做定时启动、进程检查、提交推送、关机

## 调用流程

1. 定时任务创建
   1. 计算目标触发时间（例如当前时间 + 30 分钟）。
   2. 使用系统命令创建一次性定时任务，任务内容为调用 agent task run 并传入后续提示词。
   3. 回读定时任务确认创建成功。

2. 触发后检查训练进程
   1. 先执行只读进程检查（例如 Get-Process 或 tasklist）。
   2. 若存在训练进程，不做 Git 与关机操作，只将下一次检查延后 5 分钟并结束本轮。
   3. 若不存在训练进程，进入 Git 处理流程。

3. Git 检查与提交推送
   1. 执行状态检查与远端同步检查。
   2. 审核变更后暂存并提交。
   3. 推送到远端并验证同步状态。

4. 收尾动作
   1. 仅在 Git 操作成功后，才可执行关机命令。
   2. 输出完整执行日志摘要与结果。

## 注意事项

- 每一步都必须检查 exit_code，失败即停。
- 优先使用只读检查命令，避免先改后看。
- 关机属于高风险操作，必须在用户明确授权场景下执行。
- 发生冲突、推送失败、权限错误时必须中止并报告。
- 允许在工作区外执行命令；但若需要临时写脚本来辅助流程，默认把脚本写在当前任务工作区，避免写入仓库根目录或其他外部绝对路径。

## 禁用命令（默认）

- git reset --hard
- git push --force
- git push -f
- git clean -fdx

如用户明确授权并说明范围，才可在一次性任务中临时执行。

```json
{
  "name": "automation_ops",
  "description": "自动化编排 skill。用于定时触发、进程轮询、Git 检查提交推送与任务收尾（如关机）。",
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "run_shell_command",
        "description": "执行 shell 命令，用于进程检查、定时任务与系统操作。",
        "parameters": {
          "type": "object",
          "properties": {
            "command": {
              "type": "string",
              "description": "要执行的命令字符串。"
            }
          },
          "required": ["command"]
        }
      }
    },
    {
      "type": "function",
      "function": {
        "name": "git_command",
        "description": "执行 git 子命令，用于检查、提交与推送。",
        "parameters": {
          "type": "object",
          "properties": {
            "args": {
              "type": "string",
              "description": "git 参数字符串，例如 'status --short'、'commit -m \"msg\"'。"
            }
          },
          "required": ["args"]
        }
      }
    }
  ]
}
```